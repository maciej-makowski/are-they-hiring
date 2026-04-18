"""Integration tests for nuanced UI state combinations on the home page and day detail.

Covers roadmap item #20 — ensures rendered HTML reflects the correct state for every
combination of scrape status, classification progress, and posting data. Assertions
target specific CSS classes / text snippets rather than full HTML snapshots so the
tests stay maintainable as styling evolves.
"""

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from src.db.models import JobPosting, ScrapeRun
from src.scrapers.scheduler import SCRAPERS
from src.web.app import create_app

COMPANIES = tuple(SCRAPERS.keys())
TOTAL_COMPANIES = len(COMPANIES)


# --- fixtures / factories --------------------------------------------------


@pytest.fixture
def app(db_session):
    return create_app(db_session_override=db_session)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_scrape_run(
    company: str,
    status: str,
    started_at: datetime | None = None,
    *,
    postings_found: int | None = None,
    error_message: str | None = None,
    finished_at: datetime | None = None,
) -> ScrapeRun:
    return ScrapeRun(
        id=uuid.uuid4(),
        company=company,
        status=status,
        started_at=started_at or datetime.now(UTC),
        finished_at=finished_at,
        error_message=error_message,
        postings_found=postings_found,
        attempt_number=1,
    )


def _make_posting(
    *,
    company: str,
    title: str,
    first_seen: date,
    last_seen: date,
    is_swe: bool,
    classified: bool,
    scrape_run_id: uuid.UUID,
    url: str | None = None,
) -> JobPosting:
    return JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=scrape_run_id,
        company=company,
        title=title,
        location="Remote",
        url=url or f"https://{company}.example.com/{uuid.uuid4()}",
        first_seen_date=first_seen,
        last_seen_date=last_seen,
        is_software_engineering=is_swe,
        classified_at=datetime.now(UTC) if classified else None,
    )


async def _seed_run_with_postings(
    db_session,
    *,
    company: str,
    status: str = "success",
    postings: list[dict] | None = None,
    started_at: datetime | None = None,
) -> ScrapeRun:
    """Seed a scrape run and optional postings in one shot."""
    run = _make_scrape_run(
        company,
        status,
        started_at=started_at,
        postings_found=len(postings) if postings else None,
    )
    db_session.add(run)
    await db_session.flush()
    if postings:
        for p in postings:
            db_session.add(
                _make_posting(
                    company=company,
                    scrape_run_id=run.id,
                    title=p["title"],
                    first_seen=p.get("first_seen", date.today()),
                    last_seen=p.get("last_seen", date.today()),
                    is_swe=p.get("is_swe", True),
                    classified=p.get("classified", True),
                    url=p.get("url"),
                )
            )
    await db_session.commit()
    return run


# --- hero state tests ------------------------------------------------------


class TestHeroYes:
    async def test_hero_yes_when_classified_swe_postings_today(self, client, db_session):
        """A successful scrape today with a classified SWE posting -> hero-yes."""
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            postings=[{"title": "Senior Software Engineer", "is_swe": True, "classified": True}],
        )
        response = await client.get("/")
        assert response.status_code == 200
        assert 'class="hero hero-yes"' in response.text
        assert ">YES<" in response.text
        assert "1 software engineering positions found" in response.text

    async def test_hero_yes_when_swe_postings_from_yesterday(self, client, db_session):
        """Postings from yesterday still count towards hero-yes (get_todays_scrape_summary fallback)."""
        yesterday = date.today() - timedelta(days=1)
        await _seed_run_with_postings(
            db_session,
            company="openai",
            started_at=datetime.combine(yesterday, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Staff SWE",
                    "first_seen": yesterday,
                    "last_seen": yesterday,
                    "is_swe": True,
                    "classified": True,
                }
            ],
        )
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-yes" in response.text
        assert ">YES<" in response.text


class TestHeroNo:
    async def test_hero_no_when_all_classified_but_none_swe(self, client, db_session):
        """All companies finished, every posting classified, none are SWE -> hero-no."""
        for company in COMPANIES:
            await _seed_run_with_postings(
                db_session,
                company=company,
                postings=[{"title": "Recruiter", "is_swe": False, "classified": True}],
            )
        response = await client.get("/")
        assert response.status_code == 200
        assert 'class="hero hero-no"' in response.text
        assert ">NO<" in response.text
        assert "No software engineering positions found" in response.text
        assert "siren" in response.text  # the alarm visual

    async def test_hero_no_with_two_successful_scrapers(self, client, db_session):
        """Only two scrapers need to succeed to move from unsure -> no (threshold is >=2)."""
        for company in ("anthropic", "openai"):
            await _seed_run_with_postings(
                db_session,
                company=company,
                postings=[{"title": "Marketing", "is_swe": False, "classified": True}],
            )
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-no" in response.text


