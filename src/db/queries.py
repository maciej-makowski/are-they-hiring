import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
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
    """Get posting counts and scrape status per day for the last N days.

    Returns list of dicts ordered by date ascending:
      - date: the date
      - count: number of SWE postings active on that day
      - scraped: whether at least one successful scrape ran that day
      - classifying: postings active on this day have classified_at IS NULL
    """
    today = date.today()
    results = []

    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)

        # Count SWE postings active on this day
        count_result = await session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.first_seen_date <= d,
                JobPosting.last_seen_date >= d,
                JobPosting.is_software_engineering == True,
            )
        )
        count = count_result.scalar()

        # Count unclassified postings active on this day
        unclassified_result = await session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.first_seen_date <= d,
                JobPosting.last_seen_date >= d,
                JobPosting.classified_at.is_(None),
            )
        )
        classifying = (unclassified_result.scalar() or 0) > 0

        # Check if any successful scrape ran on this day
        day_start = datetime.combine(d, datetime.min.time(), tzinfo=UTC)
        day_end = datetime.combine(d + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
        scrape_result = await session.execute(
            select(func.count(ScrapeRun.id)).where(
                ScrapeRun.status == "success",
                ScrapeRun.started_at >= day_start,
                ScrapeRun.started_at < day_end,
            )
        )
        scraped = (scrape_result.scalar() or 0) > 0

        results.append({"date": d, "count": count, "scraped": scraped, "classifying": classifying})

    return results


async def get_unclassified_count_for_date(session: AsyncSession, target_date: date) -> int:
    """Count postings active on target_date that haven't been classified yet."""
    result = await session.execute(
        select(func.count(JobPosting.id)).where(
            JobPosting.first_seen_date <= target_date,
            JobPosting.last_seen_date >= target_date,
            JobPosting.classified_at.is_(None),
        )
    )
    return result.scalar() or 0


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


async def get_scrape_runs_for_date(session: AsyncSession, target_date: date) -> list[ScrapeRun]:
    """Get all scrape runs that started on a given date."""
    day_start = datetime.combine(target_date, datetime.min.time(), tzinfo=UTC)
    day_end = datetime.combine(target_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    result = await session.execute(
        select(ScrapeRun)
        .where(ScrapeRun.started_at >= day_start, ScrapeRun.started_at < day_end)
        .order_by(ScrapeRun.started_at.desc())
    )
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
    result = await session.execute(select(ScrapeRun).order_by(ScrapeRun.started_at.desc()).limit(limit))
    return list(result.scalars().all())


async def get_todays_scrape_summary(session: AsyncSession) -> dict:
    """Get summary of today's scrape runs for determining home page state.

    Returns dict with:
      - succeeded: number of companies with successful scrapes today
      - running: number of companies with running scrapes
      - failed: number of companies with only failed scrapes today
      - total_companies: number of registered company scrapers
      - has_postings: whether any successful scrape found SWE postings
    """
    # Import here to avoid a circular import between queries and the scraper registry.
    from src.scrapers.scheduler import SCRAPERS

    today_start = datetime.combine(date.today(), datetime.min.time(), tzinfo=UTC)
    companies = list(SCRAPERS.keys())

    succeeded = 0
    running = 0
    failed = 0

    for company in companies:
        # Get the latest run for this company today
        result = await session.execute(
            select(ScrapeRun)
            .where(ScrapeRun.company == company, ScrapeRun.started_at >= today_start)
            .order_by(ScrapeRun.started_at.desc())
            .limit(1)
        )
        latest = result.scalar_one_or_none()
        if latest is None:
            pass  # no run today — counts as neither
        elif latest.status == "success":
            succeeded += 1
        elif latest.status == "running":
            running += 1
        else:
            failed += 1

    # Check for SWE postings visible today OR yesterday (use the most recent data)
    today = date.today()
    yesterday = today - timedelta(days=1)
    for check_date in [today, yesterday]:
        result = await session.execute(
            select(func.count(JobPosting.id)).where(
                JobPosting.first_seen_date <= check_date,
                JobPosting.last_seen_date >= check_date,
                JobPosting.is_software_engineering == True,
            )
        )
        count = result.scalar() or 0
        if count > 0:
            break

    # Classification stats for postings active today
    active_today_stmt = select(func.count(JobPosting.id)).where(
        JobPosting.first_seen_date <= today,
        JobPosting.last_seen_date >= today,
    )
    active_today_result = await session.execute(active_today_stmt)
    active_today_total = active_today_result.scalar() or 0

    unclassified_today_result = await session.execute(active_today_stmt.where(JobPosting.classified_at.is_(None)))
    unclassified_today = unclassified_today_result.scalar() or 0
    classified_today = active_today_total - unclassified_today

    return {
        "succeeded": succeeded,
        "running": running,
        "failed": failed,
        "total_companies": len(companies),
        "has_postings": count > 0,
        "posting_count": count,
        "active_today_total": active_today_total,
        "classified_today": classified_today,
        "unclassified_today": unclassified_today,
    }
