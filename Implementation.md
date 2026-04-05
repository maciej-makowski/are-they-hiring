# Implementation Design Document

**Project:** are-they-still-hiring-software-engineers.com
**Date:** 2026-03-13
**Status:** Approved, ready for implementation

---

## Decision Log

### 1. Target Companies
**Decision:** Anthropic, OpenAI, Google DeepMind
**Rationale:** The three most prominent AI companies making bold claims about AI replacing software engineers. Direct relevance to the project's satirical premise.

### 2. Frontend Technology
**Decision:** HTMX + Jinja2 templates served by FastAPI (no separate JS framework)
**Alternatives considered:**
- Next.js (React) — rejected: overkill for 3 pages, adds Node.js build pipeline
- SvelteKit — rejected: same concerns, lighter but still a separate frontend build
**Rationale:** The UI is essentially one main page + two secondary pages. HTMX/Jinja2 keeps everything in the Python ecosystem, simplifies deployment to a single backend container, and avoids a Node.js dependency. Charts via Chart.js, confetti via canvas-confetti, sounds via vanilla JS — all work fine without a framework.

### 3. Scraping Approach
**Decision:** Playwright browser automation for all three companies
**Alternatives considered:**
- Direct HTTP scraping (BeautifulSoup) — rejected: modern career pages rely heavily on JS rendering
- Reverse-engineering careers APIs — rejected: user preference to check actual websites directly
**Rationale:** Consistent approach across all targets. Playwright handles JS-rendered content reliably. Already needed for E2E tests so it's not an additional dependency. Each company gets its own scraper module.

### 4. Job Title Classification
**Decision:** Local LLM via Ollama (lightweight model, e.g. Gemma 2B or TinyLlama 1.1B for ARM64/Pi, or Phi-3-mini for x86)
**Alternatives considered:**
- Keyword matching on titles — rejected: misses edge cases, requires ongoing list maintenance
- Cloud LLM API calls — rejected: adds cost and external dependency
- Sentence-transformers embeddings — rejected: less flexible than a generative model
**Rationale:** Ollama runs as a container in the pod, fits the architecture naturally. Even a 1-2B model is sufficient for binary classification of job titles. Handles edge cases like "Developer Experience Lead" or "Build Systems Architect" gracefully.
**ARM64/Pi note:** On Raspberry Pi (minimum 8GB RAM recommended), use a smaller model (TinyLlama 1.1B or Gemma 2B) to keep memory pressure manageable alongside PostgreSQL and Playwright. The `OLLAMA_MODEL` env var controls which model is used. Ollama model storage uses a persistent volume to avoid re-downloading on restart.

### 5. Database & ORM
**Decision:** PostgreSQL + SQLAlchemy (async) + Alembic migrations
**Rationale:** Industry standard, well-supported async driver (asyncpg), Alembic provides reliable schema migrations.

### 6. Scrape Scheduling & Run Management
**Decision:** 3x daily scrapes (06:00, 12:00, 18:00 — configurable via `SCRAPE_SCHEDULE`), with retry on failure (exponential backoff, max 3 attempts). All runs tracked in `scrape_runs` table with status lifecycle: `pending` → `running` → `success` / `failed`. Each company's scrape runs as an independent scheduled job within the scheduler container (task-level isolation, not process-level — keeps deployment simple while ensuring one company's failure doesn't block others).
**Rationale:** Multiple daily runs provide resilience against downtime. Full run tracking enables the scrape status UI page and aids debugging. Task-level isolation is a pragmatic choice over separate containers per scraper, avoiding 3 extra Playwright container images while preserving independent failure handling.

### 7. Deduplication
**Decision:** Match postings by (company + URL). Maintain `first_seen_date` and `last_seen_date` per posting. Daily view shows postings where the date falls within their seen range.
**Rationale:** URLs are the most stable identifier for job postings. first/last seen dates give historical visibility into when postings appeared and disappeared.

### 8. Deployment
**Decision:** Podman pod with systemd quadlet units, configurable via `.env` file. Reverse proxy/TLS is an external concern (documented but not containerized). ARM64 compatible (Raspberry Pi target, minimum 8GB RAM recommended).
**Rationale:** User plans to run on a Raspberry Pi. Environment-agnostic configuration means it works on any Linux box. Quadlet units are the modern standard for Podman + systemd integration.
**Persistent volumes:** PostgreSQL data (`are-they-hiring-db-data`) and Ollama models (`are-they-hiring-ollama-models`) use named Podman volumes to survive container restarts.
**Timezone:** All schedule times and "yesterday" calculations use the `TZ` environment variable (defaults to UTC).