class TestHeroClassifying:
    async def test_hero_classifying_when_some_postings_pending(self, client, db_session):
        """Scrape succeeded but some postings haven't been classified yet -> hero-classifying."""
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            postings=[
                {"title": "Marketing", "is_swe": False, "classified": True},
                {"title": "Unclassified role", "is_swe": False, "classified": False},
            ],
        )
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-classifying" in response.text
        # The template emits the literal "Still checking — classifying today's postings" tagline.
        assert "Still checking" in response.text
        assert "classifying today" in response.text
        assert "1/2 classified" in response.text
        assert "1 remaining" in response.text

    async def test_hero_classifying_when_nothing_classified_yet(self, client, db_session):
        """Scrape succeeded but nothing classified -> hero-classifying (0/N classified)."""
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            postings=[
                {"title": "A", "is_swe": False, "classified": False},
                {"title": "B", "is_swe": False, "classified": False},
                {"title": "C", "is_swe": False, "classified": False},
            ],
        )
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-classifying" in response.text
        assert "0/3 classified" in response.text
        assert "3 remaining" in response.text


class TestHeroUnsure:
    async def test_hero_unsure_when_no_scrape_runs(self, client):
        """No scrape runs in the DB -> hero-unsure."""
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-unsure" in response.text
        assert "Unsure yet, still checking" in response.text
        assert f"0/{TOTAL_COMPANIES} scrapers finished" in response.text

    async def test_hero_unsure_while_scrapers_running(self, client, db_session):
        """Scrapers still running, no postings yet -> hero-unsure with 'running' badge."""
        for company in COMPANIES:
            db_session.add(_make_scrape_run(company, "running"))
        await db_session.commit()
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-unsure" in response.text
        assert f"0/{TOTAL_COMPANIES} scrapers finished" in response.text
        assert f"{TOTAL_COMPANIES} running" in response.text

    async def test_hero_unsure_when_only_one_scraper_succeeded(self, client, db_session):
        """One success isn't enough to claim 'NO' — still unsure."""
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            postings=[{"title": "Marketing", "is_swe": False, "classified": True}],
        )
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-unsure" in response.text
        assert f"1/{TOTAL_COMPANIES} scrapers finished" in response.text

    async def test_hero_unsure_when_all_scrapers_failed(self, client, db_session):
        """Every scraper failed -> hero-unsure with N-failed indicator."""
        for company in COMPANIES:
            db_session.add(
                _make_scrape_run(
                    company,
                    "failed",
                    error_message="boom",
                    finished_at=datetime.now(UTC),
                )
            )
        await db_session.commit()
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-unsure" in response.text
        assert "Unsure yet, still checking" in response.text
        assert f"{TOTAL_COMPANIES} failed" in response.text
        assert f"0/{TOTAL_COMPANIES} scrapers finished" in response.text

    async def test_hero_unsure_mixed_company_states(self, client, db_session):
        """One succeeded, one failed, one running -> still unsure, badges reflect mix."""
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            postings=[{"title": "Marketing", "is_swe": False, "classified": True}],
        )
        db_session.add(
            _make_scrape_run(
                "openai",
                "failed",
                error_message="timeout",
                finished_at=datetime.now(UTC),
            )
        )
        db_session.add(_make_scrape_run("deepmind", "running"))
        await db_session.commit()
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-unsure" in response.text
        assert f"1/{TOTAL_COMPANIES} scrapers finished" in response.text
        assert "1 running" in response.text
        assert "1 failed" in response.text


# --- calendar day tests ----------------------------------------------------


