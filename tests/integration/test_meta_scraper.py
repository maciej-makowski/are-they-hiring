"""Tests for Meta scraper (metacareers.com GraphQL, all teams)."""

from src.scrapers.meta import MetaScraper


def test_meta_parse_graphql_response():
    scraper = MetaScraper()
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


def test_meta_parse_empty():
    scraper = MetaScraper()
    assert scraper.parse_response({"data": {"job_search": []}}) == []
    assert scraper.parse_response({}) == []
    assert scraper.parse_response([]) == []


def test_meta_parse_missing_fields():
    scraper = MetaScraper()
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


def test_meta_parse_all_teams_mixed_response():
    """After #38: Meta scraper returns roles from every team, not just AI/FAIR.

    Verifies that postings from non-AI teams (Reality Labs, Ads, Integrity,
    Software Engineering, etc.) come through unchanged. Also confirms the
    search input no longer filters by the 'Artificial Intelligence' team.
    """
    scraper = MetaScraper()
    assert scraper._search_input["teams"] == []
    assert scraper._search_input["sub_teams"] == []

    data = {
        "data": {
            "job_search": [
                {
                    "id": "100",
                    "title": "Software Engineer, Infrastructure",
                    "locations": ["Menlo Park, CA"],
                    "teams": ["Software Engineering"],
                },
                {
                    "id": "200",
                    "title": "Silicon Validation Engineer, Reality Labs",
                    "locations": ["Redmond, WA", "Sunnyvale, CA"],
                    "teams": ["Facebook Reality Labs", "AR/VR"],
                },
                {
                    "id": "300",
                    "title": "Research Engineer, Monetization AI",
                    "locations": ["New York, NY"],
                    "teams": ["Advertising Technology"],
                },
                {
                    "id": "400",
                    "title": "Offensive Security Engineer",
                    "locations": ["Remote, US"],
                    "teams": ["Security"],
                },
                {
                    "id": "500",
                    "title": "Software Engineer, Machine Learning",
                    "locations": ["Menlo Park, CA"],
                    "teams": ["Artificial Intelligence"],
                },
            ]
        }
    }
    postings = scraper.parse_response(data)

    assert len(postings) == 5
    titles = [p["title"] for p in postings]
    assert "Software Engineer, Infrastructure" in titles
    assert "Silicon Validation Engineer, Reality Labs" in titles
    assert "Research Engineer, Monetization AI" in titles
    assert "Offensive Security Engineer" in titles
    assert "Software Engineer, Machine Learning" in titles
