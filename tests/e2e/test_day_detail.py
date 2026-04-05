from datetime import date, timedelta

BASE_URL = "http://localhost:8001"


def test_day_detail_loads(page):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page.goto(f"{BASE_URL}/day/{yesterday}")
    assert page.locator(".summary h1").is_visible()


def test_day_detail_has_back_link(page):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page.goto(f"{BASE_URL}/day/{yesterday}")
    assert page.locator(".back-link").is_visible()
