import pathlib
import pytest
from playwright.async_api import async_playwright
from src.scrapers.anthropic import AnthropicScraper

FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "fixtures" / "html_snapshots" / "anthropic_careers.html"


@pytest.fixture
async def browser_page():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest.mark.asyncio
async def test_anthropic_extract_postings(browser_page):
    html = FIXTURE_PATH.read_text()
    await browser_page.set_content(html)

    scraper = AnthropicScraper()
    postings = await scraper.extract_postings(browser_page)

    assert len(postings) == 3

    assert postings[0]["title"] == "Software Engineer"
    assert postings[0]["location"] == "San Francisco, CA"
    assert postings[0]["url"] == "https://www.anthropic.com/careers/software-engineer"

    assert postings[1]["title"] == "Backend Engineer"
    assert postings[1]["location"] == "Remote"
    assert postings[1]["url"] == "https://www.anthropic.com/careers/backend-engineer"

    assert postings[2]["title"] == "Product Manager"
    assert postings[2]["location"] == "New York, NY"
    assert postings[2]["url"] == "https://www.anthropic.com/careers/product-manager"
