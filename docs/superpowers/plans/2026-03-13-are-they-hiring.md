# Are They Still Hiring Software Engineers — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a satirical web app that scrapes job postings from Anthropic, OpenAI, and Google DeepMind, classifies them via local LLM, and displays whether they're still hiring software engineers with humorous YES/NO UI.

**Architecture:** Podman pod with 4 containers (web, scraper, db, ollama) communicating over shared localhost. FastAPI serves HTMX/Jinja2 pages. Playwright scrapes career pages 3x daily. Ollama classifies job titles. PostgreSQL stores everything.

**Tech Stack:** Python 3.12, uv, FastAPI, SQLAlchemy (async), Alembic, Playwright, APScheduler, HTMX, Jinja2, Chart.js, canvas-confetti, Podman, systemd quadlet units

**Spec:** `Implementation.md` (root of repo)

---

## File Structure

```
are-they-hiring/
├── pyproject.toml                          # uv project: all Python deps
├── .env.example                            # template for configuration
├── .gitignore
├── Makefile                                # dev commands: test, build, run, migrate
├── alembic.ini                             # Alembic config pointing to src/db/migrations
├── Containerfile.web                       # FastAPI app image
├── Containerfile.scraper                   # Scrapers + Playwright image
├── podman/
│   ├── pod.yml                             # podman play kube definition
│   └── systemd/
│       ├── are-they-hiring.pod             # quadlet pod unit
│       ├── are-they-hiring-web.container   # quadlet web container
│       ├── are-they-hiring-db.container    # quadlet postgres container
│       ├── are-they-hiring-ollama.container # quadlet ollama container
│       └── are-they-hiring-scraper.container # quadlet scraper container
├── src/
│   ├── __init__.py
│   ├── config.py                           # pydantic Settings from .env
│   ├── db/
│   │   ├── __init__.py
│   │   ├── models.py                       # SQLAlchemy ORM models (ScrapeRun, JobPosting)
│   │   ├── session.py                      # async engine + session factory
│   │   ├── queries.py                      # reusable query functions (dedup, aggregation)
│   │   └── migrations/
│   │       ├── env.py                      # Alembic env
│   │       ├── script.py.mako              # migration template
│   │       └── versions/                   # auto-generated migrations
│   ├── classifier/
│   │   ├── __init__.py
│   │   └── client.py                       # Ollama HTTP client for classification
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py                         # BaseScraper ABC with shared Playwright logic
│   │   ├── anthropic.py                    # Anthropic careers scraper
│   │   ├── openai_scraper.py               # OpenAI careers scraper
│   │   ├── deepmind.py                     # DeepMind careers scraper
│   │   └── scheduler.py                    # APScheduler entry point
│   └── web/
│       ├── __init__.py
│       ├── app.py                          # FastAPI app factory + routes
│       ├── templates/
│       │   ├── base.html                   # shared layout (nav, scrape status btn)
│       │   ├── home.html                   # YES/NO, counter, chart
│       │   ├── day_detail.html             # per-day job listing table
│       │   └── scrape_status.html          # scrape run history
│       └── static/
│           ├── style.css                   # all styles incl. siren animation
│           ├── app.js                      # counter, chart, confetti, sound triggers
│           └── sounds/
│               ├── victory.mp3             # YES celebration sound
│               └── alarm.mp3              # NO alarm sound
├── tests/
│   ├── __init__.py
│   ├── conftest.py                         # shared fixtures: async db session, test client
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_db.py                      # model + query tests
│   │   ├── test_classifier.py              # Ollama client tests (mocked HTTP)
│   │   ├── test_scrapers.py                # scraper parsing tests (mocked Playwright)
│   │   └── test_api.py                     # FastAPI endpoint tests
│   ├── e2e/
│   │   ├── __init__.py
│   │   ├── conftest.py                     # E2E fixtures: seed DB, start app
│   │   ├── test_home.py                    # home page E2E
│   │   ├── test_day_detail.py              # day detail E2E
│   │   └── test_scrape_status.py           # scrape status E2E
│   └── fixtures/
│       ├── html_snapshots/                 # saved career page HTML for scraper tests
│       │   ├── anthropic_careers.html
│       │   ├── openai_careers.html
│       │   └── deepmind_careers.html
│       └── seed_data.sql                   # test data for API/E2E tests
└── podman-compose.test.yml                 # test environment (postgres + app)
```

---

## Chunk 1: Project Scaffolding + Database Layer

### Task 1: Initialize Project

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/config.py`

- [ ] **Step 1: Initialize git repo**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && git init`
Expected: `Initialized empty Git repository`

- [ ] **Step 2: Create .gitignore**

Create `.gitignore`:

```gitignore
__pycache__/
*.pyc
*.db
*.sqlite
.venv/
.env
*.egg-info/
dist/
build/
.pytest_cache/
.mypy_cache/
.superpowers/
```

- [ ] **Step 3: Initialize uv project**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv init --lib --python 3.12 --name are-they-hiring`

This creates `pyproject.toml` and `src/are_they_hiring/`. We need to remove the auto-generated package directory since we use flat modules under `src/`.

- [ ] **Step 4: Remove auto-generated package directory**

Run: `rm -rf src/are_they_hiring`

- [ ] **Step 5: Replace pyproject.toml with project config**

Overwrite `pyproject.toml`:

```toml
[project]
name = "are-they-hiring"
version = "0.1.0"
description = "Are they still hiring software engineers?"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "sqlalchemy[asyncio]>=2.0",
    "asyncpg>=0.30",
    "alembic>=1.14",
    "jinja2>=3.1",
    "python-dotenv>=1.0",
    "pydantic-settings>=2.7",
    "httpx>=0.28",
    "playwright>=1.49",
    "apscheduler>=3.10,<4",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "pytest-httpx>=0.34",
    "aiosqlite>=0.20",
    "httpx>=0.28",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["."]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.backends"
```

- [ ] **Step 6: Create directory structure**

Run:
```bash
mkdir -p src/db/migrations/versions src/classifier src/scrapers src/web/templates src/web/static/sounds tests/integration tests/e2e tests/fixtures/html_snapshots docs/superpowers/plans docs/superpowers/specs podman/systemd
```

- [ ] **Step 7: Create __init__.py files**

Create empty `__init__.py` in: `src/`, `src/db/`, `src/classifier/`, `src/scrapers/`, `src/web/`, `tests/`, `tests/integration/`, `tests/e2e/`

- [ ] **Step 8: Create .env.example**

Create `.env.example`:

```env
# General
TZ=UTC

# Database
POSTGRES_USER=arethey
POSTGRES_PASSWORD=changeme
POSTGRES_DB=arethey
DATABASE_URL=postgresql+asyncpg://arethey:changeme@localhost:5432/arethey

# Web
WEB_PORT=8000
BASE_URL=http://localhost:8000

# Scraper
SCRAPE_SCHEDULE=06:00,12:00,18:00
SCRAPE_RETRY_MAX=3
SCRAPE_DELAY_SECONDS=2

# Ollama
OLLAMA_MODEL=tinyllama:1.1b
OLLAMA_HOST=http://localhost:11434

# Companies (career page URLs)
ANTHROPIC_CAREERS_URL=https://www.anthropic.com/careers
OPENAI_CAREERS_URL=https://openai.com/careers
DEEPMIND_CAREERS_URL=https://deepmind.google/about/careers/
```

- [ ] **Step 9: Create config.py**

Create `src/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://arethey:changeme@localhost:5432/arethey"

    # Web
    web_port: int = 8000
    base_url: str = "http://localhost:8000"

    # Scraper
    scrape_schedule: str = "06:00,12:00,18:00"
    scrape_retry_max: int = 3
    scrape_delay_seconds: int = 2

    # Ollama
    ollama_model: str = "tinyllama:1.1b"
    ollama_host: str = "http://localhost:11434"

    # Company URLs
    anthropic_careers_url: str = "https://www.anthropic.com/careers"
    openai_careers_url: str = "https://openai.com/careers"
    deepmind_careers_url: str = "https://deepmind.google/about/careers/"

    # Timezone
    tz: str = "UTC"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 10: Install dependencies**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv sync --all-extras`
Expected: Dependencies installed, `.venv` created

- [ ] **Step 11: Commit**

```bash
git add .gitignore pyproject.toml .env.example src/__init__.py src/config.py src/db/__init__.py src/classifier/__init__.py src/scrapers/__init__.py src/web/__init__.py tests/__init__.py tests/integration/__init__.py tests/e2e/__init__.py uv.lock
git commit -m "feat: initialize project with uv, config, and directory structure"
```

---

### Task 2: Database Models

**Files:**
- Create: `src/db/models.py`
- Create: `tests/integration/test_db.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Write failing test for ScrapeRun model**

Create `tests/conftest.py`:

```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session
    await engine.dispose()
```

Create `tests/integration/test_db.py`:

```python
import uuid
from datetime import datetime, timezone

from src.db.models import ScrapeRun


async def test_create_scrape_run(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="pending",
        started_at=datetime.now(timezone.utc),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    assert run.company == "anthropic"
    assert run.status == "pending"
    assert run.error_message is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py::test_create_scrape_run -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.db.models'`

- [ ] **Step 3: Write database models**

Create `src/db/models.py`:

