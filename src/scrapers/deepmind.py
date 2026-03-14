from playwright.async_api import Page
from src.scrapers.base import BaseScraper
from src.config import settings


class DeepMindScraper(BaseScraper):
    company = "deepmind"
    careers_url = settings.deepmind_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        postings = []
        cards = page.locator(".career-card")
        count = await cards.count()
        for i in range(count):
            item = cards.nth(i)
            link = item.locator("a").first
            title_el = item.locator("h3").first
            location_el = item.locator(".location").first

            title = await title_el.text_content() or ""
            location = await location_el.text_content() or ""
            href = await link.get_attribute("href") or ""

            if href and not href.startswith("http"):
                href = f"https://deepmind.google{href}"

            postings.append({
                "title": title.strip(),
                "location": location.strip(),
                "url": href,
            })
        return postings