### 9. Package Management
**Decision:** `uv` for Python dependency management
**Rationale:** Specified in project requirements. Fast, modern Python package manager.

### 10. Scraping Politeness
**Decision:** Respect `robots.txt` where possible. Add configurable delay between page loads (default 2s). User-Agent string identifies the bot. Scraping 3x/day is a very modest load.
**Rationale:** Good citizenship. These are public career pages with low request volume.

### 11. Playwright on ARM64
**Decision:** The scraper Containerfile uses Debian-based image with Chromium installed from distro packages (`chromium` apt package) rather than Playwright's bundled browsers. Playwright is configured with `PLAYWRIGHT_BROWSERS_PATH` pointing to the system Chromium.
**Rationale:** Playwright's bundled Chromium has inconsistent ARM64 Linux support. Debian's Chromium package reliably supports ARM64. This is a well-documented pattern for running Playwright on ARM.

### 12. Scrape Status Page
**Decision:** Added beyond original requirements for operational visibility. Small button in top-right corner of all pages.
**Rationale:** User-requested addition during design. Helps monitor system health on a headless Pi deployment.

---

## Architecture

```
┌─────────────────── Podman Pod ───────────────────┐
│                                                    │
│  ┌──────────┐  ┌────────┐  ┌────────┐            │
│  │   web    │  │   db   │  │ ollama │            │
│  │ FastAPI  │  │ Postgres│  │  3B    │            │
│  │ :8000    │  │ :5432  │  │ :11434 │            │
│  └──────────┘  └────────┘  └────────┘            │
│                                                    │
│  ┌──────────────────────────────────┐             │
│  │       scraper (+ scheduler)      │             │
│  │  APScheduler, runs 3x daily      │             │
│  │                                  │             │
│  │  ┌─────────┐┌────────┐┌───────┐ │             │
│  │  │Anthropic││OpenAI  ││DeepMind│ │             │
│  │  │scraper  ││scraper ││scraper │ │             │
│  │  └─────────┘└────────┘└───────┘ │             │
│  └──────────────────────────────────┘             │
│                                          :8000 ──►│
└────────────────────────────────────────────────────┘
```

All containers communicate over the pod's shared localhost network.

---

## Data Model

### scrape_runs
| Column         | Type      | Notes                              |
|----------------|-----------|------------------------------------|
| id             | UUID      | Primary key                        |
| company        | VARCHAR   | anthropic / openai / deepmind      |
| status         | VARCHAR   | pending / running / success / failed |
| started_at     | TIMESTAMP |                                    |
| finished_at    | TIMESTAMP | Nullable                           |
| error_message  | TEXT      | Nullable, populated on failure     |
| postings_found | INTEGER   | Nullable, populated on success     |
| attempt_number | INTEGER   | 1-3 for retry tracking             |

### job_postings
| Column                 | Type    | Notes                                  |
|------------------------|---------|----------------------------------------|
| id                     | UUID    | Primary key                            |
| scrape_run_id          | UUID    | FK to scrape_runs                      |
| company                | VARCHAR | anthropic / openai / deepmind          |
| title                  | VARCHAR | Original job title                     |
| location               | VARCHAR |                                        |
| url                    | VARCHAR | Link to original posting               |
| first_seen_date        | DATE    | First day this posting was observed    |
| last_seen_date         | DATE    | Most recent day this posting was seen  |
| is_software_engineering| BOOLEAN | Classified by Ollama                   |

**Dedup key:** (company, url) — on conflict, update `last_seen_date` and `scrape_run_id`.

---

## UI Pages

### Home (`/`)
- Dynamic counter: "We are X months Y days since Dario Amodei said all code will be written by AI in 6 months" (link to Business Insider article, epoch: 2025-03-14)
- Large YES (green, confetti, funny sound) or NO (red, sirens, warning lights) based on yesterday's data
  - **YES state:** Green background with subtle pulse animation. `canvas-confetti` library fires on page load. Funny victory sound (small MP3, triggered by user click — "click to celebrate" button to respect autoplay policies).
  - **NO state:** Red background with CSS `@keyframes` flashing red/amber siren animation (rotating gradient simulating warning lights). Alarm sound (same click-to-play pattern). Large warning triangle icon.
