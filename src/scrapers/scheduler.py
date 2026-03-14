import asyncio
import logging
import uuid
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.config import settings
from src.db.models import ScrapeRun
from src.db.queries import upsert_postings
from src.db.session import get_session_factory
from src.classifier.client import classify_titles
from src.scrapers.anthropic import AnthropicScraper
from src.scrapers.openai_scraper import OpenAIScraper
from src.scrapers.deepmind import DeepMindScraper

logger = logging.getLogger(__name__)

SCRAPERS = {
    "anthropic": AnthropicScraper,
    "openai": OpenAIScraper,
    "deepmind": DeepMindScraper,
}


async def run_scrape(company: str, session_factory=None) -> ScrapeRun:
    """Run a scrape for a single company with retry logic."""
    factory = session_factory or get_session_factory()
    scraper_cls = SCRAPERS[company]
    scraper = scraper_cls()

    last_error = None
    for attempt in range(1, settings.scrape_retry_max + 1):
        scrape_run = ScrapeRun(
            id=uuid.uuid4(),
            company=company,
            status="running",
            started_at=datetime.now(timezone.utc),
            attempt_number=attempt,
        )
        async with factory() as session:
            session.add(scrape_run)
            await session.flush()

            try:
                postings = await scraper.run()

                # Classify titles
                titles = [p["title"] for p in postings]
                classifications = await classify_titles(titles)
                for p in postings:
                    p["is_software_engineering"] = classifications.get(p["title"], False)

                new_count = await upsert_postings(
                    session, scrape_run.id, company, postings
                )

                scrape_run.status = "success"
                scrape_run.finished_at = datetime.now(timezone.utc)
                scrape_run.postings_found = len(postings)
                await session.commit()

                logger.info(
                    "Scrape %s attempt %d succeeded: %d postings (%d new)",
                    company, attempt, len(postings), new_count,
                )
                return scrape_run

            except Exception as e:
                last_error = e
                scrape_run.status = "failed"
                scrape_run.finished_at = datetime.now(timezone.utc)
                scrape_run.error_message = str(e)
                await session.commit()

                logger.warning(
                    "Scrape %s attempt %d failed: %s", company, attempt, e
                )

                if attempt < settings.scrape_retry_max:
                    delay = 5 * (2 ** (attempt - 1))  # 5s, 10s, 20s
                    await asyncio.sleep(delay)

    raise last_error  # type: ignore[misc]


async def run_all_scrapes(session_factory=None) -> list[ScrapeRun]:
    """Run scrapes for all companies concurrently."""
    tasks = [
        run_scrape(company, session_factory)
        for company in SCRAPERS
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    scrape_runs = []
    for company, result in zip(SCRAPERS, results):
        if isinstance(result, Exception):
            logger.error("Scrape failed for %s: %s", company, result)
        else:
            scrape_runs.append(result)
    return scrape_runs


def create_scheduler(session_factory=None) -> AsyncIOScheduler:
    """Create APScheduler with cron jobs from settings."""
    scheduler = AsyncIOScheduler(timezone=settings.tz)

    for time_str in settings.scrape_schedule.split(","):
        hour, minute = time_str.strip().split(":")
        trigger = CronTrigger(hour=int(hour), minute=int(minute), timezone=settings.tz)
        scheduler.add_job(
            run_all_scrapes,
            trigger=trigger,
            kwargs={"session_factory": session_factory},
            id=f"scrape_{hour}_{minute}",
            name=f"Scrape all companies at {time_str.strip()}",
            replace_existing=True,
        )

    return scheduler


async def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("Starting scrape scheduler...")

    session_factory = get_session_factory()
    scheduler = create_scheduler(session_factory)
    scheduler.start()

    # Also run an immediate scrape
    await run_all_scrapes(session_factory)

    # Keep running for scheduled jobs
    try:
        while True:
            await asyncio.sleep(60)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
