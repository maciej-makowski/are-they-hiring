# Are They Still Hiring Software Engineers?

A satirical web app that scrapes job postings from Anthropic, OpenAI, and Google DeepMind, classifies them using a local LLM, and displays whether Big AI is still hiring software engineers — with a countdown since Dario Amodei claimed AI would replace all software engineers.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [Podman](https://podman.io/) (container runtime)
- [podman-compose](https://github.com/containers/podman-compose) (`uv tool install podman-compose`)
- NVIDIA GPU (optional, for faster LLM classification)

## Quick Start (Dev Environment)

```bash
# 1. Clone and install Python dependencies
git clone <repo-url> && cd are-they-hiring
uv sync --all-extras

# 2. Start all services (PostgreSQL, Ollama w/ gemma2:2b, web app, scraper)
podman-compose -f podman-compose.dev.yml up -d

# 3. Open in browser
open http://localhost:8000
```

The web container auto-runs database migrations on startup. The scraper fetches from all 3 company APIs and classifies titles via Ollama immediately, then on the configured schedule.

### Port Mappings

| Service    | Port  | Notes                              |
|------------|-------|------------------------------------|
| Web        | 8000  | Main UI                            |
| PostgreSQL | 5433  | Mapped to 5433 to avoid conflicts  |
| Ollama     | 11435 | Mapped to 11435 to avoid conflicts |

### Podman Remote (Toolbox/Container Environments)

If you're running inside a toolbox or container where `podman` needs `--remote`, use the wrapper:

```bash
podman-compose --podman-path ./scripts/podman-remote.sh -f podman-compose.dev.yml up -d
```

## Running Tests

### Integration Tests (no external dependencies)

```bash
make test
```

All 40 integration tests use SQLite in-memory — no PostgreSQL or Ollama needed.

### E2E Tests (requires running dev environment)

```bash
# Start test environment
make test-env-up

# Run E2E tests
make test-e2e

# Tear down
make test-env-down
```

## Linting & Formatting

The project uses [ruff](https://docs.astral.sh/ruff/) for linting, formatting, and import sorting.

```bash
# Check for issues (CI runs this)
make lint

# Auto-fix everything
make lint-fix
```

**Rules enabled:** pycodestyle, pyflakes, isort (import sorting), pyupgrade, flake8-bugbear, flake8-simplify. Config is in `pyproject.toml` under `[tool.ruff]`.

**On PRs:** A GitHub Action automatically fixes lint/formatting issues and commits them back to the branch.

## Scraper CLI

The scraper supports independent fetch and classify stages, useful for iterating on classification without re-fetching:

```bash
# Fetch job postings from all companies (no classification)
make fetch

# Fetch from a specific company
make fetch company=anthropic

# Classify new (unclassified) postings
make classify

# Reclassify ALL postings (e.g., after changing model or prompt)
make reclassify

# Reclassify a specific company
make reclassify company=openai
```

These commands need `DATABASE_URL` and `OLLAMA_HOST` set (via `.env` file or environment). You can also run them inside the scraper container:

```bash
podman exec are-they-hiring_scraper_1 uv run python -m src.scrapers.scheduler reclassify
```

## Building Container Images

```bash
make build
```

This builds:
- `are-they-hiring-web` — FastAPI app (runs migrations on start)
- `are-they-hiring-scraper` — Scheduler + scrapers + classifier

The Ollama image (`Containerfile.ollama`) is built automatically by `podman-compose` and includes the gemma2:2b model baked in.

## Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Key settings:

| Variable              | Default                | Description                      |
|-----------------------|------------------------|----------------------------------|
| `DATABASE_URL`        | `postgresql+asyncpg://arethey:changeme@...` | PostgreSQL connection |
| `OLLAMA_MODEL`        | `gemma2:2b`            | LLM model for classification     |
| `OLLAMA_HOST`         | `http://localhost:11434` | Ollama API endpoint            |
| `CLASSIFY_CONCURRENCY`| `4`                    | Parallel Ollama requests         |
| `SCRAPE_SCHEDULE`     | `06:00,12:00,18:00`   | Cron times for scraping (UTC)    |
| `SCRAPE_RETRY_MAX`    | `3`                    | Max retry attempts per scrape    |
| `TZ`                  | `UTC`                  | Timezone for schedules           |

## Database Migrations

```bash
# Apply pending migrations
make migrate

# Generate a new migration after model changes
make revision msg="describe the change"
```

## Production Deployment (Raspberry Pi / Linux)

Systemd quadlet units are provided in `podman/systemd/`. To deploy:

```bash
# Build images
make build
podman build -f Containerfile.ollama -t are-they-hiring-ollama .

# Copy quadlet units
cp podman/systemd/* ~/.config/containers/systemd/

# Create .env for the service
mkdir -p ~/.config/are-they-hiring
cp .env ~/.config/are-they-hiring/.env
# Edit: set a real POSTGRES_PASSWORD

# Reload and start
systemctl --user daemon-reload
systemctl --user start are-they-hiring-pod.service
```

## Architecture

```
PostgreSQL ← Web (FastAPI + Jinja2) → Browser
     ↑
Scraper (APScheduler) → Greenhouse/Ashby APIs
     ↓
Ollama (gemma2:2b, GPU) → Classification
```

- **Web**: FastAPI serves HTMX/Jinja2 pages with Chart.js and confetti
- **Scraper**: Fetches from Greenhouse (Anthropic, DeepMind) and Ashby (OpenAI) JSON APIs
- **Classifier**: Parallel Ollama requests to classify job titles as SWE or not
- **Database**: PostgreSQL with deduplication by (company, URL), first/last seen tracking

See `Implementation.md` for detailed design decisions and rationale.

## Next Steps

- **Classification quality**: Review edge cases (e.g., "Developer Community Lead", "Finance Systems Integration Engineer") and refine the Ollama prompt or try a larger model
- **Sound effects**: Replace empty placeholder MP3s (`src/web/static/sounds/`) with actual audio — a fanfare for YES, an alarm for NO
- **E2E tests**: Run the Playwright E2E suite against the live dev environment (`make test-env-up && make test-e2e`)
- **Fix Starlette deprecation**: Update `TemplateResponse(name, {request: ...})` calls to the new `TemplateResponse(request, name)` signature
- **More companies**: Add scrapers for additional AI companies (xAI, Meta AI, etc.)
- **Historical charts**: Improve the daily counts chart to show trends over weeks/months
