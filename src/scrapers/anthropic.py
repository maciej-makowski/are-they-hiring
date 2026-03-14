from playwright.async_api import Page
from src.scrapers.base import BaseScraper
from src.config import settings


class AnthropicScraper(BaseScraper):
    company = "anthropic"
    careers_url = settings.anthropic_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        postings = []
        listings = page.locator('[data-testid="job-listing"]')
        count = await listings.count()
        for i in range(count):
            item = listings.nth(i)
            link = item.locator("a").first
            title_el = item.locator("h3").first
            location_el = item.locator(".location").first

            title = await title_el.text_content() or ""
            location = await location_el.text_content() or ""
            href = await link.get_attribute("href") or ""

            if href and not href.startswith("http"):
                href = f"https://www.anthropic.com{href}"

            postings.append({
                "title": title.strip(),
                "location": location.strip(),
                "url": href,
            })
        return postings
