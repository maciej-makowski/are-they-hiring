"""Tests for Anthropic scraper (Greenhouse API)."""
import pytest
from src.scrapers.anthropic import AnthropicScraper


def test_anthropic_parse_greenhouse_response():
    scraper = AnthropicScraper()
    data = {
        "jobs": [
            {
                "id": 5101832008,
                "title": "Software Engineer",
                "location": {"name": "San Francisco, CA"},
                "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/5101832008",
            },
            {
                "id": 5116274008,
                "title": "Applied AI Engineer",
                "location": {"name": "London, UK"},
                "absolute_url": "https://job-boards.greenhouse.io/anthropic/jobs/5116274008",
            },
        ]
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Software Engineer"
    assert postings[0]["location"] == "San Francisco, CA"
    assert "5101832008" in postings[0]["url"]
    assert postings[1]["title"] == "Applied AI Engineer"


def test_anthropic_parse_empty():
    scraper = AnthropicScraper()
    assert scraper.parse_response({"jobs": []}) == []


def test_anthropic_parse_missing_fields():
    scraper = AnthropicScraper()
    data = {"jobs": [{"title": "", "location": {}, "absolute_url": ""}]}
    assert scraper.parse_response(data) == []
