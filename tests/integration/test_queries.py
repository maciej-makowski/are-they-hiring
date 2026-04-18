import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select

from src.db.models import JobPosting, ScrapeRun
from src.db.queries import (
    get_daily_counts,
    get_postings_for_date,
    get_recent_scrape_runs,
    get_yesterday_count,
    upsert_postings,
)


async def _create_scrape_run(session, company="anthropic"):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company=company,
        status="completed",
        started_at=datetime.now(UTC),
        attempt_number=1,
    )
    session.add(run)
    await session.commit()
    return run


async def test_upsert_postings_inserts_new(db_session):
    run = await _create_scrape_run(db_session)
    postings = [
        {"title": "Software Engineer", "location": "SF", "url": "https://example.com/1"},
        {"title": "ML Engineer", "location": "NYC", "url": "https://example.com/2"},
    ]

    new_count = await upsert_postings(db_session, run.id, "anthropic", postings)
    await db_session.commit()

    assert new_count == 2
    result = await db_session.execute(select(JobPosting))
    all_postings = result.scalars().all()
    assert len(all_postings) == 2


async def test_upsert_postings_updates_existing(db_session):
    run1 = await _create_scrape_run(db_session)

    postings = [
        {"title": "Software Engineer", "location": "SF", "url": "https://example.com/1"},
    ]
    await upsert_postings(db_session, run1.id, "anthropic", postings)
    await db_session.commit()

    # Second upsert with same URL should update, not insert
    run2 = await _create_scrape_run(db_session)
    new_count = await upsert_postings(db_session, run2.id, "anthropic", postings)
    await db_session.commit()

    assert new_count == 0
    result = await db_session.execute(select(JobPosting))
    all_postings = result.scalars().all()
    assert len(all_postings) == 1
    assert all_postings[0].scrape_run_id == run2.id
    assert all_postings[0].last_seen_date == date.today()


async def test_upsert_postings_different_company_same_url(db_session):
    run1 = await _create_scrape_run(db_session, "anthropic")
    run2 = await _create_scrape_run(db_session, "openai")

    postings = [
        {"title": "Software Engineer", "location": "SF", "url": "https://example.com/1"},
    ]
    await upsert_postings(db_session, run1.id, "anthropic", postings)
    await upsert_postings(db_session, run2.id, "openai", postings)
    await db_session.commit()

    result = await db_session.execute(select(JobPosting))
    all_postings = result.scalars().all()
    assert len(all_postings) == 2  # different companies = different postings


async def test_get_postings_for_date(db_session):
    run = await _create_scrape_run(db_session)
    today = date.today()

    # Create a posting visible today
    p1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="Software Engineer",
        location="SF",
        url="https://example.com/1",
        first_seen_date=today - timedelta(days=2),
        last_seen_date=today,
        is_software_engineering=True,
    )
    # Create a posting that expired yesterday
    p2 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="ML Engineer",
        location="NYC",
        url="https://example.com/2",
        first_seen_date=today - timedelta(days=5),
        last_seen_date=today - timedelta(days=1),
        is_software_engineering=True,
    )
    # Create a non-SWE posting
    p3 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="Marketing Manager",
        location="SF",
        url="https://example.com/3",
        first_seen_date=today - timedelta(days=2),
        last_seen_date=today,
        is_software_engineering=False,
    )
    db_session.add_all([p1, p2, p3])
    await db_session.commit()

    # Today should show only p1 (p2 expired, p3 not SWE)
    postings = await get_postings_for_date(db_session, today)
    assert len(postings) == 1
    assert postings[0].title == "Software Engineer"

    # Yesterday should show p1 and p2
    postings_yesterday = await get_postings_for_date(db_session, today - timedelta(days=1))
    assert len(postings_yesterday) == 2


async def test_get_postings_for_date_with_company_filter(db_session):
    run = await _create_scrape_run(db_session)
    today = date.today()

    p1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="SWE",
        location="SF",
        url="https://anthropic.com/1",
        first_seen_date=today,
        last_seen_date=today,
        is_software_engineering=True,
    )
    p2 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="openai",
        title="SWE",
        location="SF",
        url="https://openai.com/1",
        first_seen_date=today,
        last_seen_date=today,
        is_software_engineering=True,
    )
    db_session.add_all([p1, p2])
    await db_session.commit()

    postings = await get_postings_for_date(db_session, today, company="anthropic")
    assert len(postings) == 1
    assert postings[0].company == "anthropic"


async def test_get_yesterday_count(db_session):
    run = await _create_scrape_run(db_session)
    today = date.today()
    yesterday = today - timedelta(days=1)

    p1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="SWE 1",
        location="SF",
        url="https://example.com/1",
        first_seen_date=yesterday,
        last_seen_date=today,
        is_software_engineering=True,
    )
    p2 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="openai",
        title="SWE 2",
        location="NYC",
        url="https://example.com/2",
        first_seen_date=yesterday,
        last_seen_date=yesterday,
        is_software_engineering=True,
    )
    # Not SWE - should not count
    p3 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="Recruiter",
        location="SF",
        url="https://example.com/3",
        first_seen_date=yesterday,
        last_seen_date=yesterday,
        is_software_engineering=False,
    )
    db_session.add_all([p1, p2, p3])
    await db_session.commit()

    count = await get_yesterday_count(db_session)
    assert count == 2


async def test_get_yesterday_count_zero(db_session):
    count = await get_yesterday_count(db_session)
    assert count == 0


async def test_get_daily_counts(db_session):
    run = await _create_scrape_run(db_session)
    today = date.today()

    # Posting visible for 3 days
    p1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="SWE",
        location="SF",
        url="https://example.com/1",
        first_seen_date=today - timedelta(days=2),
        last_seen_date=today,
        is_software_engineering=True,
    )
    db_session.add(p1)
    await db_session.commit()

    counts = await get_daily_counts(db_session, days=5)
    assert len(counts) == 5
    # Last 3 days should have count 1, first 2 should have 0
    assert counts[0]["count"] == 0
    assert counts[1]["count"] == 0
    assert counts[2]["count"] == 1
    assert counts[3]["count"] == 1
    assert counts[4]["count"] == 1
    # Dates should be ascending
    assert counts[0]["date"] < counts[4]["date"]
    # Each entry should have 'scraped' and 'classifying' keys
    assert all("scraped" in c for c in counts)
    assert all("classifying" in c for c in counts)


async def test_get_recent_scrape_runs(db_session):
    for i in range(5):
        run = ScrapeRun(
            id=uuid.uuid4(),
            company="anthropic",
            status="completed",
            started_at=datetime(2025, 1, 1, i, 0, 0, tzinfo=UTC),
            attempt_number=1,
        )
        db_session.add(run)
    await db_session.commit()

    runs = await get_recent_scrape_runs(db_session, limit=3)
    assert len(runs) == 3
    # Should be ordered by started_at descending
    # Compare hour values since SQLite may strip timezone info
    assert runs[0].started_at.hour > runs[1].started_at.hour
    assert runs[1].started_at.hour > runs[2].started_at.hour


async def test_get_recent_scrape_runs_empty(db_session):
    runs = await get_recent_scrape_runs(db_session)
    assert len(runs) == 0
