"""Tests for base scraper."""
import pytest
from unittest.mock import AsyncMock, patch

from src.scrapers.base import BaseScraper


class FakeScraper(BaseScraper):
    company = "fake"
    api_url = "https://fake.com/api/jobs"

    def parse_response(self, data):
        return [{"title": j["name"], "location": "SF", "url": j["link"]} for j in data]


@pytest.mark.asyncio
async def test_base_scraper_run():
    import httpx

    mock_response = httpx.Response(
        200,
        json=[{"name": "SWE", "link": "https://fake.com/swe-1"}],
        request=httpx.Request("GET", "https://fake.com/api/jobs"),
    )

    with patch("src.scrapers.base.httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_client

        scraper = FakeScraper()
        postings = await scraper.run()

    assert len(postings) == 1
    assert postings[0]["title"] == "SWE"