class TestCalendarDayVariants:
    async def test_calendar_day_green_for_day_with_swe_postings(self, client, db_session):
        """A past day with a classified SWE posting -> day-green + tick mark + count."""
        target = date.today() - timedelta(days=3)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Software Engineer",
                    "first_seen": target,
                    "last_seen": target,
                    "is_swe": True,
                    "classified": True,
                }
            ],
        )
        response = await client.get("/")
        assert response.status_code == 200
        # Find the calendar anchor for the target day
        href = f"/day/{target.isoformat()}"
        assert href in response.text
        # The day's anchor should include day-green (and not day-red/amber/classifying)
        snippet = _extract_day_cell(response.text, target)
        assert "day-green" in snippet
        assert "day-red" not in snippet
        assert "day-amber" not in snippet
        assert "day-classifying" not in snippet

    async def test_calendar_day_red_when_scraped_but_no_swe(self, client, db_session):
        """Past day with a successful scrape but no SWE postings -> day-red."""
        target = date.today() - timedelta(days=2)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Recruiter",
                    "first_seen": target,
                    "last_seen": target,
                    "is_swe": False,
                    "classified": True,
                }
            ],
        )
        response = await client.get("/")
        snippet = _extract_day_cell(response.text, target)
        assert "day-red" in snippet
        assert "day-green" not in snippet

    async def test_calendar_day_amber_when_never_scraped(self, client, db_session):
        """Past day with no scrape data at all -> day-amber."""
        target = date.today() - timedelta(days=5)
        # Seed a posting on a *different* day so the DB isn't empty
        other = date.today() - timedelta(days=1)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(other, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "SWE",
                    "first_seen": other,
                    "last_seen": other,
                    "is_swe": True,
                    "classified": True,
                }
            ],
        )
        response = await client.get("/")
        snippet = _extract_day_cell(response.text, target)
        assert "day-amber" in snippet

    async def test_calendar_day_classifying_when_scraped_but_unclassified(self, client, db_session):
        """Past day with a successful scrape but postings still pending classification -> day-classifying."""
        target = date.today() - timedelta(days=4)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Pending classification",
                    "first_seen": target,
                    "last_seen": target,
                    "is_swe": False,
                    "classified": False,
                },
            ],
        )
        response = await client.get("/")
        snippet = _extract_day_cell(response.text, target)
        assert "day-classifying" in snippet
        # spinner is shown in place of a check/warning
        assert "spinner" in snippet

    async def test_calendar_day_count_only_rendered_for_green(self, client, db_session):
        """Count badge is only shown on green (scraped, classified, >0 SWE postings)."""
        today = date.today()
        # Day with 5 SWE postings (classified)
        target_green = today - timedelta(days=2)
        run_green = _make_scrape_run(
            "anthropic",
            "success",
            started_at=datetime.combine(target_green, datetime.min.time(), tzinfo=UTC),
        )
        db_session.add(run_green)
        await db_session.flush()
        for i in range(5):
            db_session.add(
                _make_posting(
                    company="anthropic",
                    scrape_run_id=run_green.id,
                    title=f"SWE {i}",
                    first_seen=target_green,
                    last_seen=target_green,
                    is_swe=True,
                    classified=True,
                    url=f"https://anthropic.example.com/swe-{i}",
                )
            )
        await db_session.commit()
        response = await client.get("/")
        snippet = _extract_day_cell(response.text, target_green)
        assert "day-green" in snippet
        assert 'class="day-count">5<' in snippet


# --- failure-mode and edge-case tests --------------------------------------


class TestFailureModes:
    async def test_partial_classification_across_companies(self, client, db_session):
        """Some companies fully classified, one still pending -> hero-classifying.

        anthropic: fully classified, no SWE. openai: fully classified, no SWE.
        deepmind: one classified, one still pending.
        """
        for company in ("anthropic", "openai"):
            await _seed_run_with_postings(
                db_session,
                company=company,
                postings=[{"title": "Marketing", "is_swe": False, "classified": True}],
            )
        await _seed_run_with_postings(
            db_session,
            company="deepmind",
            postings=[
                {"title": "Already classified", "is_swe": False, "classified": True},
                {"title": "Pending", "is_swe": False, "classified": False},
            ],
        )
        response = await client.get("/")
        assert "hero-classifying" in response.text
        # 3 classified out of 4 active postings
        assert "3/4 classified" in response.text

    async def test_scrape_found_postings_but_zero_after_dedup(self, client, db_session):
        """scrape_runs.postings_found > 0 but no JobPosting rows inserted (all were duplicates).

        The home state derives "no" from active_today_total > 0, so a dedup-wipes-everything
        scrape leaves us in `hero-unsure` — we can't prove there are zero SWE roles when no
        postings are in the DB for today. This locks that behaviour in so a future refactor
        doesn't accidentally promote this to "hero-no".
        """
        run = _make_scrape_run("anthropic", "success", postings_found=12)
        db_session.add(run)
        db_session.add(_make_scrape_run("openai", "success", postings_found=10))
        await db_session.commit()
        response = await client.get("/")
        assert response.status_code == 200
        # With no JobPosting rows active today, we stay unsure even though scrapes succeeded.
        assert "hero-unsure" in response.text
        assert f"2/{TOTAL_COMPANIES} scrapers finished" in response.text
        # /scrapes still reflects the raw postings_found value (surfacing dedup activity).
        scrapes = await client.get("/scrapes")
        assert scrapes.status_code == 200
        assert "12" in scrapes.text
        assert "10" in scrapes.text

    async def test_stale_postings_beyond_calendar_window_not_shown(self, client, db_session):
        """A SWE posting whose last_seen_date is older than 30 days must not appear on the calendar."""
        stale = date.today() - timedelta(days=45)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(stale, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Old SWE role",
                    "first_seen": stale,
                    "last_seen": stale,
                    "is_swe": True,
                    "classified": True,
                }
            ],
        )
        response = await client.get("/")
        assert response.status_code == 200
        # No calendar anchor points to that stale date
        assert f"/day/{stale.isoformat()}" not in response.text
        # And the hero shouldn't light up green from stale data
        assert "hero-yes" not in response.text

    async def test_stale_posting_with_long_last_seen_range_shows_in_calendar(self, client, db_session):
        """A posting first seen long ago but still active (last_seen within window) should count."""
        far_past = date.today() - timedelta(days=90)
        today = date.today()
        run = _make_scrape_run("anthropic", "success", started_at=datetime.now(UTC))
        db_session.add(run)
        await db_session.flush()
        db_session.add(
            _make_posting(
                company="anthropic",
                scrape_run_id=run.id,
                title="Long-running SWE role",
                first_seen=far_past,
                last_seen=today,
                is_swe=True,
                classified=True,
            )
        )
        await db_session.commit()
        response = await client.get("/")
        assert response.status_code == 200
        assert "hero-yes" in response.text


