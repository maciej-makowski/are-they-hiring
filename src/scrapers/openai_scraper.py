from src.scrapers.base import BaseScraper


class OpenAIScraper(BaseScraper):
    company = "openai"
    api_url = "https://api.ashbyhq.com/posting-api/job-board/openai"

    def parse_response(self, data: dict | list) -> list[dict]:
        jobs = data.get("jobs", []) if isinstance(data, dict) else data
        postings = []
        for job in jobs:
            title = job.get("title", "")
            location = job.get("location", "")
            url = job.get("jobUrl", "")

            if title and url:
                postings.append({
                    "title": title.strip(),
                    "location": location.strip() if location else "",
                    "url": url,
                })
        return postings