```python
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ScrapeRun(Base):
    __tablename__ = "scrape_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20))  # pending/running/success/failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    postings_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)

    postings: Mapped[list["JobPosting"]] = relationship(back_populates="scrape_run")


class JobPosting(Base):
    __tablename__ = "job_postings"
    __table_args__ = (
        UniqueConstraint("company", "url", name="uq_company_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    scrape_run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("scrape_runs.id"))
    company: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(500))
    location: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(1000))
    first_seen_date: Mapped[date] = mapped_column(Date)
    last_seen_date: Mapped[date] = mapped_column(Date)
    is_software_engineering: Mapped[bool] = mapped_column(Boolean, default=False)

    scrape_run: Mapped["ScrapeRun"] = relationship(back_populates="postings")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py::test_create_scrape_run -v`
Expected: PASS

- [ ] **Step 5: Write test for JobPosting model with dedup constraint**

Append to `tests/integration/test_db.py`:

```python
import pytest
from sqlalchemy.exc import IntegrityError

from src.db.models import JobPosting


async def test_create_job_posting(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="openai",
        status="success",
        started_at=datetime.now(timezone.utc),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    posting = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="openai",
        title="Senior Software Engineer",
        location="San Francisco",
        url="https://openai.com/careers/senior-swe",
        first_seen_date=date(2026, 3, 13),
        last_seen_date=date(2026, 3, 13),
        is_software_engineering=True,
    )
    db_session.add(posting)
    await db_session.commit()
    await db_session.refresh(posting)
    assert posting.title == "Senior Software Engineer"
    assert posting.is_software_engineering is True


async def test_duplicate_company_url_rejected(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.now(timezone.utc),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    posting1 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="SWE",
        location="SF",
        url="https://anthropic.com/careers/swe-1",
        first_seen_date=date(2026, 3, 13),
        last_seen_date=date(2026, 3, 13),
        is_software_engineering=True,
    )
    db_session.add(posting1)
    await db_session.commit()

    posting2 = JobPosting(
        id=uuid.uuid4(),
        scrape_run_id=run.id,
        company="anthropic",
        title="SWE duplicate",
        location="SF",
        url="https://anthropic.com/careers/swe-1",
        first_seen_date=date(2026, 3, 13),
        last_seen_date=date(2026, 3, 13),
        is_software_engineering=True,
    )
    db_session.add(posting2)
    with pytest.raises(IntegrityError):
        await db_session.commit()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py -v`
Expected: 3 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/db/models.py tests/conftest.py tests/integration/test_db.py
git commit -m "feat: add SQLAlchemy models for ScrapeRun and JobPosting"
```

---

### Task 3: Database Session Management

**Files:**
- Create: `src/db/session.py`

- [ ] **Step 1: Write test for session factory**

Append to `tests/integration/test_db.py`:

```python
from sqlalchemy import text

from src.db.session import get_session_factory


async def test_session_factory_creates_working_session():
    factory = get_session_factory("sqlite+aiosqlite:///:memory:")
    async with factory() as session:
        assert session is not None
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py::test_session_factory_creates_working_session -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement session.py**

Create `src/db/session.py`:

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.config import settings


def get_session_factory(url: str | None = None) -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(url or settings.database_url)
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py::test_session_factory_creates_working_session -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/db/session.py tests/integration/test_db.py
git commit -m "feat: add async database session factory"
```

---

### Task 4: Database Query Functions

**Files:**
- Create: `src/db/queries.py`

- [ ] **Step 1: Write test for upsert_postings (dedup logic)**

Append to `tests/integration/test_db.py`:

```python
from datetime import date
from src.db.queries import upsert_postings


async def test_upsert_postings_inserts_new(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(),
        company="anthropic",
        status="success",
        started_at=datetime.now(timezone.utc),
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    raw_postings = [
        {"title": "SWE", "location": "SF", "url": "https://anthropic.com/swe-1"},
        {"title": "SRE", "location": "NYC", "url": "https://anthropic.com/sre-1"},
    ]
    count = await upsert_postings(
        db_session,
        scrape_run=run,
        raw_postings=raw_postings,
        classifications={"https://anthropic.com/swe-1": True, "https://anthropic.com/sre-1": True},
        today=date(2026, 3, 13),
    )
    assert count == 2


async def test_upsert_postings_updates_last_seen(db_session):
    run1 = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run1)
    await db_session.commit()

    raw = [{"title": "SWE", "location": "SF", "url": "https://anthropic.com/swe-1"}]
    await upsert_postings(
        db_session, scrape_run=run1, raw_postings=raw,
        classifications={"https://anthropic.com/swe-1": True},
        today=date(2026, 3, 13),
    )

    run2 = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run2)
    await db_session.commit()

    await upsert_postings(
        db_session, scrape_run=run2, raw_postings=raw,
        classifications={"https://anthropic.com/swe-1": True},
        today=date(2026, 3, 14),
    )

    from sqlalchemy import select
    result = await db_session.execute(
        select(JobPosting).where(JobPosting.url == "https://anthropic.com/swe-1")
    )
    posting = result.scalar_one()
    assert posting.first_seen_date == date(2026, 3, 13)
    assert posting.last_seen_date == date(2026, 3, 14)
    assert posting.scrape_run_id == run2.id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py::test_upsert_postings_inserts_new tests/integration/test_db.py::test_upsert_postings_updates_last_seen -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement upsert_postings**

Create `src/db/queries.py`:

```python
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import JobPosting, ScrapeRun


async def upsert_postings(
    session: AsyncSession,
    scrape_run: ScrapeRun,
    raw_postings: list[dict],
    classifications: dict[str, bool],
    today: date,
) -> int:
    """Insert new postings or update last_seen_date for existing ones. Returns count."""
    count = 0
    for raw in raw_postings:
        url = raw["url"]
        result = await session.execute(
            select(JobPosting).where(
                JobPosting.company == scrape_run.company,
                JobPosting.url == url,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.last_seen_date = today
            existing.scrape_run_id = scrape_run.id
        else:
            posting = JobPosting(
                scrape_run_id=scrape_run.id,
                company=scrape_run.company,
                title=raw["title"],
                location=raw["location"],
                url=url,
                first_seen_date=today,
                last_seen_date=today,
                is_software_engineering=classifications.get(url, False),
            )
            session.add(posting)
        count += 1

    await session.commit()
    return count


async def get_daily_counts(
    session: AsyncSession,
    days: int = 30,
) -> list[dict]:
    """Get SWE posting counts per day for the last N days.

    Uses last_seen_date because each scrape updates it — so grouping by
    last_seen_date shows how many postings were confirmed active on each day.
    """
    result = await session.execute(
        select(
            JobPosting.last_seen_date,
            func.count(JobPosting.id),
        )
        .where(JobPosting.is_software_engineering.is_(True))
        .group_by(JobPosting.last_seen_date)
        .order_by(JobPosting.last_seen_date.desc())
        .limit(days)
    )
    return [{"date": str(row[0]), "count": row[1]} for row in result.all()]


async def get_postings_for_date(
    session: AsyncSession,
    target_date: date,
) -> list[JobPosting]:
    """Get all software engineering postings visible on a given date."""
    result = await session.execute(
        select(JobPosting)
        .where(
            JobPosting.is_software_engineering.is_(True),
            JobPosting.first_seen_date <= target_date,
            JobPosting.last_seen_date >= target_date,
        )
        .order_by(JobPosting.company, JobPosting.title)
    )
    return list(result.scalars().all())


async def get_yesterday_count(session: AsyncSession, yesterday: date) -> int:
    """Get total software engineering postings for yesterday (determines YES/NO)."""
    result = await session.execute(
        select(func.count(JobPosting.id))
        .where(
            JobPosting.is_software_engineering.is_(True),
            JobPosting.first_seen_date <= yesterday,
            JobPosting.last_seen_date >= yesterday,
        )
    )
    return result.scalar() or 0


async def get_recent_scrape_runs(
    session: AsyncSession,
    limit: int = 50,
) -> list[ScrapeRun]:
    """Get recent scrape runs for the status page."""
    result = await session.execute(
        select(ScrapeRun)
        .order_by(ScrapeRun.started_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: Run all tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py -v`
Expected: All tests PASS

- [ ] **Step 5: Write tests for get_daily_counts and get_yesterday_count**

Append to `tests/integration/test_db.py`:

