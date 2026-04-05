BASE_URL = "http://localhost:8001"


def test_scrape_status_loads(page):
    page.goto(f"{BASE_URL}/scrapes")
    assert page.locator("h1").text_content() == "Scrape Run History"


def test_scrape_status_has_back_link(page):
    page.goto(f"{BASE_URL}/scrapes")
    assert page.locator(".back-link").is_visible()
