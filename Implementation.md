# Implementation Design Document

**Project:** are-they-still-hiring-software-engineers.com
**Initial design:** 2026-03-13
**Last updated:** 2026-04-19
**Status:** Implemented, running in dev environment

---

## Decision Log

### 1. Target Companies
**Decision:** Anthropic, OpenAI, Google DeepMind, xAI (added 2026-04-18), Perplexity (added 2026-04-18), Meta (added 2026-04-18 — initially AI/FAIR only, broadened to all teams 2026-04-18, see #38)
**Rationale:** The most prominent AI companies making bold claims about AI replacing software engineers. Direct relevance to the project's satirical premise. Additional labs can be added incrementally via the `SCRAPERS` registry; see roadmap item 6 for the remaining candidates.

### 2. Frontend Technology
**Decision:** HTMX + Jinja2 templates served by FastAPI (no separate JS framework)
**Alternatives considered:**
- Next.js (React) — rejected: overkill for 3 pages, adds Node.js build pipeline
- SvelteKit — rejected: same concerns, lighter but still a separate frontend build
**Rationale:** The UI is essentially one main page + two secondary pages. HTMX/Jinja2 keeps everything in the Python ecosystem, simplifies deployment to a single backend container, and avoids a Node.js dependency. Charts via Chart.js, confetti via canvas-confetti, sounds via vanilla JS — all work fine without a framework.

### 3. Scraping Approach
**Decision (revised 2026-04-05):** JSON API scraping via httpx (no browser automation)
**Original decision:** Playwright browser automation for all three companies
**What changed:** All companies expose public job board APIs:
- Anthropic: Greenhouse API (`boards-api.greenhouse.io/v1/boards/anthropic/jobs`)
- OpenAI: Ashby API (`api.ashbyhq.com/posting-api/job-board/openai`)
- DeepMind: Greenhouse API (`boards-api.greenhouse.io/v1/boards/deepmind/jobs`)
- xAI: Greenhouse API (`boards-api.greenhouse.io/v1/boards/xai/jobs`)
- Perplexity: Ashby API (`api.ashbyhq.com/posting-api/job-board/perplexity`)
- Meta: metacareers GraphQL (`metacareers.com/graphql` with `doc_id=9114524511922157`, all teams — `teams=[]` / `sub_teams=[]`). Initially scoped to the "Artificial Intelligence" team only; broadened in #38 because the narrow SWE classifier rejects AI-team roles by design, yielding a boring "0 SWE at Meta". Unfiltered, the endpoint returns the full result set (~600 roles) in a single response and signals completion via `extensions.is_final=true`, so no cursor-based pagination is required. More fragile than Greenhouse/Ashby — if Meta rebuilds their frontend the `doc_id` changes — but the only usable JSON surface on metacareers.com.
**Rationale:** JSON APIs are faster, lighter (no browser/Chromium needed), more reliable, and return structured data. The scraper container went from ~1.3GB (with Chromium) to ~580MB. Playwright is no longer a runtime dependency for scraping.

### 4. Job Title Classification
**Decision (revised 2026-04-19):** Local LLM via Ollama using `qwen2.5:1.5b` model with a `/api/chat` call carrying a `SYSTEM` rule + ~30 few-shot user/assistant message pairs. Temperature 0, `num_predict=4` cap.
**Earlier iterations:**
- TinyLlama 1.1B — classified "Account Executive" as SWE. Replaced.
- Gemma2:2b with `/api/generate` and a single string prompt — scored 7/8 on a tiny smoke set.
- Gemma3:270m-it-qat — deployed in prod briefly; measured at 95% recall but only ~4% precision on a hand-labelled ground-truth set of 1381 titles — said "yes" to almost everything.
**What changed:** Switched to `/api/chat` (which uses Ollama's chat template) and supplied the classification rule as a `SYSTEM` message with the examples as alternating user/assistant turns. On 1381 hand-labelled titles, qwen2.5:1.5b with this format scored 97.8% accuracy, 69.8% precision, 72.5% recall — the best Pi-viable result across gemma2:2b, gemma3:1b-it-qat, gemma4:e2b/e4b, llama3.2:1b/3b, qwen2.5:1.5b/3b.
**Why the narrower rule:** the satirical premise ("is Big AI still hiring software engineers?") targets *generic* SWE roles. AI-specific engineering (Applied AI, Research Engineer, Inference, Alignment, AI-product-specific work) and security/infrastructure roles are excluded, because hiring those is orthogonal to Dario's claim.
**Implementation details:**
- Classification runs with configurable parallelism (default 4 concurrent requests via `CLASSIFY_CONCURRENCY`)
- Custom `Containerfile.ollama` bakes the model into the image (no download at runtime)
- GPU support: `nvidia.com/gpu=all` device passthrough + `OLLAMA_VULKAN=1` for NVIDIA GPUs
- `classified_at` timestamp on each posting prevents redundant reclassification on container restart
- Pipeline is split: `fetch` saves raw postings, `classify` runs Ollama separately. `reclassify` forces re-evaluation of all postings.

### 5. Database & ORM
**Decision:** PostgreSQL + SQLAlchemy (async) + Alembic migrations
**Rationale:** Industry standard, well-supported async driver (asyncpg), Alembic provides reliable schema migrations.

### 6. Scrape Scheduling & Run Management
**Decision:** 3x daily scrapes (06:00, 12:00, 18:00 — configurable via `SCRAPE_SCHEDULE`), with retry on failure (exponential backoff, max 3 attempts). All runs tracked in `scrape_runs` table with status lifecycle: `running` → `success` / `failed`. Each company's scrape runs concurrently via `asyncio.gather` (task-level isolation).
**Progress tracking (added 2026-04-05):** `scrape_runs` table has `stage`, `progress_current`, `progress_total` columns. Stages: `fetching` → `saving` → (then separately) `classifying`. The scrapes admin page auto-refreshes every 5s while runs are in progress.
**Pipeline split (added 2026-04-05):** Fetching and classification are independent stages. CLI supports: `fetch [company]`, `classify [company]`, `reclassify [company]`, `run` (full pipeline + scheduler).

### 7. Deduplication
**Decision:** Match postings by (company + URL). Maintain `first_seen_date` and `last_seen_date` per posting. Daily view shows postings where the date falls within their seen range.
**Rationale:** URLs are the most stable identifier for job postings. first/last seen dates give historical visibility into when postings appeared and disappeared.

### 8. Deployment
**Decision:** Podman pod with systemd quadlet units, configurable via `.env` file. Reverse proxy/TLS is an external concern (documented but not containerized). ARM64 compatible (Raspberry Pi target, minimum 8GB RAM recommended).
**Rationale:** User plans to run on a Raspberry Pi. Environment-agnostic configuration means it works on any Linux box. Quadlet units are the modern standard for Podman + systemd integration.
**Persistent volumes:** PostgreSQL data (`arethey-db-data`). Ollama model is baked into the container image (no volume needed).
**Timezone:** All schedule times and date calculations use the `TZ` environment variable (defaults to UTC).
**Dev environment (added 2026-04-05):** `podman-compose.dev.yml` runs all 4 services locally. Uses `scripts/podman-remote.sh` wrapper for toolbox/container environments where `podman --remote` is needed.

### 9. Package Management
**Decision:** `uv` for Python dependency management
**Rationale:** Specified in project requirements. Fast, modern Python package manager.

### 10. Scraping Politeness
**Decision:** User-Agent string identifies the bot (`AreTheyHiringBot/1.0`). Scraping 3x/day via public JSON APIs is a very modest load.
**Note:** Since we switched to public APIs (Greenhouse/Ashby), robots.txt and page-load delays are no longer relevant.

### 11. Scrape Status Page
**Decision:** Added beyond original requirements for operational visibility. Small gear button in top-right corner of all pages.
**Features (expanded 2026-04-05):** Shows stage (fetching/saving/classifying), progress bars with counts, auto-refresh while runs are in progress, error details for failed runs.

### 12. Three-State Home Page (added 2026-04-05)
**Decision:** Home page has three display states instead of binary YES/NO:
- **YES** (green + confetti): At least one scraper found classified SWE postings (checks today first, falls back to yesterday)
- **NO** (red + sirens): At least 2/3 scrapers succeeded and returned 0 SWE postings
- **Unsure** (amber + "..."): Scrapers still running or insufficient data. Shows X/3 scrapers finished, auto-refreshes every 10s.
**Rationale:** Prevents misleading "NO" when scrapers haven't run yet today.

### 13. Collapsible Job Listings (added 2026-04-05)
**Decision:** Day detail page shows company sections collapsed by default. Click to expand and see the full job table.
**Rationale:** The summary (company name + posting count) is more useful at a glance than hundreds of rows.

---

## Architecture

```
┌─────────────────── Podman Pod ───────────────────┐
│                                                    │
│  ┌──────────┐  ┌────────┐  ┌─────────────┐       │
│  │   web    │  │   db   │  │   ollama    │       │
│  │ FastAPI  │  │ Postgres│  │ qwen2.5:1.5b│       │
│  │ :8000    │  │ :5432  │  │ :11434 GPU │       │
│  └──────────┘  └────────┘  └─────────────┘       │
│                                                    │
│  ┌──────────────────────────────────┐             │
│  │       scraper (+ scheduler)      │             │
│  │  APScheduler, runs 3x daily      │             │
│  │  Pipeline: fetch → classify      │             │
│  │                                  │             │
│  │  ┌─────────┐┌────────┐┌───────┐┌────┐┌──────────┐│             │
│  │  │Anthropic││OpenAI  ││DeepMind││xAI ││Perplexity││             │
│  │  │Greenhouse│Ashby   ││Greenhouse│Greenhouse│Ashby │             │
│  │  │  API    ││  API   ││  API  ││ API││  API     ││             │
│  │  └─────────┘└────────┘└───────┘└────┘└──────────┘│             │
│  └──────────────────────────────────┘             │
│                                          :8000 ──►│
└────────────────────────────────────────────────────┘
```

All containers communicate over the pod's shared network.

---

## Data Model

### scrape_runs
| Column           | Type      | Notes                                    |
|------------------|-----------|------------------------------------------|
| id               | UUID      | Primary key                              |
| company          | VARCHAR   | anthropic / openai / deepmind / xai / perplexity / meta       |
| status           | VARCHAR   | running / success / failed               |
| started_at       | TIMESTAMP |                                          |
| finished_at      | TIMESTAMP | Nullable                                 |
| error_message    | TEXT      | Nullable, populated on failure           |
| postings_found   | INTEGER   | Nullable, populated on success           |
| attempt_number   | INTEGER   | 1-3 for retry tracking                   |
| stage            | VARCHAR   | Nullable: fetching / saving / classifying |
| progress_current | INTEGER   | Nullable, current item in stage          |
| progress_total   | INTEGER   | Nullable, total items in stage           |

### job_postings
| Column                 | Type      | Notes                                  |
|------------------------|-----------|----------------------------------------|
| id                     | UUID      | Primary key                            |
| scrape_run_id          | UUID      | FK to scrape_runs                      |
| company                | VARCHAR   | anthropic / openai / deepmind / xai / perplexity / meta    |
| title                  | VARCHAR   | Original job title                     |
| location               | VARCHAR   |                                        |
| url                    | VARCHAR   | Link to original posting               |
| first_seen_date        | DATE      | First day this posting was observed    |
| last_seen_date         | DATE      | Most recent day this posting was seen  |
| is_software_engineering| BOOLEAN   | Classified by Ollama                   |
| classified_at          | TIMESTAMP | Nullable, when classification was done |

**Dedup key:** (company, url) — on conflict, update `last_seen_date` and `scrape_run_id`.
**Classification:** Only postings with `classified_at IS NULL` are classified on normal runs. `reclassify` ignores this and re-evaluates all postings.

---

## UI Pages

### Home (`/`)
- Heading: "Is Big AI still hiring Software Engineers?"
- Dynamic counter: months/days since Dario Amodei's claim (epoch: 2025-03-14, link to Business Insider article)
- Three-state display:
  - **YES** (green pulse, confetti on load, "click to celebrate" sound button): at least one scraper found SWE postings
  - **NO** (red flash, siren animation, warning triangle, "click to panic" sound button): 2/3+ scrapers succeeded with 0 postings
  - **Unsure** (amber pulse, "..." display, scraper progress summary, auto-refresh 10s): insufficient data
- Chart.js bar chart: posting counts by date, warning triangles for zero days, clickable bars → day detail
- Gear button → scrape status page

### Day Detail (`/day/<YYYY-MM-DD>`)
- Back button to home
- Total posting count for the date
- Company sections **collapsed by default**, click to expand
- Each section shows: company name, posting count, expandable job table (title, location, link)
- Gear button → scrape status

### Scrape Status (`/scrapes`)
- Back button to home
- Table: time, company, status (with icons), stage + progress bar, found count, duration
- Auto-refreshes every 5s while any run is in progress
- Error details shown inline for failed runs

### About (`/about`)
- Static Jinja2 template (no DB access). Explains the site's satirical framing,
  lists the six tracked companies, summarises the classification rule, flags
  methodology caveats, and links to the repo.
- Reachable via the info glyph in the top-right nav, next to the settings cog.

---

## Testing Strategy

### Integration Tests (pytest) — 40 tests
- **Scrapers:** Mock httpx responses with JSON fixtures matching Greenhouse/Ashby API format
- **Classifier:** Mock httpx responses to Ollama API via pytest-httpx
- **Scheduler:** Test fetch_and_save (success + retry), classify_postings, reclassify (force)
- **API:** FastAPI TestClient, test all 3 pages + health endpoint, 3-state home page logic
- **Database:** Model creation, dedup constraint, session factory, upsert, aggregation queries

### E2E Tests (Playwright)
- Home page YES/NO state rendering, counter, chart, scrape status link
- Day detail loads with back link
- Scrape status loads with table
- **Note:** E2E tests require `make test-env-up` (podman-compose test environment)

### Test Infrastructure
- `podman-compose.test.yml` for E2E environment
- All integration tests use SQLite in-memory (no external dependencies)
- Single entry point: `make test`

---

## Container Images

| Image   | Containerfile          | Base                 | Contents                                   |
|---------|------------------------|----------------------|--------------------------------------------|
| web     | Containerfile.web      | python:3.12-slim     | FastAPI app, templates, static, Alembic    |
| scraper | Containerfile.scraper  | python:3.12-slim     | Scrapers (httpx), scheduler, classifier    |
| db      | (stock)                | postgres:16          | PostgreSQL                                 |
| ollama  | Containerfile.ollama   | ollama/ollama:latest | Ollama + qwen2.5:1.5b baked in (no download) |

**Note:** Web container runs `scripts/web-entrypoint.sh` which applies Alembic migrations before starting uvicorn.

---

## Configuration (.env)

```
# General
TZ=UTC

# Database
POSTGRES_USER=arethey
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=arethey
DATABASE_URL=postgresql+asyncpg://arethey:changeme@localhost:5432/arethey

# Web
WEB_PORT=8000
BASE_URL=http://localhost:8000

# Scraper
SCRAPE_SCHEDULE=06:00,12:00,18:00
SCRAPE_RETRY_MAX=3

# Ollama
OLLAMA_MODEL=qwen2.5:1.5b
OLLAMA_HOST=http://localhost:11434
CLASSIFY_CONCURRENCY=4

# Company APIs (auto-configured, override if needed)
# Anthropic:  boards-api.greenhouse.io/v1/boards/anthropic/jobs
# OpenAI:     api.ashbyhq.com/posting-api/job-board/openai
# DeepMind:   boards-api.greenhouse.io/v1/boards/deepmind/jobs
# xAI:        boards-api.greenhouse.io/v1/boards/xai/jobs
# Perplexity: api.ashbyhq.com/posting-api/job-board/perplexity
# Meta:       metacareers.com/graphql (POST, doc_id 9114524511922157, teams=[] / sub_teams=[] — all roles)
```

---

## CLI Commands

The scraper module doubles as a CLI tool:

```bash
# Full pipeline + scheduler (default, used by container CMD)
python -m src.scrapers.scheduler run

# Fetch only (save raw postings, no classification)
python -m src.scrapers.scheduler fetch [company]

# Classify only new (unclassified) postings
python -m src.scrapers.scheduler classify [company]

# Reclassify ALL postings (force, ignores classified_at)
python -m src.scrapers.scheduler reclassify [company]
```

Makefile shortcuts: `make fetch`, `make classify`, `make reclassify`

---

## Project Structure

```
are-they-hiring/
├── pyproject.toml
├── alembic.ini
├── .env.example
├── Makefile
├── Containerfile.web                  # FastAPI app image
├── Containerfile.scraper              # Scrapers + scheduler image
├── Containerfile.ollama               # Ollama + bundled qwen2.5:1.5b
├── podman-compose.dev.yml             # Local dev environment (4 services)
├── podman-compose.test.yml            # E2E test environment
├── scripts/
│   ├── web-entrypoint.sh              # Runs migrations then uvicorn
│   └── podman-remote.sh               # Wrapper for podman --remote
├── podman/
│   ├── pod.yml                        # Podman play kube definition
│   └── systemd/                       # Quadlet units for systemd
│       ├── are-they-hiring.pod
│       ├── are-they-hiring-web.container
│       ├── are-they-hiring-db.container
│       ├── are-they-hiring-ollama.container
│       └── are-they-hiring-scraper.container
├── src/
│   ├── config.py                      # Pydantic settings from .env
│   ├── db/
│   │   ├── models.py                  # ScrapeRun, JobPosting
│   │   ├── session.py                 # Async session factory
│   │   ├── queries.py                 # Upsert, aggregation, scrape summary
│   │   └── migrations/                # Alembic (3 migrations)
│   ├── classifier/
│   │   └── client.py                  # Parallel Ollama classification
│   ├── scrapers/
│   │   ├── base.py                    # BaseScraper ABC (httpx + JSON)
│   │   ├── anthropic.py               # Greenhouse API parser
│   │   ├── openai_scraper.py          # Ashby API parser
│   │   ├── deepmind.py                # Greenhouse API parser
│   │   ├── xai.py                     # Greenhouse API parser
│   │   ├── perplexity.py              # Ashby API parser (thin subclass of openai_scraper)
│   │   ├── meta.py                     # metacareers GraphQL parser (doc_id persisted-query, all teams)
│   │   └── scheduler.py               # fetch/classify/reclassify + APScheduler
│   └── web/
│       ├── app.py                     # FastAPI app factory + routes
│       ├── templates/                 # Jinja2 (base, home, day_detail, scrape_status, about)
│       └── static/                    # CSS, JS, sound placeholders
├── tests/
│   ├── conftest.py                    # SQLite in-memory db_session fixture
│   ├── integration/                   # 40 tests (scrapers, classifier, API, DB, scheduler)
│   ├── e2e/                           # Playwright browser tests
│   └── fixtures/
│       ├── html_snapshots/            # (legacy, from Playwright era)
│       └── seed_data.sql              # E2E test seed data
└── docs/
    └── superpowers/plans/             # Implementation plan (historical)
```