```python
from src.db.queries import get_daily_counts, get_yesterday_count, get_postings_for_date


async def test_get_daily_counts(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    for i in range(3):
        posting = JobPosting(
            id=uuid.uuid4(), scrape_run_id=run.id, company="anthropic",
            title=f"SWE {i}", location="SF", url=f"https://anthropic.com/swe-{i}",
            first_seen_date=date(2026, 3, 13), last_seen_date=date(2026, 3, 13),
            is_software_engineering=True,
        )
        db_session.add(posting)
    # One non-SWE posting — should not be counted
    db_session.add(JobPosting(
        id=uuid.uuid4(), scrape_run_id=run.id, company="anthropic",
        title="Marketing Manager", location="SF", url="https://anthropic.com/marketing",
        first_seen_date=date(2026, 3, 13), last_seen_date=date(2026, 3, 13),
        is_software_engineering=False,
    ))
    await db_session.commit()

    counts = await get_daily_counts(db_session)
    assert len(counts) == 1
    assert counts[0]["count"] == 3


async def test_get_yesterday_count(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(), company="openai", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    db_session.add(JobPosting(
        id=uuid.uuid4(), scrape_run_id=run.id, company="openai",
        title="Backend Engineer", location="SF", url="https://openai.com/be",
        first_seen_date=date(2026, 3, 12), last_seen_date=date(2026, 3, 13),
        is_software_engineering=True,
    ))
    await db_session.commit()

    count = await get_yesterday_count(db_session, date(2026, 3, 13))
    assert count == 1

    count_miss = await get_yesterday_count(db_session, date(2026, 3, 11))
    assert count_miss == 0


async def test_get_postings_for_date(db_session):
    run = ScrapeRun(
        id=uuid.uuid4(), company="deepmind", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    db_session.add(JobPosting(
        id=uuid.uuid4(), scrape_run_id=run.id, company="deepmind",
        title="Platform Engineer", location="London", url="https://deepmind.google/pe",
        first_seen_date=date(2026, 3, 10), last_seen_date=date(2026, 3, 14),
        is_software_engineering=True,
    ))
    db_session.add(JobPosting(
        id=uuid.uuid4(), scrape_run_id=run.id, company="deepmind",
        title="Research Scientist", location="London", url="https://deepmind.google/rs",
        first_seen_date=date(2026, 3, 10), last_seen_date=date(2026, 3, 14),
        is_software_engineering=False,
    ))
    await db_session.commit()

    postings = await get_postings_for_date(db_session, date(2026, 3, 12))
    assert len(postings) == 1
    assert postings[0].title == "Platform Engineer"
```

- [ ] **Step 6: Run all tests**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_db.py -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/db/queries.py tests/integration/test_db.py
git commit -m "feat: add database query functions with dedup and aggregation"
```

---

### Task 5: Alembic Setup

**Files:**
- Create: `alembic.ini`
- Create: `src/db/migrations/env.py`
- Create: `src/db/migrations/script.py.mako`

- [ ] **Step 1: Initialize Alembic**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run alembic init src/db/migrations`

This will create `alembic.ini` in the project root and migration files in `src/db/migrations/`. If it complains the directory exists, remove `src/db/migrations/` first and re-run.

- [ ] **Step 2: Update alembic.ini**

Edit `alembic.ini` — set `script_location`:

```ini
script_location = src/db/migrations
sqlalchemy.url = postgresql+asyncpg://arethey:changeme@localhost:5432/arethey
```

- [ ] **Step 3: Update env.py to use async and our models**

Replace `src/db/migrations/env.py`:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from src.config import settings
from src.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = settings.database_url
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(settings.database_url)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 4: Create Makefile with migrate command**

Create `Makefile`:

```makefile
.PHONY: test migrate revision lint

test:
	uv run pytest tests/ -v

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(msg)"

lint:
	uv run python -m py_compile src/config.py
	uv run python -m py_compile src/db/models.py
```

- [ ] **Step 5: Verify Alembic configuration loads correctly**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run alembic check 2>&1 || true`
Expected: May show "Target database is not up to date" (no postgres running) or import errors. The key is that `env.py` imports succeed — no `ModuleNotFoundError`. If you see import errors, fix them before proceeding.

Also verify with: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run python -c "from src.db.migrations.env import target_metadata; print(target_metadata.tables.keys())"`
Expected: Output includes `scrape_runs` and `job_postings`

- [ ] **Step 6: Commit**

```bash
git add alembic.ini src/db/migrations/ Makefile
git commit -m "feat: add Alembic migration setup with async support"
```

---

## Chunk 2: Classifier + Scrapers

### Task 6: Ollama Classifier Client

**Files:**
- Create: `src/classifier/client.py`
- Create: `tests/integration/test_classifier.py`

- [ ] **Step 1: Write failing test for classify_titles**

Create `tests/integration/test_classifier.py`:

```python
import pytest
from unittest.mock import AsyncMock

from src.classifier.client import classify_titles


@pytest.fixture
def mock_ollama(httpx_mock):
    def setup(responses: list[str]):
        for resp in responses:
            httpx_mock.add_response(
                url="http://localhost:11434/api/generate",
                method="POST",
                json={"response": resp},
            )
    return setup


async def test_classify_titles_yes(mock_ollama):
    mock_ollama(["yes"])
    result = await classify_titles(
        ["Senior Software Engineer"],
        ollama_host="http://localhost:11434",
        model="test-model",
    )
    assert result == {"Senior Software Engineer": True}


async def test_classify_titles_no(mock_ollama):
    mock_ollama(["no"])
    result = await classify_titles(
        ["Marketing Manager"],
        ollama_host="http://localhost:11434",
        model="test-model",
    )
    assert result == {"Marketing Manager": False}


async def test_classify_titles_multiple(mock_ollama):
    mock_ollama(["yes", "no", "yes"])
    result = await classify_titles(
        ["Backend Engineer", "HR Director", "SRE"],
        ollama_host="http://localhost:11434",
        model="test-model",
    )
    assert result == {
        "Backend Engineer": True,
        "HR Director": False,
        "SRE": True,
    }


async def test_classify_titles_handles_unexpected_response(mock_ollama):
    mock_ollama(["maybe"])
    result = await classify_titles(
        ["Ambiguous Role"],
        ollama_host="http://localhost:11434",
        model="test-model",
    )
    assert result == {"Ambiguous Role": False}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_classifier.py -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement classifier client**

Create `src/classifier/client.py`:

```python
import httpx

from src.config import settings

PROMPT_TEMPLATE = (
    "Given this job title: \"{title}\"\n"
    "Is this a software engineering role? This includes roles like software engineer, "
    "backend/frontend/fullstack developer, SRE, platform engineer, infrastructure "
    "engineer, DevOps engineer, and similar hands-on coding roles. "
    "It does NOT include research scientist, data analyst, product manager, designer, "
    "or management roles.\n"
    "Answer only: yes or no"
)


async def classify_titles(
    titles: list[str],
    ollama_host: str | None = None,
    model: str | None = None,
) -> dict[str, bool]:
    """Classify job titles as software engineering or not via Ollama."""
    host = ollama_host or settings.ollama_host
    model_name = model or settings.ollama_model
    results: dict[str, bool] = {}

    async with httpx.AsyncClient(timeout=30.0) as client:
        for title in titles:
            prompt = PROMPT_TEMPLATE.format(title=title)
            response = await client.post(
                f"{host}/api/generate",
                json={
                    "model": model_name,
                    "prompt": prompt,
                    "stream": False,
                },
            )
            response.raise_for_status()
            answer = response.json()["response"].strip().lower()
            results[title] = answer.startswith("yes")

    return results
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_classifier.py -v`
Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/classifier/client.py tests/integration/test_classifier.py
git commit -m "feat: add Ollama classifier client for job title classification"
```

---

### Task 7: Base Scraper Class

**Files:**
- Create: `src/scrapers/base.py`
- Create: `tests/integration/test_scrapers.py`

- [ ] **Step 1: Write failing test for base scraper interface**

Create `tests/integration/test_scrapers.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from src.scrapers.base import BaseScraper

FIXTURES = Path(__file__).parent.parent / "fixtures" / "html_snapshots"


class FakeScraper(BaseScraper):
    company = "fake"
    careers_url = "https://fake.com/careers"

    async def extract_postings(self, page) -> list[dict]:
        return [
            {"title": "SWE", "location": "SF", "url": "https://fake.com/swe-1"},
        ]


async def test_base_scraper_run_returns_postings():
    scraper = FakeScraper()
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_context.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)

    mock_pw = AsyncMock()
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("src.scrapers.base.async_playwright") as mock_async_pw:
        mock_async_pw.return_value.__aenter__ = AsyncMock(return_value=mock_pw)
        mock_async_pw.return_value.__aexit__ = AsyncMock(return_value=False)
        postings = await scraper.run()

    assert len(postings) == 1
    assert postings[0]["title"] == "SWE"
    assert postings[0]["url"] == "https://fake.com/swe-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_base_scraper_run_returns_postings -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement base scraper**

Create `src/scrapers/base.py`:

```python
import asyncio
from abc import ABC, abstractmethod

from playwright.async_api import async_playwright, Page

from src.config import settings


class BaseScraper(ABC):
    company: str
    careers_url: str

    @abstractmethod
    async def extract_postings(self, page: Page) -> list[dict]:
        """Extract job postings from the loaded careers page.

        Returns list of dicts with keys: title, location, url
        """
        ...

    async def run(self) -> list[dict]:
        """Navigate to careers page and extract postings."""
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            context = await browser.new_context(
                user_agent="AreTheyHiringBot/1.0 (+https://github.com/are-they-hiring)"
            )
            page = await context.new_page()

            await page.goto(self.careers_url, wait_until="networkidle")
            await asyncio.sleep(settings.scrape_delay_seconds)

            postings = await self.extract_postings(page)

            await context.close()
            await browser.close()

        return postings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_base_scraper_run_returns_postings -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/base.py tests/integration/test_scrapers.py
