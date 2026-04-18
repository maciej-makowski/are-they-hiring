import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.db.models import JobPosting, ScrapeRun
from src.web.app import create_app


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
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.combine(target_date, datetime.min.time(), tzinfo=UTC),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    for i in range(count):
        db_session.add(
            JobPosting(
                id=uuid.uuid4(),
                scrape_run_id=run.id,
                company="anthropic",
                title=f"SWE {i}",
                location="SF",
                url=f"https://anthropic.com/swe-{i}",
                first_seen_date=target_date,
                last_seen_date=target_date,
                is_software_engineering=True,
            )
        )
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


async def test_home_page_unsure_state(client):
    """With no scrape runs, state should be 'unsure' not 'NO'."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "Unsure" in response.text
    assert "hero-unsure" in response.text


async def test_home_page_no_state(client, db_session):
    """With postings fetched today, all classified, none SWE -> 'NO'."""
    today = date.today()
    for company in ["anthropic", "openai"]:
        run = ScrapeRun(
            id=uuid.uuid4(),
            company=company,
            status="success",
            started_at=datetime.now(UTC),
            attempt_number=1,
            postings_found=1,
        )
        db_session.add(run)
        await db_session.flush()
        db_session.add(
            JobPosting(
                id=uuid.uuid4(),
                scrape_run_id=run.id,
                company=company,
                title="Product Manager",
                location="SF",
                url=f"https://{company}.com/pm",
                first_seen_date=today,
                last_seen_date=today,
                is_software_engineering=False,
                classified_at=datetime.now(UTC),
            )
        )
    await db_session.commit()
    response = await client.get("/")
    assert response.status_code == 200
    assert "NO" in response.text
    assert "hero-no" in response.text


async def test_home_page_classifying_state(client, db_session):
    """With postings fetched today but some unclassified -> 'classifying'."""
    today = date.today()
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.now(UTC),
        attempt_number=1,
        postings_found=2,
    )
    db_session.add(run)
    await db_session.flush()
    # One classified, one not
    db_session.add(
        JobPosting(
            id=uuid.uuid4(),
            scrape_run_id=run.id,
            company="anthropic",
            title="Marketing",
            location="SF",
            url="https://anthropic.com/mkt",
            first_seen_date=today,
            last_seen_date=today,
            is_software_engineering=False,
            classified_at=datetime.now(UTC),
        )
    )
    db_session.add(
        JobPosting(
            id=uuid.uuid4(),
            scrape_run_id=run.id,
            company="anthropic",
            title="Not yet classified",
            location="SF",
            url="https://anthropic.com/pending",
            first_seen_date=today,
            last_seen_date=today,
            is_software_engineering=False,
            classified_at=None,
        )
    )
    await db_session.commit()
    response = await client.get("/")
    assert response.status_code == 200
    assert "hero-classifying" in response.text
    assert "classifying" in response.text.lower()
    assert "1/2 classified" in response.text


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


async def test_day_detail_no_scrape(client):
    """Day with no scrape data should show amber 'no scraping' message."""
    target = date(2020, 1, 1)
    response = await client.get(f"/day/{target.isoformat()}")
    assert response.status_code == 200
    assert "No scraping was performed" in response.text


async def test_day_detail_scraped_no_postings(client, db_session):
    """Day with scrapes but 0 SWE postings should show red warning."""
    target = date.today() - timedelta(days=2)
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
        attempt_number=1,
        postings_found=0,
    )
    db_session.add(run)
    await db_session.commit()
    response = await client.get(f"/day/{target.isoformat()}")
    assert response.status_code == 200
    assert "no software engineering postings were found" in response.text


async def test_scrape_status_page(client, db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC) + timedelta(seconds=5),
        postings_found=12,
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    response = await client.get("/scrapes")
    assert response.status_code == 200
    assert "Scrape Run History" in response.text
    assert "anthropic" in response.text.lower()
    assert "12" in response.text
    assert "success" in response.text


async def test_scrape_status_shows_errors(client, db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="openai",
        status="failed",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC) + timedelta(seconds=2),
        error_message="Connection timed out after 30s",
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    response = await client.get("/scrapes")
    assert response.status_code == 200
    assert "failed" in response.text
    assert "Connection timed out after 30s" in response.text
