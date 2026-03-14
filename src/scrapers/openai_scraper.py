from playwright.async_api import Page
from src.scrapers.base import BaseScraper
from src.config import settings


class OpenAIScraper(BaseScraper):
    company = "openai"
    careers_url = settings.openai_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        postings = []
        cards = page.locator(".job-card")
        count = await cards.count()
        for i in range(count):
            item = cards.nth(i)
            link = item.locator("a").first
            title_el = item.locator(".job-title").first
            location_el = item.locator(".job-location").first

            title = await title_el.text_content() or ""
            location = await location_el.text_content() or ""
            href = await link.get_attribute("href") or ""

            postings.append({
                "title": title.strip(),
                "location": location.strip(),
                "url": href,
            })
        return postings
