import uuid
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from src.scrapers.scheduler import run_scrape, SCRAPERS
from src.scrapers.base import BaseScraper
from src.db.models import Base, ScrapeRun

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class FakeScraper(BaseScraper):
    company = "fake"
    api_url = "https://fake.com/api/jobs"

    def parse_response(self, data):
        return data

    async def run(self) -> list[dict]:
        return [
            {"title": "Software Engineer", "location": "Remote", "url": "https://fake.com/jobs/1"},
            {"title": "Product Manager", "location": "NYC", "url": "https://fake.com/jobs/2"},
        ]


class FailingScraper(BaseScraper):
    company = "failing"
    api_url = "https://failing.com/api/jobs"
    call_count = 0

    def parse_response(self, data):
        return []

    async def run(self) -> list[dict]:
        FailingScraper.call_count += 1
        raise RuntimeError("Scrape failed!")


@pytest.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_run_scrape_success(session_factory):
    mock_classify = AsyncMock(return_value={
        "Software Engineer": True,
        "Product Manager": False,
    })

    with patch.dict(SCRAPERS, {"fake": FakeScraper}), \
         patch("src.scrapers.scheduler.classify_titles", mock_classify):
        result = await run_scrape("fake", session_factory)

    assert result.status == "success"
    assert result.company == "fake"
    assert result.postings_found == 2
    assert result.attempt_number == 1
    assert result.finished_at is not None
    mock_classify.assert_called_once()


@pytest.mark.asyncio
async def test_run_scrape_failure_retries(session_factory):
    FailingScraper.call_count = 0

    with patch.dict(SCRAPERS, {"failing": FailingScraper}), \
         patch("src.scrapers.scheduler.settings") as mock_settings, \
         patch("src.scrapers.scheduler.asyncio.sleep", new_callable=AsyncMock):
        mock_settings.scrape_retry_max = 3

        with pytest.raises(RuntimeError, match="Scrape failed!"):
            await run_scrape("failing", session_factory)

    assert FailingScraper.call_count == 3


@pytest.mark.asyncio
async def test_run_scrape_classifies_titles(session_factory):
    mock_classify = AsyncMock(return_value={
        "Software Engineer": True,
        "Product Manager": False,
    })

    with patch.dict(SCRAPERS, {"fake": FakeScraper}), \
         patch("src.scrapers.scheduler.classify_titles", mock_classify):
        await run_scrape("fake", session_factory)

    mock_classify.assert_called_once_with(["Software Engineer", "Product Manager"])