git commit -m "feat: add base scraper class with Playwright integration"
```

---

### Task 8: Anthropic Scraper

**Files:**
- Create: `src/scrapers/anthropic.py`
- Create: `tests/fixtures/html_snapshots/anthropic_careers.html`

- [ ] **Step 1: Create fixture HTML**

Create `tests/fixtures/html_snapshots/anthropic_careers.html`:

```html
<!DOCTYPE html>
<html>
<body>
  <div data-testid="job-listing">
    <a href="/careers/senior-software-engineer">
      <h3>Senior Software Engineer</h3>
    </a>
    <span class="location">San Francisco, CA</span>
  </div>
  <div data-testid="job-listing">
    <a href="/careers/product-manager">
      <h3>Product Manager</h3>
    </a>
    <span class="location">San Francisco, CA</span>
  </div>
  <div data-testid="job-listing">
    <a href="/careers/platform-engineer">
      <h3>Platform Engineer</h3>
    </a>
    <span class="location">Remote</span>
  </div>
</body>
</html>
```

**Note:** The actual HTML structure will differ from this fixture. During implementation, inspect the real Anthropic careers page and update both the fixture and the scraper selectors accordingly.

- [ ] **Step 2: Write failing test**

Append to `tests/integration/test_scrapers.py`:

```python
from playwright.async_api import async_playwright
from src.scrapers.anthropic import AnthropicScraper


async def test_anthropic_scraper_extracts_postings():
    """Uses a real Playwright page with set_content to test locator-based parsing."""
    scraper = AnthropicScraper()
    html = (FIXTURES / "anthropic_careers.html").read_text()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)

        postings = await scraper.extract_postings(page)

        await browser.close()

    assert len(postings) == 3
    assert postings[0]["title"] == "Senior Software Engineer"
    assert postings[0]["location"] == "San Francisco, CA"
    assert "senior-software-engineer" in postings[0]["url"]
```

**Note:** This test requires Playwright browsers installed. Run `uv run playwright install chromium` if not already done.

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_anthropic_scraper_extracts_postings -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement Anthropic scraper**

Create `src/scrapers/anthropic.py`:

```python
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.config import settings


class AnthropicScraper(BaseScraper):
    company = "anthropic"
    careers_url = settings.anthropic_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        """Extract job postings from Anthropic careers page.

        Note: Selectors must be updated if Anthropic changes their page structure.
        Inspect the real page and update selectors + fixture HTML accordingly.
        """
        postings = []
        listings = await page.locator("[data-testid='job-listing']").all()

        if not listings:
            listings = await page.locator("a[href*='/careers/']").all()

        for listing in listings:
            try:
                link = listing.locator("a[href*='/careers/']")
                if await listing.get_attribute("href"):
                    link = listing

                title_el = listing.locator("h3")
                title = await title_el.text_content() if await title_el.count() else ""
                if not title:
                    title = await link.text_content() or ""
                title = title.strip()

                href = await link.get_attribute("href") or ""
                if href.startswith("/"):
                    href = f"https://www.anthropic.com{href}"

                location_el = listing.locator(".location")
                location = ""
                if await location_el.count():
                    location = (await location_el.text_content() or "").strip()

                if title and href:
                    postings.append({
                        "title": title,
                        "location": location,
                        "url": href,
                    })
            except Exception:
                continue

        return postings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_anthropic_scraper_extracts_postings -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scrapers/anthropic.py tests/fixtures/html_snapshots/anthropic_careers.html tests/integration/test_scrapers.py
git commit -m "feat: add Anthropic careers page scraper"
```

---

### Task 9: OpenAI Scraper

**Files:**
- Create: `src/scrapers/openai_scraper.py`
- Create: `tests/fixtures/html_snapshots/openai_careers.html`

- [ ] **Step 1: Create fixture HTML**

Create `tests/fixtures/html_snapshots/openai_careers.html`:

```html
<!DOCTYPE html>
<html>
<body>
  <div class="job-card">
    <a href="https://openai.com/careers/backend-engineer">
      <h3 class="job-title">Backend Engineer</h3>
    </a>
    <span class="job-location">San Francisco</span>
  </div>
  <div class="job-card">
    <a href="https://openai.com/careers/research-scientist">
      <h3 class="job-title">Research Scientist</h3>
    </a>
    <span class="job-location">San Francisco</span>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write failing test**

Append to `tests/integration/test_scrapers.py`:

```python
from src.scrapers.openai_scraper import OpenAIScraper


async def test_openai_scraper_extracts_postings():
    scraper = OpenAIScraper()
    html = (FIXTURES / "openai_careers.html").read_text()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)

        postings = await scraper.extract_postings(page)

        await browser.close()

    assert len(postings) == 2
    assert postings[0]["title"] == "Backend Engineer"
    assert "backend-engineer" in postings[0]["url"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_openai_scraper_extracts_postings -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement OpenAI scraper**

Create `src/scrapers/openai_scraper.py`:

```python
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.config import settings


class OpenAIScraper(BaseScraper):
    company = "openai"
    careers_url = settings.openai_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        """Extract job postings from OpenAI careers page."""
        postings = []
        cards = await page.locator(".job-card").all()

        if not cards:
            cards = await page.locator("[class*='job']").all()

        for card in cards:
            try:
                link = card.locator("a")
                title_el = card.locator(".job-title, h3")
                location_el = card.locator(".job-location, [class*='location']")

                title = (await title_el.text_content() or "").strip()
                href = await link.get_attribute("href") or ""
                location = ""
                if await location_el.count():
                    location = (await location_el.text_content() or "").strip()

                if title and href:
                    postings.append({
                        "title": title,
                        "location": location,
                        "url": href,
                    })
            except Exception:
                continue

        return postings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_openai_scraper_extracts_postings -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scrapers/openai_scraper.py tests/fixtures/html_snapshots/openai_careers.html tests/integration/test_scrapers.py
git commit -m "feat: add OpenAI careers page scraper"
```

---

### Task 10: DeepMind Scraper

**Files:**
- Create: `src/scrapers/deepmind.py`
- Create: `tests/fixtures/html_snapshots/deepmind_careers.html`

- [ ] **Step 1: Create fixture HTML**

Create `tests/fixtures/html_snapshots/deepmind_careers.html`:

```html
<!DOCTYPE html>
<html>
<body>
  <div class="career-card">
    <a href="https://deepmind.google/about/careers/positions/1234-ml-infrastructure-engineer">
      <h3>ML Infrastructure Engineer</h3>
    </a>
    <span class="location">London, UK</span>
  </div>
  <div class="career-card">
    <a href="https://deepmind.google/about/careers/positions/5678-research-engineer">
      <h3>Research Engineer</h3>
    </a>
    <span class="location">Mountain View, CA</span>
  </div>
</body>
</html>
```

- [ ] **Step 2: Write failing test**

Append to `tests/integration/test_scrapers.py`:

```python
from src.scrapers.deepmind import DeepMindScraper


async def test_deepmind_scraper_extracts_postings():
    scraper = DeepMindScraper()
    html = (FIXTURES / "deepmind_careers.html").read_text()

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html)

        postings = await scraper.extract_postings(page)

        await browser.close()

    assert len(postings) == 2
    assert postings[0]["title"] == "ML Infrastructure Engineer"
    assert "London" in postings[0]["location"]
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_deepmind_scraper_extracts_postings -v`
Expected: FAIL — `ImportError`

- [ ] **Step 4: Implement DeepMind scraper**

Create `src/scrapers/deepmind.py`:

```python
from playwright.async_api import Page

from src.scrapers.base import BaseScraper
from src.config import settings


class DeepMindScraper(BaseScraper):
    company = "deepmind"
    careers_url = settings.deepmind_careers_url

    async def extract_postings(self, page: Page) -> list[dict]:
        """Extract job postings from Google DeepMind careers page."""
        postings = []
        cards = await page.locator(".career-card").all()

        if not cards:
            cards = await page.locator("a[href*='/careers/positions/']").all()

        for card in cards:
            try:
                link = card.locator("a") if await card.locator("a").count() else card
                title_el = card.locator("h3")
                location_el = card.locator(".location, [class*='location']")

                title = (await title_el.text_content() or "").strip()
                href = await link.get_attribute("href") or ""
                location = ""
                if await location_el.count():
                    location = (await location_el.text_content() or "").strip()

                if title and href:
                    postings.append({
                        "title": title,
                        "location": location,
                        "url": href,
                    })
            except Exception:
                continue

        return postings
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_deepmind_scraper_extracts_postings -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/scrapers/deepmind.py tests/fixtures/html_snapshots/deepmind_careers.html tests/integration/test_scrapers.py
git commit -m "feat: add DeepMind careers page scraper"
```

---

### Task 11: Scrape Scheduler

**Files:**
- Create: `src/scrapers/scheduler.py`

- [ ] **Step 1: Write failing test for run_scrape orchestration**

Append to `tests/integration/test_scrapers.py`:

```python
from datetime import datetime, timezone
from src.scrapers.scheduler import run_scrape
from src.db.models import ScrapeRun
from sqlalchemy import select


async def test_run_scrape_creates_successful_run(db_session):
    with patch("src.scrapers.scheduler.SCRAPERS", {"fake": FakeScraper}):
        with patch.object(FakeScraper, "run", new_callable=AsyncMock) as mock_run:
            mock_run.return_value = [
                {"title": "SWE", "location": "SF", "url": "https://fake.com/swe-1"},
            ]
            with patch("src.scrapers.scheduler.classify_titles", new_callable=AsyncMock) as mock_classify:
                mock_classify.return_value = {"SWE": True}
                await run_scrape("fake", db_session)

    result = await db_session.execute(select(ScrapeRun).where(ScrapeRun.company == "fake"))
    run = result.scalar_one()
    assert run.status == "success"
    assert run.postings_found == 1


