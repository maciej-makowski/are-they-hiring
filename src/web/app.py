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
        daily_counts = [
            {"date": d["date"].isoformat(), "count": d["count"], "scraped": d["scraped"]} for d in raw_counts
        ]

        # Determine display state:
        # "yes"     - at least one scraper finished and found SWE postings
        # "no"      - at least 2/3 scrapers succeeded and all returned 0
        # "unsure"  - scrapers still running or not enough data
        if summary["has_postings"]:
            state = "yes"
        elif summary["succeeded"] >= 2 and not summary["has_postings"]:
            state = "no"
        else:
            state = "unsure"

        delta = today - CLAIM_EPOCH
        months = delta.days // 30
        days_r = delta.days % 30
        return templates.TemplateResponse(
            "home.html",
            {
                "request": request,
                "state": state,
                "count": summary["posting_count"],
                "daily_counts": daily_counts,
                "months": months,
                "days_remainder": days_r,
                "total_days": delta.days,
                "scrape_summary": summary,
            },
        )

    @app.get("/day/{target_date}")
    async def day_detail(request: Request, target_date: str, session: AsyncSession = Depends(get_session)):
        parsed_date = date.fromisoformat(target_date)
        postings = await get_postings_for_date(session, parsed_date)
        by_company: dict[str, list] = {}
        for p in postings:
            by_company.setdefault(p.company, []).append(p)
        return templates.TemplateResponse(
            "day_detail.html",
            {
                "request": request,
                "target_date": parsed_date,
                "postings": postings,
                "by_company": by_company,
                "total": len(postings),
            },
        )

    @app.get("/scrapes")
    async def scrape_status(request: Request, session: AsyncSession = Depends(get_session)):
        runs = await get_recent_scrape_runs(session)
        return templates.TemplateResponse("scrape_status.html", {"request": request, "runs": runs})

    return app
