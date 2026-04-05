from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, JobPosting
from src.scrapers.base import BaseScraper
from src.scrapers.scheduler import SCRAPERS, classify_postings, fetch_and_save


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
async def test_fetch_and_save_success(session_factory):
    with patch.dict(SCRAPERS, {"fake": FakeScraper}):
        result = await fetch_and_save("fake", session_factory)

    assert result.status == "success"
    assert result.company == "fake"
    assert result.postings_found == 2
    assert result.attempt_number == 1
    assert result.finished_at is not None
    assert result.stage is None  # cleared after completion

    # Verify postings were saved
    async with session_factory() as session:
        res = await session.execute(select(JobPosting).where(JobPosting.company == "fake"))
        postings = list(res.scalars().all())
    assert len(postings) == 2
    # Postings should not be classified yet
    assert all(p.is_software_engineering is False for p in postings)


@pytest.mark.asyncio
async def test_fetch_failure_retries(session_factory):
    FailingScraper.call_count = 0

    with (
        patch.dict(SCRAPERS, {"failing": FailingScraper}),
        patch("src.scrapers.scheduler.settings") as mock_settings,
        patch("src.scrapers.scheduler.asyncio.sleep", new_callable=AsyncMock),
    ):
        mock_settings.scrape_retry_max = 3

        with pytest.raises(RuntimeError, match="Scrape failed!"):
            await fetch_and_save("failing", session_factory)

    assert FailingScraper.call_count == 3


@pytest.mark.asyncio
async def test_classify_postings(session_factory):
    # First, fetch and save
    with patch.dict(SCRAPERS, {"fake": FakeScraper}):
        await fetch_and_save("fake", session_factory)

    # Then classify separately
    mock_classify = AsyncMock(
        return_value={
            "Software Engineer": True,
            "Product Manager": False,
        }
    )

    with patch("src.scrapers.scheduler.classify_titles", mock_classify):
        count = await classify_postings(company="fake", session_factory=session_factory)

    assert count == 1  # only Software Engineer changed to True
    args, kwargs = mock_classify.call_args
    assert "Software Engineer" in args[0]
    assert "Product Manager" in args[0]

    # Verify classification was applied
    async with session_factory() as session:
        res = await session.execute(select(JobPosting).where(JobPosting.company == "fake").order_by(JobPosting.title))
        postings = list(res.scalars().all())
    pm = next(p for p in postings if p.title == "Product Manager")
    swe = next(p for p in postings if p.title == "Software Engineer")
    assert swe.is_software_engineering is True
    assert pm.is_software_engineering is False


@pytest.mark.asyncio
async def test_reclassify_postings(session_factory):
    # Fetch and save
    with patch.dict(SCRAPERS, {"fake": FakeScraper}):
        await fetch_and_save("fake", session_factory)

    # Classify once
    mock_classify = AsyncMock(
        return_value={
            "Software Engineer": True,
            "Product Manager": False,
        }
    )
    with patch("src.scrapers.scheduler.classify_titles", mock_classify):
        await classify_postings(company="fake", session_factory=session_factory)

    # Reclassify with different results (force=True)
    mock_reclassify = AsyncMock(
        return_value={
            "Software Engineer": False,
            "Product Manager": True,
        }
    )
    with patch("src.scrapers.scheduler.classify_titles", mock_reclassify):
        count = await classify_postings(company="fake", session_factory=session_factory, force=True)

    assert count == 2  # both changed

    async with session_factory() as session:
        res = await session.execute(select(JobPosting).where(JobPosting.company == "fake").order_by(JobPosting.title))
        postings = list(res.scalars().all())
    pm = next(p for p in postings if p.title == "Product Manager")
    swe = next(p for p in postings if p.title == "Software Engineer")
    assert swe.is_software_engineering is False
    assert pm.is_software_engineering is True