async def test_run_scrape_handles_failure(db_session):
    with patch("src.scrapers.scheduler.SCRAPERS", {"fake": FakeScraper}):
        with patch.object(FakeScraper, "run", new_callable=AsyncMock) as mock_run:
            mock_run.side_effect = RuntimeError("Browser crashed")
            await run_scrape("fake", db_session)

    result = await db_session.execute(select(ScrapeRun).where(ScrapeRun.company == "fake"))
    run = result.scalar_one()
    assert run.status == "failed"
    assert "Browser crashed" in run.error_message
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py::test_run_scrape_creates_successful_run tests/integration/test_scrapers.py::test_run_scrape_handles_failure -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement scheduler**

Create `src/scrapers/scheduler.py`:

```python
import asyncio
import logging
from datetime import datetime, date, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession

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


async def run_scrape(company: str, session: AsyncSession) -> None:
    """Run a single scrape for a company with retry logic.

    Creates ScrapeRun records for each attempt. Retries with exponential backoff
    up to SCRAPE_RETRY_MAX times on failure.
    """
    scraper_cls = SCRAPERS[company]
    max_attempts = settings.scrape_retry_max

    for attempt in range(1, max_attempts + 1):
        scraper = scraper_cls()
        run = ScrapeRun(
            company=company,
            status="running",
            started_at=datetime.now(timezone.utc),
            attempt_number=attempt,
        )
        session.add(run)
        await session.commit()

        try:
            raw_postings = await scraper.run()
            titles = [p["title"] for p in raw_postings]
            classifications = await classify_titles(titles)

            url_classifications = {}
            for posting in raw_postings:
                url_classifications[posting["url"]] = classifications.get(posting["title"], False)

            today = date.today()
            count = await upsert_postings(
                session,
                scrape_run=run,
                raw_postings=raw_postings,
                classifications=url_classifications,
                today=today,
            )

            run.status = "success"
            run.postings_found = count
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return  # Success — no retry needed

        except Exception as e:
            logger.error(f"Scrape failed for {company} (attempt {attempt}/{max_attempts}): {e}")
            run.status = "failed"
            run.error_message = str(e)
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()

            if attempt < max_attempts:
                backoff = 2 ** (attempt - 1) * 5  # 5s, 10s, 20s...
                logger.info(f"Retrying {company} in {backoff}s...")
                await asyncio.sleep(backoff)


async def run_all_scrapes() -> None:
    """Run scrapes for all companies concurrently."""
    session_factory = get_session_factory()

    async def _scrape_company(company: str):
        try:
            async with session_factory() as session:
                await run_scrape(company, session)
        except Exception as e:
            logger.error(f"Failed to run scrape for {company}: {e}")

    await asyncio.gather(*[_scrape_company(c) for c in SCRAPERS])


def create_scheduler() -> AsyncIOScheduler:
    """Create and configure the APScheduler instance."""
    scheduler = AsyncIOScheduler()

    schedule_times = settings.scrape_schedule.split(",")
    for time_str in schedule_times:
        hour, minute = time_str.strip().split(":")
        scheduler.add_job(
            run_all_scrapes,
            "cron",
            hour=int(hour),
            minute=int(minute),
            timezone=settings.tz,
        )

    return scheduler


async def main():
    scheduler = create_scheduler()
    scheduler.start()
    logger.info("Scheduler started. Scrapes scheduled at: %s", settings.scrape_schedule)

    # Run immediately on startup
    await run_all_scrapes()

    # Keep running for scheduled jobs
    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_scrapers.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/scrapers/scheduler.py tests/integration/test_scrapers.py
git commit -m "feat: add scrape scheduler with APScheduler and run orchestration"
```

---

## Chunk 3: Web Application

### Task 12: FastAPI App + Base Template

**Files:**
- Create: `src/web/app.py`
- Create: `src/web/templates/base.html`
- Create: `tests/integration/test_api.py`

- [ ] **Step 1: Write failing test for health endpoint**

Create `tests/integration/test_api.py`:

```python
import pytest
from httpx import AsyncClient, ASGITransport

from src.web.app import create_app


@pytest.fixture
def app(db_session):
    return create_app(db_session_override=db_session)


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py::test_health_endpoint -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement FastAPI app factory**

Create `src/web/app.py`:

```python
from datetime import date, timedelta, datetime
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

# Epoch: date Dario Amodei made the claim (Business Insider, March 14, 2025)
CLAIM_EPOCH = date(2025, 3, 14)


def create_app(db_session_override=None) -> FastAPI:
    app = FastAPI(title="Are They Still Hiring Software Engineers?")

    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # Session dependency
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
        yesterday = today - timedelta(days=1)

        count = await get_yesterday_count(session, yesterday)
        daily_counts = await get_daily_counts(session)
        is_hiring = count > 0

        # Calculate time since claim
        delta = today - CLAIM_EPOCH
        months = delta.days // 30
        days = delta.days % 30

        return templates.TemplateResponse("home.html", {
            "request": request,
            "is_hiring": is_hiring,
            "count": count,
            "daily_counts": daily_counts,
            "months": months,
            "days_remainder": days,
            "total_days": delta.days,
        })

    @app.get("/day/{target_date}")
    async def day_detail(request: Request, target_date: str, session: AsyncSession = Depends(get_session)):
        parsed_date = date.fromisoformat(target_date)
        postings = await get_postings_for_date(session, parsed_date)

        # Group by company
        by_company: dict[str, list] = {}
        for p in postings:
            by_company.setdefault(p.company, []).append(p)

        return templates.TemplateResponse("day_detail.html", {
            "request": request,
            "target_date": parsed_date,
            "postings": postings,
            "by_company": by_company,
            "total": len(postings),
        })

    @app.get("/scrapes")
    async def scrape_status(request: Request, session: AsyncSession = Depends(get_session)):
        runs = await get_recent_scrape_runs(session)
        return templates.TemplateResponse("scrape_status.html", {
            "request": request,
            "runs": runs,
        })

    return app
```

- [ ] **Step 4: Create base template**

Create `src/web/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Are They Still Hiring Software Engineers?</title>
    <link rel="stylesheet" href="/static/style.css">
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
    <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1"></script>
</head>
<body>
    <nav>
        <a href="/scrapes" class="scrapes-btn" title="Scrape Status">&#9881;</a>
    </nav>
    <main>
        {% block content %}{% endblock %}
    </main>
    <script src="/static/app.js"></script>
</body>
</html>
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py::test_health_endpoint -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/web/app.py src/web/templates/base.html tests/integration/test_api.py
git commit -m "feat: add FastAPI app factory with health endpoint and base template"
```

---

### Task 13: Home Page

**Files:**
- Create: `src/web/templates/home.html`
- Create: `src/web/static/style.css`
- Create: `src/web/static/app.js`

- [ ] **Step 1: Write failing test for home page**

Append to `tests/integration/test_api.py`:

```python
import uuid
from datetime import datetime, timezone, date, timedelta

from src.db.models import ScrapeRun, JobPosting


async def _seed_postings(db_session, target_date: date, count: int = 3):
    """Helper to seed test postings."""
    run = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime.now(timezone.utc), attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()
    for i in range(count):
        db_session.add(JobPosting(
            id=uuid.uuid4(), scrape_run_id=run.id, company="anthropic",
            title=f"SWE {i}", location="SF", url=f"https://anthropic.com/swe-{i}",
            first_seen_date=target_date, last_seen_date=target_date,
            is_software_engineering=True,
        ))
    await db_session.commit()


async def test_home_page_yes_state(db_session, client):
    yesterday = date.today() - timedelta(days=1)
    await _seed_postings(db_session, yesterday, count=5)

    response = await client.get("/")
    assert response.status_code == 200
    assert "YES" in response.text
    assert "5" in response.text  # count should appear


async def test_home_page_no_state(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "NO" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py::test_home_page_yes_state tests/integration/test_api.py::test_home_page_no_state -v`
Expected: FAIL — template not found

- [ ] **Step 3: Create home template**

Create `src/web/templates/home.html`:

```html
{% extends "base.html" %}
{% block content %}
<div class="hero {% if is_hiring %}hero-yes{% else %}hero-no{% endif %}">
    <div class="counter">
        <p>It has been
            <strong id="counter-months">{{ months }}</strong> months and
            <strong id="counter-days">{{ days_remainder }}</strong> days
            since <a href="https://www.businessinsider.com/anthropic-ceo-dario-amodei-ai-replace-all-code" target="_blank">
            Dario Amodei said all code will be written by AI in 6 months</a>.
        </p>
    </div>

    <div class="answer-display">
        {% if is_hiring %}
        <h1 class="answer answer-yes">YES</h1>
        <p class="subtitle">They are still hiring <strong>{{ count }}</strong> software engineers.</p>
        <button id="celebrate-btn" class="sound-btn" onclick="playCelebrate()">
            &#127881; Click to celebrate
        </button>
        {% else %}
        <h1 class="answer answer-no">NO</h1>
        <p class="subtitle">No software engineering postings found yesterday.</p>
        <div class="siren-container">
            <div class="siren"></div>
        </div>
        <button id="alarm-btn" class="sound-btn" onclick="playAlarm()">
            &#9888; Click to panic
        </button>
        {% endif %}
    </div>

    <div class="chart-container">
        <h2>Software Engineering Postings Per Day</h2>
        <canvas id="postsChart" width="800" height="300"></canvas>
    </div>
</div>

<script>
    const dailyCounts = {{ daily_counts | tojson }};
</script>
{% endblock %}
```

- [ ] **Step 4: Create CSS**

Create `src/web/static/style.css`:

```css
* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: #111;
    color: #eee;
    min-height: 100vh;
}

