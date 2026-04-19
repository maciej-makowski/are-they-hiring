import json

import httpx

from src.scrapers.base import BaseScraper


class MetaScraper(BaseScraper):
    company = "meta"
    api_url = "https://www.metacareers.com/graphql"

    # Meta's careers frontend issues a GraphQL "CareersJobSearchResultsQuery" against
    # this endpoint. `doc_id` is the persisted-query hash published by their bundle.
    # If Meta changes the hash, fetches will 4xx — the scrape_runs table captures that.
    #
    # `teams` / `sub_teams` left empty => all Meta roles across every team, not just
    # the AI / FAIR team. The endpoint returns the full result set in a single
    # response and signals completion via `extensions.is_final = true`, so no
    # cursor-based pagination is needed at the current size (~600 open roles).
    _doc_id = "9114524511922157"
    _search_input = {
        "q": "",
        "teams": [],
        "offices": [],
        "divisions": [],
        "roles": [],
        "leadership_levels": [],
        "is_leadership": False,
        "is_in_page": False,
        "sub_teams": [],
    }

    async def run(self) -> list[dict]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.api_url,
                headers={"User-Agent": "AreTheyHiringBot/1.0"},
                data={
                    "fb_dtsg": "",
                    "doc_id": self._doc_id,
                    "variables": json.dumps({"search_input": self._search_input}),
                },
            )
            response.raise_for_status()
            data = response.json()
        return self.parse_response(data)

    def parse_response(self, data: dict | list) -> list[dict]:
        if not isinstance(data, dict):
            return []
        jobs = (data.get("data") or {}).get("job_search") or []
        postings = []
        for job in jobs:
            title = (job.get("title") or "").strip()
            job_id = str(job.get("id") or "").strip()
            if not title or not job_id:
                continue
            locations = job.get("locations") or []
            if not locations:
                location = "Unlisted"
            elif len(locations) == 1:
                location = locations[0]
            else:
                location = f"{locations[0]} (+{len(locations) - 1} more)"
            postings.append(
                {
                    "title": title,
                    "location": location,
                    "url": f"https://www.metacareers.com/jobs/{job_id}/",
                }
            )
        return postings
