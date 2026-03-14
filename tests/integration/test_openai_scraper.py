import pathlib
import pytest
from playwright.async_api import async_playwright
from src.scrapers.openai_scraper import OpenAIScraper

FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "html_snapshots" / "openai_careers.html"


@pytest.fixture
async def browser_page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.mark.asyncio
async def test_openai_extract_postings(browser_page):
    html = FIXTURE_PATH.read_text()
    await browser_page.set_content(html)

    scraper = OpenAIScraper()
    postings = await scraper.extract_postings(browser_page)

    assert len(postings) == 2

    assert postings[0]["title"] == "Senior Frontend Engineer"
    assert postings[0]["location"] == "San Francisco"
    assert postings[0]["url"] == "https://openai.com/careers/senior-frontend-engineer"

    assert postings[1]["title"] == "ML Engineer"
    assert postings[1]["location"] == "Remote"
    assert postings[1]["url"] == "https://openai.com/careers/ml-engineer"
