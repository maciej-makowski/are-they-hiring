"""Tests for DeepMind scraper (Greenhouse API)."""

from src.scrapers.deepmind import DeepMindScraper


def test_deepmind_parse_greenhouse_response():
    scraper = DeepMindScraper()
    data = {
        "jobs": [
            {
                "id": 7686685,
                "title": "Research Engineer, Human Understanding",
                "location": {"name": "London, UK"},
                "absolute_url": "https://job-boards.greenhouse.io/deepmind/jobs/7686685",
            },
            {
                "id": 7669433,
                "title": "Software Engineer, Infrastructure",
                "location": {"name": "Mountain View, California, US"},
                "absolute_url": "https://job-boards.greenhouse.io/deepmind/jobs/7669433",
            },
        ]
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Research Engineer, Human Understanding"
    assert postings[0]["location"] == "London, UK"
    assert "7686685" in postings[0]["url"]
    assert postings[1]["title"] == "Software Engineer, Infrastructure"


def test_deepmind_parse_empty():
    scraper = DeepMindScraper()
    assert scraper.parse_response({"jobs": []}) == []
