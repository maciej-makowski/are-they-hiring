import uuid
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from src.db.models import Base, JobPosting, ScrapeRun
from src.db.session import get_session_factory


async def test_create_scrape_run(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="running",
        started_at=datetime.now(UTC),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    result = await db_session.execute(select(ScrapeRun))
    runs = result.scalars().all()
    assert len(runs) == 1
    assert runs[0].company == "anthropic"
    assert runs[0].status == "running"


async def test_create_job_posting(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="openai",
        status="completed",
        started_at=datetime.now(UTC),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    posting = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="openai",
        title="Software Engineer",
        location="San Francisco",
        url="https://openai.com/careers/swe",
        first_seen_date=date.today(),
        last_seen_date=date.today(),
        is_software_engineering=True,
    )
    db_session.add(posting)
    await db_session.commit()

    result = await db_session.execute(select(JobPosting))
    postings = result.scalars().all()
    assert len(postings) == 1
    assert postings[0].title == "Software Engineer"
    assert postings[0].is_software_engineering is True


async def test_scrape_run_posting_relationship(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="deepmind",
        status="completed",
        started_at=datetime.now(UTC),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    for i in range(3):
        posting = JobPosting(
            id=uuid.uuid4(),
            scrape_run_id=run.id,
            company="deepmind",
            title=f"Engineer {i}",
            location="London",
            url=f"https://deepmind.google/careers/{i}",
            first_seen_date=date.today(),
            last_seen_date=date.today(),
        )
        db_session.add(posting)
    await db_session.commit()

    result = await db_session.execute(select(ScrapeRun).where(ScrapeRun.id == run.id))
    fetched_run = result.scalar_one()
    await db_session.refresh(fetched_run, ["postings"])
    assert len(fetched_run.postings) == 3


async def test_job_posting_dedup_constraint(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="completed",
        started_at=datetime.now(UTC),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    posting1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="Software Engineer",
        location="SF",
        url="https://anthropic.com/careers/swe",
        first_seen_date=date.today(),
        last_seen_date=date.today(),
    )
    db_session.add(posting1)
    await db_session.commit()

    posting2 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="Software Engineer v2",
        location="NYC",
        url="https://anthropic.com/careers/swe",  # same URL + company
        first_seen_date=date.today(),
        last_seen_date=date.today(),
    )
    db_session.add(posting2)
    with pytest.raises(IntegrityError):
        await db_session.commit()


async def test_get_session_factory():
    factory = get_session_factory("sqlite+aiosqlite:///:memory:")
    async with factory() as session:
        assert session is not None
        # Verify we can execute a simple query
        conn = await session.connection()
        await conn.run_sync(Base.metadata.create_all)
        run = ScrapeRun(
            company="test",
            status="running",
            started_at=datetime.now(UTC),
            attempt_number=1,
        )
        session.add(run)
        await session.commit()
        result = await session.execute(select(ScrapeRun))
        assert len(result.scalars().all()) == 1
