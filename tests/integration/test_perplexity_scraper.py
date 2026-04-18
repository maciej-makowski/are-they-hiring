"""Tests for Perplexity scraper (Ashby API)."""

from src.scrapers.perplexity import PerplexityScraper


def test_perplexity_parse_ashby_response():
    scraper = PerplexityScraper()
    data = {
        "jobs": [
            {
                "id": "638e6823-be7f-46c6-9675-7b1197fc9b8c",
                "title": "Engineering Site Lead",
                "location": "London",
                "department": "Engineering",
                "jobUrl": "https://jobs.ashbyhq.com/perplexity/638e6823-be7f-46c6-9675-7b1197fc9b8c",
            },
            {
                "id": "1dc97d9e-565e-4079-9fba-40fab14a3602",
                "title": "Member of Technical Staff (iOS Software Engineer)",
                "location": "San Francisco",
                "department": "Engineering",
                "jobUrl": "https://jobs.ashbyhq.com/perplexity/1dc97d9e-565e-4079-9fba-40fab14a3602",
            },
        ]
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Engineering Site Lead"
    assert postings[0]["location"] == "London"
    assert "638e6823" in postings[0]["url"]
    assert postings[1]["title"] == "Member of Technical Staff (iOS Software Engineer)"
    assert postings[1]["location"] == "San Francisco"


def test_perplexity_parse_empty():
    scraper = PerplexityScraper()
    assert scraper.parse_response({"jobs": []}) == []


def test_perplexity_parse_missing_location():
    scraper = PerplexityScraper()
    data = {
        "jobs": [
            {
                "title": "SWE",
                "location": None,
                "jobUrl": "https://jobs.ashbyhq.com/perplexity/x",
            },
        ]
    }
    postings = scraper.parse_response(data)
    assert len(postings) == 1
    assert postings[0]["location"] == ""
