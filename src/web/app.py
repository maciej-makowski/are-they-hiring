from datetime import date, timedelta
from pathlib import Path

from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.session import get_session_factory
from src.db.queries import get_daily_counts, get_postings_for_date, get_yesterday_count, get_recent_scrape_runs

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
        count = await get_yesterday_count(session)
        daily_counts = await get_daily_counts(session)
        is_hiring = count > 0
        delta = today - CLAIM_EPOCH
        months = delta.days // 30
        days_r = delta.days % 30
        return templates.TemplateResponse("home.html", {
            "request": request, "is_hiring": is_hiring, "count": count,
            "daily_counts": daily_counts, "months": months,
            "days_remainder": days_r, "total_days": delta.days,
        })

    @app.get("/day/{target_date}")
    async def day_detail(request: Request, target_date: str, session: AsyncSession = Depends(get_session)):
        parsed_date = date.fromisoformat(target_date)
        postings = await get_postings_for_date(session, parsed_date)
        by_company: dict[str, list] = {}
        for p in postings:
            by_company.setdefault(p.company, []).append(p)
        return templates.TemplateResponse("day_detail.html", {
            "request": request, "target_date": parsed_date,
            "postings": postings, "by_company": by_company, "total": len(postings),
        })

    @app.get("/scrapes")
    async def scrape_status(request: Request, session: AsyncSession = Depends(get_session)):
        runs = await get_recent_scrape_runs(session)
        return templates.TemplateResponse("scrape_status.html", {"request": request, "runs": runs})

    return app
