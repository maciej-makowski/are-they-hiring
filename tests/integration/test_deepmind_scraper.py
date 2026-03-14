import pathlib
import pytest
from playwright.async_api import async_playwright
from src.scrapers.deepmind import DeepMindScraper

FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "html_snapshots" / "deepmind_careers.html"


@pytest.fixture
async def browser_page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.mark.asyncio
async def test_deepmind_extract_postings(browser_page):
    html = FIXTURE_PATH.read_text()
    await browser_page.set_content(html)

    scraper = DeepMindScraper()
    postings = await scraper.extract_postings(browser_page)

    assert len(postings) == 3

    assert postings[0]["title"] == "SRE Engineer"
    assert postings[0]["location"] == "London, UK"
    assert postings[0]["url"] == "https://deepmind.google/careers/positions/sre-engineer"

    assert postings[1]["title"] == "Research Scientist"
    assert postings[1]["location"] == "Mountain View, CA"
    assert postings[1]["url"] == "https://deepmind.google/careers/positions/research-scientist"

    assert postings[2]["title"] == "Platform Engineer"
    assert postings[2]["location"] == "London, UK"
    assert postings[2]["url"] == "https://deepmind.google/careers/positions/platform-engineer"
