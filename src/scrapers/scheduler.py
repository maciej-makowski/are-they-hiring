import asyncio
import logging
import uuid
from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from src.classifier.client import classify_titles
from src.config import settings
from src.db.models import JobPosting, ScrapeRun
from src.db.queries import upsert_postings
from src.db.session import get_session_factory
from src.scrapers.anthropic import AnthropicScraper
from src.scrapers.deepmind import DeepMindScraper
from src.scrapers.meta import MetaScraper
from src.scrapers.openai_scraper import OpenAIScraper
from src.scrapers.perplexity import PerplexityScraper
from src.scrapers.xai import XAIScraper

logger = logging.getLogger(__name__)

SCRAPERS = {
    "anthropic": AnthropicScraper,
    "openai": OpenAIScraper,
    "deepmind": DeepMindScraper,
    "xai": XAIScraper,
    "perplexity": PerplexityScraper,
    "meta": MetaScraper,
}


async def fetch_and_save(company: str, session_factory=None) -> ScrapeRun:
    """Stage 1: Fetch postings from API and save to DB (no classification)."""
    factory = session_factory or get_session_factory()
    scraper_cls = SCRAPERS[company]
    scraper = scraper_cls()

    last_error = None
    for attempt in range(1, settings.scrape_retry_max + 1):
        scrape_run = ScrapeRun(
            id=uuid.uuid4(),
            company=company,
            status="running",
            started_at=datetime.now(UTC),
            attempt_number=attempt,
            stage="fetching",
            progress_current=0,
            progress_total=1,
        )
        async with factory() as session:
            session.add(scrape_run)
            await session.flush()
            await session.commit()

            try:
                postings = await scraper.run()

                scrape_run.stage = "saving"
                scrape_run.progress_current = 0
                scrape_run.progress_total = len(postings)
                await session.commit()

                new_count = await upsert_postings(session, scrape_run.id, company, postings)

                scrape_run.stage = None
                scrape_run.progress_current = None
                scrape_run.progress_total = None
                scrape_run.status = "success"
                scrape_run.finished_at = datetime.now(UTC)
                scrape_run.postings_found = len(postings)
                await session.commit()

                logger.info(
                    "Fetch %s attempt %d: %d postings (%d new)",
                    company,
                    attempt,
                    len(postings),
                    new_count,
                )
                return scrape_run

            except Exception as e:
                last_error = e
                scrape_run.stage = None
                scrape_run.status = "failed"
                scrape_run.finished_at = datetime.now(UTC)
                scrape_run.error_message = str(e)
                await session.commit()

                logger.warning("Fetch %s attempt %d failed: %s", company, attempt, e)

                if attempt < settings.scrape_retry_max:
                    delay = 5 * (2 ** (attempt - 1))
                    await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


async def classify_postings(
    company: str | None = None,
    session_factory=None,
    force: bool = False,
) -> int:
    """Stage 2: Classify postings via Ollama. Can be run independently.

    Args:
        company: Classify only this company's postings (None = all).
        session_factory: DB session factory.
        force: If True, reclassify all postings. If False, only unclassified ones.

    Returns number of postings classified.
    Returns 0 without any work if settings.classify_enabled is False.
    """
    if not settings.classify_enabled:
        logger.info("Classification disabled (CLASSIFY_ENABLED=false); skipping.")
        return 0

    factory = session_factory or get_session_factory()
    now = datetime.now(UTC)

    async with factory() as session:
        stmt = select(JobPosting)
        if company:
            stmt = stmt.where(JobPosting.company == company)
        if not force:
            stmt = stmt.where(JobPosting.classified_at.is_(None))

        result = await session.execute(stmt.order_by(JobPosting.company, JobPosting.title))
        postings = list(result.scalars().all())

        if not postings:
            logger.info("No postings to classify%s", f" for {company}" if company else "")
            return 0

        titles = list({p.title for p in postings})  # dedupe titles
        logger.info("Classifying %d unique titles (%d postings)...", len(titles), len(postings))

        async def on_progress(current: int, total: int):
            if current % 50 == 0 or current == total:
                logger.info("Classification progress: %d/%d", current, total)

        classifications = await classify_titles(titles, on_progress=on_progress)

        # Apply classifications
        classified = 0
        for posting in postings:
            new_val = classifications.get(posting.title, False)
            if posting.is_software_engineering != new_val or force:
                posting.is_software_engineering = new_val
                classified += 1
            posting.classified_at = now

        await session.commit()
        logger.info("Classified %d postings (%d changed)", len(postings), classified)
        return classified


async def fetch_all(session_factory=None) -> list[ScrapeRun]:
    """Fetch postings from all companies concurrently."""
    tasks = [fetch_and_save(company, session_factory) for company in SCRAPERS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scrape_runs = []
    for company, result in zip(SCRAPERS, results, strict=False):
        if isinstance(result, Exception):
            logger.error("Fetch failed for %s: %s", company, result)
        else:
            scrape_runs.append(result)
    return scrape_runs


async def run_full_pipeline(session_factory=None) -> None:
    """Run the full pipeline: fetch all companies, then classify."""
    await fetch_all(session_factory)
    await classify_postings(session_factory=session_factory)


def create_scheduler(session_factory=None) -> AsyncIOScheduler:
    """Create APScheduler with cron jobs from settings."""
    scheduler = AsyncIOScheduler(timezone=settings.tz)

    for time_str in settings.scrape_schedule.split(","):
        hour, minute = time_str.strip().split(":")
        trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=settings.tz)
        scheduler.add_job(
            run_full_pipeline,
            trigger=trigger,
            kwargs={"session_factory": session_factory},
            id=f"scrape_{hour}_{minute}",
            name=f"Scrape all companies at {time_str.strip()}",
            replace_existing=True,
        )

    return scheduler


async def main():
    import sys

    logging.basicConfig(level=logging.INFO)

    # CLI commands: fetch, classify, reclassify, or default (full pipeline + scheduler)
    command = sys.argv[1] if len(sys.argv) > 1 else "run"
    company = sys.argv[2] if len(sys.argv) > 2 else None

    session_factory = get_session_factory()

    if command == "fetch":
        if company:
            await fetch_and_save(company, session_factory)
        else:
            await fetch_all(session_factory)

    elif command == "classify":
        await classify_postings(company=company, session_factory=session_factory)

    elif command == "reclassify":
        await classify_postings(company=company, session_factory=session_factory, force=True)

    elif command == "run":
        logger.info("Starting scrape scheduler...")
        scheduler = create_scheduler(session_factory)
        scheduler.start()

        # Run full pipeline immediately
        await run_full_pipeline(session_factory)

        # Keep running for scheduled jobs
        try:
            while True:
                await asyncio.sleep(60)
        except KeyboardInterrupt, SystemExit:
            scheduler.shutdown()
    else:
        print("Usage: python -m src.scrapers.scheduler [fetch|classify|reclassify|run] [company]")
        print("  fetch [company]       - Fetch postings (all companies or specific one)")
        print("  classify [company]    - Classify unclassified postings")
        print("  reclassify [company]  - Reclassify ALL postings (force)")
        print("  run                   - Full pipeline + scheduler (default)")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
