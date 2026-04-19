from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.queries import get_daily_counts, get_postings_for_date, get_recent_scrape_runs, get_todays_scrape_summary
from src.db.session import get_session_factory

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
CLAIM_EPOCH = date(2025, 3, 14)  # Dario Amodei's claim date


def create_app(db_session_override=None) -> FastAPI:
    app = FastAPI(title="Are They Still Hiring Software Engineers?")
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    _session_factory = None

    async def get_session():
        if db_session_override is not None:
            yield db_session_override
            return
        nonlocal _session_factory
        if _session_factory is None:
            _session_factory = get_session_factory()
        async with _session_factory() as session:
            yield session

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def home(request: Request, session: AsyncSession = Depends(get_session)):
        today = date.today()
        summary = await get_todays_scrape_summary(session)
        raw_counts = await get_daily_counts(session)
        # Build a lookup by date string
        day_data = {
            d["date"].isoformat(): {
                "date": d["date"].isoformat(),
                "count": d["count"],
                "scraped": d["scraped"],
                "classifying": d["classifying"],
            }
            for d in raw_counts
        }

        # Build calendar weeks (Mon=0 ... Sun=6)
        from datetime import timedelta

        current_month = today.month
        start = today - timedelta(days=29)
        # Pad to start of the week (Monday)
        start_weekday = start.weekday()  # 0=Mon

        calendar_weeks = []
        week = [None] * start_weekday  # pad leading days
        d = start
        while d <= today:
            iso = d.isoformat()
            entry = day_data.get(iso, {"date": iso, "count": 0, "scraped": False, "classifying": False})
            entry["in_current_month"] = d.month == current_month
            entry["day_num"] = d.day
            entry["weekday"] = d.strftime("%a")
            week.append(entry)
            if len(week) == 7:
                calendar_weeks.append(week)
                week = []
            d += timedelta(days=1)
        if week:
            calendar_weeks.append(week)

        # Determine display state:
        # "yes"         - at least one scraper finished and found SWE postings
        # "classifying" - postings fetched but some not yet classified
        # "no"          - all of today's postings classified, none are SWE
        # "unsure"      - scrapers still running or haven't run today
        if summary["has_postings"]:
            state = "yes"
        elif summary["unclassified_today"] > 0:
            state = "classifying"
        elif summary["succeeded"] >= 2 and summary["active_today_total"] > 0:
            state = "no"
        else:
            state = "unsure"

        delta = today - CLAIM_EPOCH
        months = delta.days // 30
        days_r = delta.days % 30
        return templates.TemplateResponse(
            request,
            "home.html",
            {
                "state": state,
                "count": summary["posting_count"],
                "calendar_weeks": calendar_weeks,
                "months": months,
                "days_remainder": days_r,
                "total_days": delta.days,
                "scrape_summary": summary,
            },
        )

    @app.get("/day/{target_date}")
    async def day_detail(request: Request, target_date: str, session: AsyncSession = Depends(get_session)):
        from src.db.queries import get_scrape_runs_for_date, get_unclassified_count_for_date

        parsed_date = date.fromisoformat(target_date)
        postings = await get_postings_for_date(session, parsed_date)
        scrape_runs = await get_scrape_runs_for_date(session, parsed_date)
        unclassified = await get_unclassified_count_for_date(session, parsed_date)
        by_company: dict[str, list] = {}
        for p in postings:
            by_company.setdefault(p.company, []).append(p)

        scraped = len(scrape_runs) > 0
        return templates.TemplateResponse(
            request,
            "day_detail.html",
            {
                "target_date": parsed_date,
                "postings": postings,
                "by_company": by_company,
                "total": len(postings),
                "scraped": scraped,
                "scrape_runs": scrape_runs,
                "unclassified": unclassified,
            },
        )

    @app.get("/scrapes")
    async def scrape_status(request: Request, session: AsyncSession = Depends(get_session)):
        runs = await get_recent_scrape_runs(session)
        return templates.TemplateResponse(request, "scrape_status.html", {"runs": runs})

    @app.get("/about")
    async def about(request: Request):
        return templates.TemplateResponse(request, "about.html", {})

    return app
