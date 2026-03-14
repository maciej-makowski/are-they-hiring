import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from playwright.async_api import Page
from src.scrapers.base import BaseScraper


class FakeScraper(BaseScraper):
    company = "fake"
    careers_url = "https://fake.com/careers"

    async def extract_postings(self, page: Page) -> list[dict]:
        return [
            {"title": "Software Engineer", "location": "Remote", "url": "https://fake.com/jobs/1"},
        ]


@pytest.mark.asyncio
async def test_base_scraper_run():
    mock_page = AsyncMock()
    mock_context = AsyncMock()
    mock_context.new_page.return_value = mock_page

    mock_browser = AsyncMock()
    mock_browser.new_context.return_value = mock_context

    mock_pw = AsyncMock()
    mock_pw.chromium.launch.return_value = mock_browser

    mock_pw_context = AsyncMock()
    mock_pw_context.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw_context.__aexit__ = AsyncMock(return_value=False)

    with patch("src.scrapers.base.async_playwright", return_value=mock_pw_context):
        with patch("src.scrapers.base.settings") as mock_settings:
            mock_settings.scrape_delay_seconds = 0

            scraper = FakeScraper()
            result = await scraper.run()

    assert len(result) == 1
    assert result[0]["title"] == "Software Engineer"
    mock_page.goto.assert_called_once_with("https://fake.com/careers", wait_until="networkidle")
    mock_browser.new_context.assert_called_once()
    mock_context.close.assert_called_once()
    mock_browser.close.assert_called_once()
