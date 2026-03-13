import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import JobPosting, ScrapeRun


async def upsert_postings(
    session: AsyncSession,
    scrape_run_id: uuid.UUID,
    company: str,
    postings: list[dict],
) -> int:
    """Insert new postings or update last_seen_date for existing ones.

    Each posting dict should have: title, location, url.
    Returns the number of new postings inserted.
    """
    today = date.today()
    new_count = 0

    for p in postings:
        result = await session.execute(
            select(JobPosting).where(
                JobPosting.company == company,
                JobPosting.url == p["url"],
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.last_seen_date = today
            existing.scrape_run_id = scrape_run_id
        else:
            posting = JobPosting(
                id=uuid.uuid4(),
                scrape_run_id=scrape_run_id,
                company=company,
                title=p["title"],
                location=p["location"],
                url=p["url"],
                first_seen_date=today,
                last_seen_date=today,
                is_software_engineering=p.get("is_software_engineering", False),
            )
            session.add(posting)
            new_count += 1

    await session.flush()
    return new_count


async def get_daily_counts(
    session: AsyncSession,
    days: int = 30,
) -> list[dict]:
    """Get posting counts per day for the last N days.

    Returns list of dicts with 'date' and 'count' keys, ordered by date ascending.
    A posting is counted on a day if first_seen_date <= day <= last_seen_date.
    """
    today = date.today()
    results = []

    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        result = await session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.first_seen_date <= d,
                JobPosting.last_seen_date >= d,
                JobPosting.is_software_engineering == True,
            )
        )
        count = result.scalar()
        results.append({"date": d, "count": count})

    return results


async def get_postings_for_date(
    session: AsyncSession,
    target_date: date,
    company: str | None = None,
) -> list[JobPosting]:
    """Get all software engineering postings visible on a given date."""
    stmt = select(JobPosting).where(
        JobPosting.first_seen_date <= target_date,
        JobPosting.last_seen_date >= target_date,
        JobPosting.is_software_engineering == True,
    )
    if company:
        stmt = stmt.where(JobPosting.company == company)
    stmt = stmt.order_by(JobPosting.company, JobPosting.title)

    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_yesterday_count(session: AsyncSession) -> int:
    """Get total software engineering posting count for yesterday."""
    yesterday = date.today() - timedelta(days=1)
    result = await session.execute(
        select(func.count(JobPosting.id)).where(
            JobPosting.first_seen_date <= yesterday,
            JobPosting.last_seen_date >= yesterday,
            JobPosting.is_software_engineering == True,
        )
    )
    return result.scalar() or 0


async def get_recent_scrape_runs(
    session: AsyncSession,
    limit: int = 50,
) -> list[ScrapeRun]:
    """Get the most recent scrape runs, ordered by started_at descending."""
    result = await session.execute(
        select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit)
    )
    return list(result.scalars().all())