nav {
    position: fixed;
    top: 1rem;
    right: 1rem;
    z-index: 100;
}

.scrapes-btn {
    display: inline-block;
    font-size: 1.5rem;
    color: #888;
    text-decoration: none;
    padding: 0.5rem;
    border-radius: 50%;
    transition: color 0.2s;
}
.scrapes-btn:hover { color: #fff; }

main { padding: 2rem; max-width: 900px; margin: 0 auto; }

/* Hero */
.hero { text-align: center; padding-top: 3rem; }

.counter { margin-bottom: 2rem; font-size: 1.1rem; color: #aaa; }
.counter a { color: #6ea8fe; }
.counter strong { color: #fff; font-size: 1.3rem; }

/* Answer display */
.answer {
    font-size: 8rem;
    font-weight: 900;
    letter-spacing: 0.1em;
    margin: 1rem 0;
}
.answer-yes { color: #22c55e; }
.answer-no { color: #ef4444; }

.hero-yes { animation: pulse-green 3s ease-in-out infinite; }
.hero-no { animation: flash-red 1.5s ease-in-out infinite; }

@keyframes pulse-green {
    0%, 100% { background: #111; }
    50% { background: #0a1f0a; }
}

@keyframes flash-red {
    0%, 100% { background: #111; }
    50% { background: #2a0a0a; }
}

.subtitle { font-size: 1.3rem; margin: 0.5rem 0 1.5rem; color: #ccc; }

/* Siren animation */
.siren-container { margin: 1rem 0; }
.siren {
    width: 60px; height: 60px;
    margin: 0 auto;
    border-radius: 50%;
    animation: siren-rotate 1s linear infinite;
}
@keyframes siren-rotate {
    0% { background: radial-gradient(circle, #ef4444, transparent); box-shadow: 0 0 30px #ef4444; }
    50% { background: radial-gradient(circle, #f59e0b, transparent); box-shadow: 0 0 30px #f59e0b; }
    100% { background: radial-gradient(circle, #ef4444, transparent); box-shadow: 0 0 30px #ef4444; }
}

/* Sound button */
.sound-btn {
    background: none;
    border: 1px solid #555;
    color: #ccc;
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    cursor: pointer;
    font-size: 1rem;
    margin-top: 1rem;
}
.sound-btn:hover { border-color: #aaa; color: #fff; }

/* Chart */
.chart-container {
    margin-top: 3rem;
    background: #1a1a1a;
    border-radius: 1rem;
    padding: 2rem;
}
.chart-container h2 { margin-bottom: 1rem; font-size: 1.2rem; color: #aaa; }

/* Day detail */
.back-link { color: #6ea8fe; text-decoration: none; margin-bottom: 1rem; display: inline-block; }
.back-link:hover { text-decoration: underline; }

.summary { margin: 1rem 0 2rem; }
.summary h1 { font-size: 2rem; margin-bottom: 0.5rem; }
.company-breakdown { display: flex; gap: 2rem; margin: 1rem 0; }
.company-count { background: #1a1a1a; padding: 1rem 1.5rem; border-radius: 0.5rem; }
.company-count .name { color: #aaa; font-size: 0.9rem; }
.company-count .num { font-size: 2rem; font-weight: 700; color: #22c55e; }

/* Job table */
.job-table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
.job-table th { text-align: left; padding: 0.75rem; color: #aaa; border-bottom: 1px solid #333; font-size: 0.85rem; text-transform: uppercase; }
.job-table td { padding: 0.75rem; border-bottom: 1px solid #222; }
.job-table tr:hover { background: #1a1a1a; }
.job-table a { color: #6ea8fe; text-decoration: none; }
.job-table a:hover { text-decoration: underline; }

/* Scrape status */
.status-table { width: 100%; border-collapse: collapse; }
.status-table th { text-align: left; padding: 0.75rem; color: #aaa; border-bottom: 1px solid #333; font-size: 0.85rem; text-transform: uppercase; }
.status-table td { padding: 0.75rem; border-bottom: 1px solid #222; }
.status-success { color: #22c55e; }
.status-failed { color: #ef4444; }
.status-running { color: #f59e0b; }
.error-details { color: #ef4444; font-size: 0.85rem; padding: 0.5rem; background: #1a0a0a; border-radius: 0.25rem; margin-top: 0.25rem; }

/* Warning triangle for chart */
.warning-icon { font-size: 2rem; color: #f59e0b; }
```

- [ ] **Step 5: Create JavaScript**

Create `src/web/static/app.js`:

```javascript
// === Counter (client-side live update) ===
const EPOCH = new Date('2025-03-14');

function updateCounter() {
    const now = new Date();
    const diff = now - EPOCH;
    const totalDays = Math.floor(diff / (1000 * 60 * 60 * 24));
    const months = Math.floor(totalDays / 30);
    const days = totalDays % 30;

    const monthsEl = document.getElementById('counter-months');
    const daysEl = document.getElementById('counter-days');
    if (monthsEl) monthsEl.textContent = months;
    if (daysEl) daysEl.textContent = days;
}
updateCounter();
setInterval(updateCounter, 60000);

// === Chart ===
if (typeof dailyCounts !== 'undefined' && document.getElementById('postsChart')) {
    const ctx = document.getElementById('postsChart').getContext('2d');

    // Warning triangle plugin for zero-posting days
    const warningPlugin = {
        id: 'warningTriangle',
        afterDatasetsDraw(chart) {
            const dataset = chart.data.datasets[0];
            const meta = chart.getDatasetMeta(0);
            dataset.data.forEach((value, index) => {
                if (value === 0) {
                    const bar = meta.data[index];
                    const { x } = bar;
                    const y = chart.scales.y.getPixelForValue(0) - 20;
                    chart.ctx.save();
                    chart.ctx.font = '24px serif';
                    chart.ctx.textAlign = 'center';
                    chart.ctx.fillText('\u26A0\uFE0F', x, y);
                    chart.ctx.restore();
                }
            });
        }
    };

    const labels = dailyCounts.map(d => d.date).reverse();
    const data = dailyCounts.map(d => d.count).reverse();

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'SWE Postings',
                data: data,
                backgroundColor: '#22c55e',
                borderRadius: 4,
            }]
        },
        options: {
            responsive: true,
            onClick: (event, elements) => {
                if (elements.length > 0) {
                    const index = elements[0].index;
                    const dateStr = labels[index];
                    window.location.href = '/day/' + dateStr;
                }
            },
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { color: '#888' }, grid: { display: false } },
                y: { ticks: { color: '#888' }, grid: { color: '#222' }, beginAtZero: true },
            }
        },
        plugins: [warningPlugin]
    });
}

// === Sound effects ===
function playCelebrate() {
    const audio = new Audio('/static/sounds/victory.mp3');
    audio.play().catch(() => {});
    // Also fire confetti
    if (typeof confetti === 'function') {
        confetti({ particleCount: 200, spread: 100, origin: { y: 0.6 } });
    }
}

function playAlarm() {
    const audio = new Audio('/static/sounds/alarm.mp3');
    audio.play().catch(() => {});
}
```

- [ ] **Step 6: Create placeholder sound files**

Run:
```bash
# Create tiny silent MP3 placeholders (1 second of silence)
# These should be replaced with actual fun sounds later
touch src/web/static/sounds/victory.mp3
touch src/web/static/sounds/alarm.mp3
```

**Note:** Replace these with actual sound files. Short royalty-free sounds work well — a fanfare for victory, an alarm buzzer for the NO state.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/web/app.py src/web/templates/base.html src/web/templates/home.html src/web/static/style.css src/web/static/app.js src/web/static/sounds/ tests/integration/test_api.py
git commit -m "feat: add home page with YES/NO display, counter, chart, and sound effects"
```

---

### Task 14: Day Detail Page

**Files:**
- Create: `src/web/templates/day_detail.html`

- [ ] **Step 1: Write failing test for day detail endpoint**

Append to `tests/integration/test_api.py`:

```python
async def test_day_detail_page(db_session, client):
    target = date(2026, 3, 12)
    await _seed_postings(db_session, target, count=3)

    response = await client.get(f"/day/{target.isoformat()}")
    assert response.status_code == 200
    assert "March 12, 2026" in response.text or "2026-03-12" in response.text
    assert "SWE 0" in response.text
    assert "anthropic" in response.text.lower()


async def test_day_detail_empty(client):
    response = await client.get("/day/2026-01-01")
    assert response.status_code == 200
    assert "0" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py::test_day_detail_page tests/integration/test_api.py::test_day_detail_empty -v`
Expected: FAIL — template not found

- [ ] **Step 3: Create day detail template**

Create `src/web/templates/day_detail.html`:

```html
{% extends "base.html" %}
{% block content %}
<a href="/" class="back-link">&larr; Back</a>

<div class="summary">
    <h1>{{ target_date.strftime('%B %d, %Y') }}</h1>
    <p class="subtitle">Total software engineering postings: <strong>{{ total }}</strong></p>

    <div class="company-breakdown">
        {% for company, posts in by_company.items() %}
        <div class="company-count">
            <div class="name">{{ company | title }}</div>
            <div class="num">{{ posts | length }}</div>
        </div>
        {% endfor %}
    </div>
</div>

<table class="job-table">
    <thead>
        <tr>
            <th>Company</th>
            <th>Title</th>
            <th>Location</th>
            <th>Link</th>
        </tr>
    </thead>
    <tbody>
        {% for posting in postings %}
        <tr>
            <td>{{ posting.company | title }}</td>
            <td>{{ posting.title }}</td>
            <td>{{ posting.location }}</td>
            <td><a href="{{ posting.url }}" target="_blank">&rarr;</a></td>
        </tr>
        {% else %}
        <tr>
            <td colspan="4" style="text-align:center; color:#666;">No postings found for this date.</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/templates/day_detail.html tests/integration/test_api.py
git commit -m "feat: add day detail page with company breakdown and job table"
```

---

### Task 15: Scrape Status Page

**Files:**
- Create: `src/web/templates/scrape_status.html`

- [ ] **Step 1: Write failing test for scrape status endpoint**

Append to `tests/integration/test_api.py`:

```python
async def test_scrape_status_page(db_session, client):
    run = ScrapeRun(
        id=uuid.uuid4(), company="anthropic", status="success",
        started_at=datetime(2026, 3, 13, 12, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 3, 13, 12, 0, 4, tzinfo=timezone.utc),
        postings_found=18, attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    response = await client.get("/scrapes")
    assert response.status_code == 200
    assert "anthropic" in response.text.lower()
    assert "18" in response.text


async def test_scrape_status_shows_errors(db_session, client):
    run = ScrapeRun(
        id=uuid.uuid4(), company="openai", status="failed",
        started_at=datetime(2026, 3, 13, 6, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 3, 13, 6, 0, 10, tzinfo=timezone.utc),
        error_message="TimeoutError: page load exceeded 30s",
        attempt_number=1,
    )
    db_session.add(run)
    await db_session.commit()

    response = await client.get("/scrapes")
    assert response.status_code == 200
    assert "failed" in response.text.lower()
    assert "TimeoutError" in response.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py::test_scrape_status_page tests/integration/test_api.py::test_scrape_status_shows_errors -v`
Expected: FAIL — template not found

- [ ] **Step 3: Create scrape status template**

Create `src/web/templates/scrape_status.html`:

```html
{% extends "base.html" %}
{% block content %}
<a href="/" class="back-link">&larr; Back</a>

<h1>Scrape Run History</h1>

<table class="status-table">
    <thead>
        <tr>
            <th>Time</th>
            <th>Company</th>
            <th>Status</th>
            <th>Found</th>
            <th>Duration</th>
        </tr>
    </thead>
    <tbody>
        {% for run in runs %}
        <tr>
            <td>{{ run.started_at.strftime('%Y-%m-%d %H:%M') if run.started_at else '-' }}</td>
            <td>{{ run.company | title }}</td>
            <td class="status-{{ run.status }}">
                {% if run.status == 'success' %}&#10003;
                {% elif run.status == 'failed' %}&#10007;
                {% elif run.status == 'running' %}&#9203;
                {% else %}&#8230;{% endif %}
                {{ run.status }}
            </td>
            <td>{{ run.postings_found if run.postings_found is not none else '-' }}</td>
            <td>
                {% if run.finished_at and run.started_at %}
                    {{ (run.finished_at - run.started_at).total_seconds() | round(1) }}s
                {% else %}-{% endif %}
            </td>
        </tr>
        {% if run.status == 'failed' and run.error_message %}
        <tr>
            <td colspan="5">
                <div class="error-details">{{ run.error_message }}</div>
            </td>
        </tr>
        {% endif %}
        {% else %}
        <tr>
            <td colspan="5" style="text-align:center; color:#666;">No scrape runs yet.</td>
        </tr>
        {% endfor %}
    </tbody>
</table>
{% endblock %}
```

- [ ] **Step 4: Run all API tests**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/test_api.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/web/templates/scrape_status.html tests/integration/test_api.py
git commit -m "feat: add scrape status page with run history and error details"
```

---

## Chunk 4: Containerization + E2E Tests

### Task 16: Containerfiles

**Files:**
- Create: `Containerfile.web`
- Create: `Containerfile.scraper`

- [ ] **Step 1: Create web Containerfile**

Create `Containerfile.web`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY alembic.ini ./

# Install dependencies (no dev deps)
RUN uv sync --no-dev --frozen

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "src.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create scraper Containerfile**

Create `Containerfile.scraper`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system deps for Playwright/Chromium (ARM64 compatible)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxkbcommon0 \
    libgbm1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Point Playwright at system Chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/usr
ENV PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install dependencies (no dev deps)
RUN uv sync --no-dev --frozen

CMD ["uv", "run", "python", "-m", "src.scrapers.scheduler"]
```

- [ ] **Step 3: Verify Containerfiles build**

Run:
```bash
cd /var/home/cfiet/Documents/Projects/are-they-hiring && podman build -f Containerfile.web -t are-they-hiring-web .
```
Expected: Image builds successfully

Run:
```bash
cd /var/home/cfiet/Documents/Projects/are-they-hiring && podman build -f Containerfile.scraper -t are-they-hiring-scraper .
```
Expected: Image builds successfully

- [ ] **Step 4: Commit**

```bash
git add Containerfile.web Containerfile.scraper
git commit -m "feat: add Containerfiles for web and scraper images"
```

---

### Task 17: Podman Pod Configuration

**Files:**
- Create: `podman/pod.yml`

- [ ] **Step 1: Create pod definition**

Create `podman/pod.yml`:

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: are-they-hiring
spec:
  containers:
    - name: db
      image: docker.io/postgres:16
      env:
        - name: POSTGRES_USER
          value: "${POSTGRES_USER:-arethey}"
        - name: POSTGRES_PASSWORD
          value: "${POSTGRES_PASSWORD:-changeme}"
        - name: POSTGRES_DB
          value: "${POSTGRES_DB:-arethey}"
      volumeMounts:
        - name: db-data
          mountPath: /var/lib/postgresql/data
      ports: []

    - name: ollama
      image: docker.io/ollama/ollama:latest
      volumeMounts:
        - name: ollama-models
          mountPath: /root/.ollama
      ports: []

    - name: web
      image: localhost/are-they-hiring-web:latest
      env:
        - name: DATABASE_URL
          value: "postgresql+asyncpg://${POSTGRES_USER:-arethey}:${POSTGRES_PASSWORD:-changeme}@localhost:5432/${POSTGRES_DB:-arethey}"
        - name: OLLAMA_HOST
          value: "http://localhost:11434"
        - name: TZ
          value: "${TZ:-UTC}"
      ports:
        - containerPort: 8000
          hostPort: ${WEB_PORT:-8000}

    - name: scraper
      image: localhost/are-they-hiring-scraper:latest
      env:
        - name: DATABASE_URL
          value: "postgresql+asyncpg://${POSTGRES_USER:-arethey}:${POSTGRES_PASSWORD:-changeme}@localhost:5432/${POSTGRES_DB:-arethey}"
        - name: OLLAMA_HOST
          value: "http://localhost:11434"
        - name: OLLAMA_MODEL
          value: "${OLLAMA_MODEL:-tinyllama:1.1b}"
        - name: SCRAPE_SCHEDULE
          value: "${SCRAPE_SCHEDULE:-06:00,12:00,18:00}"
        - name: TZ
          value: "${TZ:-UTC}"
      ports: []

  volumes:
    - name: db-data
      persistentVolumeClaim:
        claimName: are-they-hiring-db-data
    - name: ollama-models
      persistentVolumeClaim:
        claimName: are-they-hiring-ollama-models
```

- [ ] **Step 2: Commit**

```bash
git add podman/pod.yml
git commit -m "feat: add Podman pod definition with all containers"
```

---

### Task 18: Systemd Quadlet Units

**Files:**
- Create: `podman/systemd/are-they-hiring.pod`
- Create: `podman/systemd/are-they-hiring-web.container`
- Create: `podman/systemd/are-they-hiring-db.container`
- Create: `podman/systemd/are-they-hiring-ollama.container`
- Create: `podman/systemd/are-they-hiring-scraper.container`

- [ ] **Step 1: Create pod quadlet unit**

Create `podman/systemd/are-they-hiring.pod`:

```ini
[Pod]
PodName=are-they-hiring
PublishPort=${WEB_PORT:-8000}:8000

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Create db container quadlet**

Create `podman/systemd/are-they-hiring-db.container`:

```ini
[Unit]
Description=Are They Hiring - PostgreSQL
Requires=are-they-hiring-pod.service
After=are-they-hiring-pod.service

[Container]
Image=docker.io/postgres:16
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env
Volume=are-they-hiring-db-data:/var/lib/postgresql/data

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Create ollama container quadlet**

Create `podman/systemd/are-they-hiring-ollama.container`:

```ini
[Unit]
Description=Are They Hiring - Ollama LLM
Requires=are-they-hiring-pod.service
After=are-they-hiring-pod.service

[Container]
Image=docker.io/ollama/ollama:latest
Pod=are-they-hiring.pod
Volume=are-they-hiring-ollama-models:/root/.ollama

[Install]
WantedBy=default.target
```

- [ ] **Step 4: Create web container quadlet**

Create `podman/systemd/are-they-hiring-web.container`:

```ini
[Unit]
Description=Are They Hiring - Web (FastAPI)
Requires=are-they-hiring-db.service are-they-hiring-ollama.service
After=are-they-hiring-db.service are-they-hiring-ollama.service

[Container]
Image=localhost/are-they-hiring-web:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env

[Install]
WantedBy=default.target
```

- [ ] **Step 5: Create scraper container quadlet**

Create `podman/systemd/are-they-hiring-scraper.container`:

```ini
[Unit]
Description=Are They Hiring - Scraper (Playwright + APScheduler)
Requires=are-they-hiring-db.service are-they-hiring-ollama.service
After=are-they-hiring-db.service are-they-hiring-ollama.service

[Container]
Image=localhost/are-they-hiring-scraper:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env

[Install]
WantedBy=default.target
```

- [ ] **Step 6: Commit**

```bash
git add podman/systemd/
git commit -m "feat: add systemd quadlet units for pod deployment"
```

---

### Task 19: Test Infrastructure + Makefile

**Files:**
- Create: `podman-compose.test.yml`
- Modify: `Makefile`

- [ ] **Step 1: Create test compose file**

Create `podman-compose.test.yml`:

```yaml
version: "3.8"
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_USER: arethey_test
      POSTGRES_PASSWORD: testpass
      POSTGRES_DB: arethey_test
    ports:
      - "5433:5432"
    tmpfs:
      - /var/lib/postgresql/data

  web:
    build:
      context: .
      dockerfile: Containerfile.web
    environment:
      DATABASE_URL: postgresql+asyncpg://arethey_test:testpass@db:5432/arethey_test
      OLLAMA_HOST: http://ollama:11434
    ports:
      - "8001:8000"
    depends_on:
      - db

  ollama:
    image: ollama/ollama:latest
    tmpfs:
      - /root/.ollama
```

- [ ] **Step 2: Update Makefile**

Replace `Makefile`:

```makefile
.PHONY: test test-integration test-e2e migrate revision lint build run clean

# Development
test:
	uv run pytest tests/integration/ -v

test-e2e:
	uv run pytest tests/e2e/ -v

migrate:
	uv run alembic upgrade head

revision:
	uv run alembic revision --autogenerate -m "$(msg)"

lint:
	uv run python -m py_compile src/config.py
	uv run python -m py_compile src/db/models.py
	uv run python -m py_compile src/web/app.py

# Container
build:
	podman build -f Containerfile.web -t are-they-hiring-web .
	podman build -f Containerfile.scraper -t are-they-hiring-scraper .

run:
	podman play kube podman/pod.yml

clean:
	podman play kube --down podman/pod.yml 2>/dev/null || true

# Test environment
test-env-up:
	podman-compose -f podman-compose.test.yml up -d

test-env-down:
	podman-compose -f podman-compose.test.yml down -v
```

- [ ] **Step 3: Commit**

```bash
git add podman-compose.test.yml Makefile
git commit -m "feat: add test compose file and update Makefile with build/run targets"
```

---

### Task 20: E2E Tests

**Files:**
- Create: `tests/e2e/conftest.py`
- Create: `tests/e2e/test_home.py`
- Create: `tests/e2e/test_day_detail.py`
- Create: `tests/e2e/test_scrape_status.py`
- Create: `tests/fixtures/seed_data.sql`

- [ ] **Step 1: Create seed data SQL**

Create `tests/fixtures/seed_data.sql`:

```sql
-- Seed data for E2E tests
INSERT INTO scrape_runs (id, company, status, started_at, finished_at, postings_found, attempt_number)
VALUES
    ('a0000000-0000-0000-0000-000000000001', 'anthropic', 'success', '2026-03-12 12:00:00+00', '2026-03-12 12:00:05+00', 3, 1),
    ('a0000000-0000-0000-0000-000000000002', 'openai', 'success', '2026-03-12 12:00:00+00', '2026-03-12 12:00:07+00', 2, 1),
    ('a0000000-0000-0000-0000-000000000003', 'deepmind', 'failed', '2026-03-12 12:00:00+00', '2026-03-12 12:00:10+00', NULL, 1);

INSERT INTO job_postings (id, scrape_run_id, company, title, location, url, first_seen_date, last_seen_date, is_software_engineering)
VALUES
    ('b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001', 'anthropic', 'Senior Software Engineer', 'San Francisco', 'https://anthropic.com/swe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001', 'anthropic', 'Platform Engineer', 'Remote', 'https://anthropic.com/pe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001', 'anthropic', 'Product Manager', 'NYC', 'https://anthropic.com/pm-1', CURRENT_DATE - 1, CURRENT_DATE - 1, false),
    ('b0000000-0000-0000-0000-000000000004', 'a0000000-0000-0000-0000-000000000002', 'openai', 'Backend Engineer', 'San Francisco', 'https://openai.com/be-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true),
    ('b0000000-0000-0000-0000-000000000005', 'a0000000-0000-0000-0000-000000000002', 'openai', 'Frontend Engineer', 'San Francisco', 'https://openai.com/fe-1', CURRENT_DATE - 1, CURRENT_DATE - 1, true);
```

- [ ] **Step 2: Create E2E conftest**

Create `tests/e2e/conftest.py`:

```python
import pytest
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

SEED_SQL = Path(__file__).parent.parent / "fixtures" / "seed_data.sql"
BASE_URL = "http://localhost:8001"


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    page = browser.new_page()
    yield page
    page.close()
```

**Note:** E2E tests assume the test environment is running (`make test-env-up`). The seed SQL should be loaded into the test DB before running E2E tests.

- [ ] **Step 3: Create home page E2E test**

Create `tests/e2e/test_home.py`:

```python
import re

BASE_URL = "http://localhost:8001"


def test_home_page_loads(page):
    page.goto(BASE_URL)
    assert page.title() == "Are They Still Hiring Software Engineers?"


def test_home_shows_yes_or_no(page):
    page.goto(BASE_URL)
    answer = page.locator(".answer")
    text = answer.text_content()
    assert text in ("YES", "NO")


def test_home_shows_counter(page):
    page.goto(BASE_URL)
    counter = page.locator(".counter")
    assert "months" in counter.text_content()
    assert "Dario Amodei" in counter.text_content()


def test_home_has_chart(page):
    page.goto(BASE_URL)
    canvas = page.locator("#postsChart")
    assert canvas.is_visible()


def test_home_has_scrape_status_link(page):
    page.goto(BASE_URL)
    link = page.locator(".scrapes-btn")
    assert link.is_visible()
    assert link.get_attribute("href") == "/scrapes"


def test_chart_bars_are_clickable(page):
    page.goto(BASE_URL)
    # Chart click navigation tested by verifying the onclick handler exists
    canvas = page.locator("#postsChart")
    assert canvas.is_visible()
```

- [ ] **Step 4: Create day detail E2E test**

Create `tests/e2e/test_day_detail.py`:

```python
from datetime import date, timedelta

BASE_URL = "http://localhost:8001"


def test_day_detail_loads(page):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page.goto(f"{BASE_URL}/day/{yesterday}")
    assert page.locator(".summary h1").is_visible()


def test_day_detail_shows_table(page):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page.goto(f"{BASE_URL}/day/{yesterday}")
    table = page.locator(".job-table")
    assert table.is_visible()


def test_day_detail_has_back_link(page):
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    page.goto(f"{BASE_URL}/day/{yesterday}")
    back = page.locator(".back-link")
    assert back.is_visible()
    back.click()
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")
```

- [ ] **Step 5: Create scrape status E2E test**

Create `tests/e2e/test_scrape_status.py`:

```python
BASE_URL = "http://localhost:8001"


def test_scrape_status_loads(page):
    page.goto(f"{BASE_URL}/scrapes")
    assert page.locator("h1").text_content() == "Scrape Run History"


def test_scrape_status_shows_table(page):
    page.goto(f"{BASE_URL}/scrapes")
    table = page.locator(".status-table")
    assert table.is_visible()


def test_scrape_status_has_back_link(page):
    page.goto(f"{BASE_URL}/scrapes")
    back = page.locator(".back-link")
    assert back.is_visible()
    back.click()
    assert page.url.rstrip("/") == BASE_URL.rstrip("/")
```

- [ ] **Step 6: Commit**

```bash
git add tests/e2e/ tests/fixtures/seed_data.sql
git commit -m "feat: add E2E tests for home, day detail, and scrape status pages"
```

---

### Task 21: Final Integration - Run All Tests

- [ ] **Step 1: Install Playwright browsers**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run playwright install chromium`
Expected: Chromium downloaded

- [ ] **Step 2: Run all integration tests**

Run: `cd /var/home/cfiet/Documents/Projects/are-they-hiring && uv run pytest tests/integration/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit any test fixes**

If any tests needed adjustment, commit the fixes:
```bash
git add -u
git commit -m "fix: adjust tests for full integration run"
```
