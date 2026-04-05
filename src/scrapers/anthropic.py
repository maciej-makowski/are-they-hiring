from src.scrapers.base import BaseScraper


class AnthropicScraper(BaseScraper):
    company = "anthropic"
    api_url = "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs"

    def parse_response(self, data: dict | list) -> list[dict]:
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        postings = []
        for job in jobs:
            title = job.get("title", "")
            location = job.get("location", {})
            location_name = location.get("name", "") if isinstance(location, dict) else str(location)
            url = job.get("absolute_url", "")

            if title and url:
                postings.append(
                    {
                        "title": title.strip(),
                        "location": location_name.strip(),
                        "url": url,
                    }
                )
        return postings