- Chart.js bar chart: green bars = posting count by date. Zero-posting days rendered via Chart.js custom plugin that draws a warning triangle (⚠️) at the x-axis position instead of a bar.
- Clickable bars navigate to day detail page
- Small gear/wrench button in top-right corner links to scrape status page

### Day Detail (`/day/<YYYY-MM-DD>`)
- Back button to home
- Total posting count for the date
- Breakdown by company
- Sortable/filterable table: company, title, location, link
- Scrape status button in top-right

### Scrape Status (`/scrapes`)
- Back button to home
- Paginated table of recent scrape runs: time, company, status, postings found, duration
- Expandable error details on failed runs

---

## Testing Strategy

### Integration Tests (pytest)
- **Scrapers:** Mock Playwright with saved HTML snapshots, verify correct parsing
- **Classifier:** Test Ollama client against fixture job titles with expected results (uses real Ollama in test pod)
- **API:** FastAPI TestClient, test endpoints, aggregation, edge cases
- **Database:** Deduplication logic, first/last seen updates, daily queries

### E2E Tests (Playwright)
- Home page YES/NO state rendering
- Counter date math correctness
- Chart rendering and click navigation
- Day detail breakdown and table
- Scrape status page

### Test Infrastructure
- `podman-compose.test.yml` spins up test pod (PostgreSQL + Ollama + app)
- Scrapers tested in isolation with mocked browser responses
- Single entry point: `make test`

---

## Container Images

| Image          | Base                    | Contents                          |
|----------------|-------------------------|-----------------------------------|
| web            | python:3.12-slim        | FastAPI app, templates, static    |
| scraper        | python:3.12-slim + Playwright | Scrapers, scheduler, browser |
| db             | postgres:16 (stock)     | PostgreSQL                        |
| ollama         | ollama/ollama (stock)   | Ollama + model (persistent volume, pulled if missing) |

---

## Configuration (.env)

```
# General
TZ=UTC

# Database
POSTGRES_USER=arethey
POSTGRES_PASSWORD=<generated>
POSTGRES_DB=arethey

# Web
WEB_PORT=8000
BASE_URL=http://localhost:8000

# Scraper
SCRAPE_SCHEDULE=06:00,12:00,18:00
SCRAPE_RETRY_MAX=3
SCRAPE_DELAY_SECONDS=2

# Ollama
OLLAMA_MODEL=tinyllama:1.1b  # use phi3:mini on x86 with more RAM
OLLAMA_HOST=localhost:11434

# Companies (career page URLs)
ANTHROPIC_CAREERS_URL=https://www.anthropic.com/careers
OPENAI_CAREERS_URL=https://openai.com/careers
DEEPMIND_CAREERS_URL=https://deepmind.google/about/careers/
```

---

## Project Structure

```
are-they-hiring/
├── pyproject.toml
├── .env.example
├── Makefile
├── Containerfile.web
├── Containerfile.scraper
├── podman/
│   ├── pod.yaml
│   └── systemd/
│       ├── are-they-hiring.pod
│       ├── are-they-hiring-web.container
│       ├── are-they-hiring-db.container
│       ├── are-they-hiring-ollama.container
│       └── are-they-hiring-scraper.container
├── src/
│   ├── web/
│   │   ├── app.py
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── home.html
│   │   │   ├── day_detail.html
│   │   │   └── scrape_status.html
│   │   └── static/
│   │       ├── style.css
│   │       ├── app.js
│   │       └── sounds/
│   │           ├── victory.mp3
│   │           └── alarm.mp3
│   ├── scrapers/
│   │   ├── base.py
│   │   ├── anthropic.py
│   │   ├── openai_scraper.py
│   │   ├── deepmind.py
│   │   └── scheduler.py
│   ├── classifier/
│   │   └── client.py
│   └── db/
│       ├── models.py
│       ├── session.py
│       └── migrations/
├── tests/
│   ├── integration/
│   │   ├── test_scrapers.py
│   │   ├── test_classifier.py
│   │   ├── test_api.py
│   │   └── test_db.py
│   ├── e2e/
│   │   ├── test_home.py
│   │   ├── test_day_detail.py
│   │   └── test_scrape_status.py
│   └── fixtures/
│       ├── html_snapshots/
│       └── seed_data.sql
└── podman-compose.test.yml
```
