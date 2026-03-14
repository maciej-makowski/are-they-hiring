import asyncio
from abc import ABC, abstractmethod
from playwright.async_api import async_playwright, Page
from src.config import settings


class BaseScraper(ABC):
    company: str
    careers_url: str

    @abstractmethod
    async def extract_postings(self, page: Page) -> list[dict]:
        ...

    async def run(self) -> list[dict]:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(
                user_agent="AreTheyHiringBot/1.0 (+https://github.com/are-they-hiring)"
            )
            page = await context.new_page()
            await page.goto(self.careers_url, wait_until="networkidle")
            await asyncio.sleep(settings.scrape_delay_seconds)
            postings = await self.extract_postings(page)
            await context.close()
            await browser.close()
        return postings
