from abc import ABC, abstractmethod

import httpx


class BaseScraper(ABC):
    company: str
    api_url: str

    @abstractmethod
    def parse_response(self, data: dict | list) -> list[dict]:
        """Parse API response into list of dicts with keys: title, location, url"""
        ...

    async def run(self) -> list[dict]:
        """Fetch job listings from the company's job board API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.api_url,
                headers={"User-Agent": "AreTheyHiringBot/1.0"},
            )
            response.raise_for_status()
            data = response.json()
        return self.parse_response(data)
