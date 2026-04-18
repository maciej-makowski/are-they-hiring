"""Tests for xAI scraper (Greenhouse API)."""

from src.scrapers.xai import XAIScraper


def test_xai_parse_greenhouse_response():
    scraper = XAIScraper()
    data = {
        "jobs": [
            {
                "id": 5045788007,
                "title": "Software Engineer - Infrastructure",
                "location": {"name": "Palo Alto, California, United States"},
                "absolute_url": "https://job-boards.greenhouse.io/xai/jobs/5045788007",
            },
            {
                "id": 4922800007,
                "title": "Research Engineer",
                "location": {"name": "Remote"},
                "absolute_url": "https://job-boards.greenhouse.io/xai/jobs/4922800007",
            },
        ]
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Software Engineer - Infrastructure"
    assert postings[0]["location"] == "Palo Alto, California, United States"
    assert "5045788007" in postings[0]["url"]
    assert postings[1]["title"] == "Research Engineer"
    assert postings[1]["location"] == "Remote"


def test_xai_parse_empty():
    scraper = XAIScraper()
    assert scraper.parse_response({"jobs": []}) == []


def test_xai_parse_missing_fields():
    scraper = XAIScraper()
    data = {"jobs": [{"title": "", "location": {}, "absolute_url": ""}]}
    assert scraper.parse_response(data) == []
