"""Tests for OpenAI scraper (Ashby API)."""
import pytest
from src.scrapers.openai_scraper import OpenAIScraper


def test_openai_parse_ashby_response():
    scraper = OpenAIScraper()
    data = {
        "jobs": [
            {
                "id": "abc-123",
                "title": "Research Scientist",
                "location": "San Francisco, California",
                "department": "Research",
                "jobUrl": "https://jobs.ashbyhq.com/openai/abc-123",
            },
            {
                "id": "def-456",
                "title": "Backend Engineer",
                "location": "New York, New York",
                "department": "Engineering",
                "jobUrl": "https://jobs.ashbyhq.com/openai/def-456",
            },
        ]
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Research Scientist"
    assert postings[0]["location"] == "San Francisco, California"
    assert "abc-123" in postings[0]["url"]
    assert postings[1]["title"] == "Backend Engineer"


def test_openai_parse_empty():
    scraper = OpenAIScraper()
    assert scraper.parse_response({"jobs": []}) == []


def test_openai_parse_missing_location():
    scraper = OpenAIScraper()
    data = {
        "jobs": [
            {"title": "SWE", "location": None, "jobUrl": "https://jobs.ashbyhq.com/openai/x"},
        ]
    }
    postings = scraper.parse_response(data)
    assert len(postings) == 1
    assert postings[0]["location"] == ""
