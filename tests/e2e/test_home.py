BASE_URL = "http://localhost:8001"

def test_home_page_loads(page):
    page.goto(BASE_URL)
    assert page.title() == "Are They Still Hiring Software Engineers?"

def test_home_shows_yes_or_no(page):
    page.goto(BASE_URL)
    answer = page.locator(".answer")
    text = answer.text_content()
    assert text in ("YES", "NO")

def test_home_shows_counter(page):
    page.goto(BASE_URL)
    counter = page.locator(".counter")
    assert "months" in counter.text_content()

def test_home_has_chart(page):
    page.goto(BASE_URL)
    assert page.locator("#postsChart").is_visible()

def test_home_has_scrape_status_link(page):
    page.goto(BASE_URL)
    link = page.locator(".scrapes-btn")
    assert link.is_visible()
