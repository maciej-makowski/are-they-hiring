import pytest
import uuid
from datetime import datetime, timezone, date, timedelta
from httpx import AsyncClient, ASGITransport
from src.web.app import create_app
from src.db.models import ScrapeRun, JobPosting


@pytest.fixture
def app(db_session):
    return create_app(db_session_override=db_session)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _seed_postings(db_session, target_date: date, count: int = 3):
    run = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    for i in range(count):
        db_session.add(JobPosting(
            id=uuid.uuid4(), scrape_run_id=run.id, company="anthropic",
            title=f"SWE {i}", location="SF", url=f"https://anthropic.com/swe-{i}",
            first_seen_date=target_date, last_seen_date=target_date,
            is_software_engineering=True,
        ))
    await db_session.commit()
    return run


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_home_page_yes_state(client, db_session):
    yesterday = date.today() - timedelta(days=1)
    await _seed_postings(db_session, yesterday, count=3)
    response = await client.get("/")
    assert response.status_code == 200
    assert "YES" in response.text
    assert "hero-yes" in response.text


async def test_home_page_no_state(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "NO" in response.text
    assert "hero-no" in response.text


async def test_day_detail_page(client, db_session):
    target = date.today() - timedelta(days=1)
    await _seed_postings(db_session, target, count=3)
    response = await client.get(f"/day/{target.isoformat()}")
    assert response.status_code == 200
    assert target.strftime("%B %d, %Y") in response.text
    assert "SWE 0" in response.text
    assert "SWE 1" in response.text
    assert "SWE 2" in response.text
    assert "3 posting" in response.text


async def test_day_detail_empty(client):
    target = date(2020, 1, 1)
    response = await client.get(f"/day/{target.isoformat()}")
    assert response.status_code == 200
    assert "0 software engineering posting" in response.text
