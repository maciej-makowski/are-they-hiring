"""Tests for Meta AI scraper (metacareers.com GraphQL)."""

from src.scrapers.meta_ai import MetaAIScraper


def test_meta_ai_parse_graphql_response():
    scraper = MetaAIScraper()
    data = {
        "data": {
            "job_search": [
                {
                    "id": "1436181490732782",
                    "title": "Software Engineer, Machine Learning",
                    "locations": ["Menlo Park, CA", "New York, NY", "Remote, US"],
                    "teams": ["Artificial Intelligence"],
                },
                {
                    "id": "807341018406296",
                    "title": "Research Engineer",
                    "locations": ["Singapore"],
                    "teams": ["Artificial Intelligence"],
                },
            ]
        }
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 2
    assert postings[0]["title"] == "Software Engineer, Machine Learning"
    assert postings[0]["location"] == "Menlo Park, CA (+2 more)"
    assert postings[0]["url"] == "https://www.metacareers.com/jobs/1436181490732782/"
    assert postings[1]["title"] == "Research Engineer"
    assert postings[1]["location"] == "Singapore"


def test_meta_ai_parse_empty():
    scraper = MetaAIScraper()
    assert scraper.parse_response({"data": {"job_search": []}}) == []
    assert scraper.parse_response({}) == []
    assert scraper.parse_response([]) == []


def test_meta_ai_parse_missing_fields():
    scraper = MetaAIScraper()
    data = {
        "data": {
            "job_search": [
                {"id": "", "title": "No id", "locations": []},
                {"id": "123", "title": "", "locations": ["Menlo Park, CA"]},
                {"id": "456", "title": "Unlisted location role", "locations": None},
            ]
        }
    }
    postings = scraper.parse_response(data)
    assert len(postings) == 1
    assert postings[0]["title"] == "Unlisted location role"
    assert postings[0]["location"] == "Unlisted"