# --- day-detail tests ------------------------------------------------------


class TestDayDetail:
    async def test_day_detail_amber_when_no_scrape(self, client):
        """A date we never scraped renders the amber 'no scraping' banner."""
        target = date(2020, 1, 1)
        response = await client.get(f"/day/{target.isoformat()}")
        assert response.status_code == 200
        assert 'class="day-status day-status-amber"' in response.text
        assert "No scraping was performed" in response.text

    async def test_day_detail_amber_when_classification_pending(self, client, db_session):
        """Scraped day with unclassified postings and 0 SWE so far -> amber pending banner."""
        target = date.today() - timedelta(days=1)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Pending",
                    "first_seen": target,
                    "last_seen": target,
                    "is_swe": False,
                    "classified": False,
                }
            ],
        )
        response = await client.get(f"/day/{target.isoformat()}")
        assert response.status_code == 200
        assert 'class="day-status day-status-amber"' in response.text
        assert "pending classification" in response.text
        assert "spinner-lg" in response.text

    async def test_day_detail_red_when_scraped_no_swe(self, client, db_session):
        """Scraped day with no SWE postings -> red banner."""
        target = date.today() - timedelta(days=2)
        await _seed_run_with_postings(
            db_session,
            company="anthropic",
            started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            postings=[
                {
                    "title": "Marketing",
                    "first_seen": target,
                    "last_seen": target,
                    "is_swe": False,
                    "classified": True,
                }
            ],
        )
        response = await client.get(f"/day/{target.isoformat()}")
        assert response.status_code == 200
        assert 'class="day-status day-status-red"' in response.text
        assert "no software engineering postings were found" in response.text

    async def test_day_detail_groups_by_company(self, client, db_session):
        """Multiple companies with SWE postings -> day detail groups them under company cards."""
        target = date.today() - timedelta(days=3)
        for company, count in (("anthropic", 2), ("openai", 1)):
            run = _make_scrape_run(
                company,
                "success",
                started_at=datetime.combine(target, datetime.min.time(), tzinfo=UTC),
            )
            db_session.add(run)
            await db_session.flush()
            for i in range(count):
                db_session.add(
                    _make_posting(
                        company=company,
                        scrape_run_id=run.id,
                        title=f"{company.title()} SWE {i}",
                        first_seen=target,
                        last_seen=target,
                        is_swe=True,
                        classified=True,
                        url=f"https://{company}.example.com/swe-{i}",
                    )
                )
        await db_session.commit()
        response = await client.get(f"/day/{target.isoformat()}")
        assert response.status_code == 200
        assert "3 software engineering posting" in response.text
        # Both companies listed
        assert "Anthropic" in response.text
        assert "Openai" in response.text
        # Each title appears
        assert "Anthropic SWE 0" in response.text
        assert "Anthropic SWE 1" in response.text
        assert "Openai SWE 0" in response.text


# --- helpers --------------------------------------------------------------


def _extract_day_cell(html: str, target: date) -> str:
    """Return the substring of the calendar anchor for a given date.

    The calendar links are of the form <a href="/day/YYYY-MM-DD" class="..."> ... </a>.
    We slice from the href to the closing </a> so assertions can be scoped to a
    single calendar cell without being affected by unrelated markup elsewhere on
    the page.
    """
    href = f'href="/day/{target.isoformat()}"'
    start = html.find(href)
    assert start != -1, f"calendar cell for {target} not found in rendered HTML"
    end = html.find("</a>", start)
    assert end != -1, f"calendar cell for {target} not closed in rendered HTML"
    return html[start:end]
