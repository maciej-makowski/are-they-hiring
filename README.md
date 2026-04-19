# Are They Still Hiring Software Engineers?

A satirical web app that scrapes job postings from Anthropic, OpenAI, Google DeepMind, xAI, Perplexity, and Meta, classifies them using a local LLM, and displays whether Big AI is still hiring software engineers — with a countdown since Dario Amodei claimed AI would replace all software engineers.

> **Contributing?** Read [`AGENTS.md`](AGENTS.md) first — it lays out the repo conventions (branches, commits, tests, docs) both humans and AI agents should follow.

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

# 2. Start all services (PostgreSQL, Ollama w/ gemma3:270m, web app, scraper)
podman-compose -f podman-compose.dev.yml up -d

# 3. Open in browser
open http://localhost:8000
```

The web container auto-runs database migrations on startup. The scraper fetches from all 5 company APIs and classifies titles via Ollama immediately, then on the configured schedule.

### Port Mappings

| Service    | Port  | Notes                              |
|------------|-------|------------------------------------|
| Web        | 8000  | Main UI                            |
| PostgreSQL | 5433  | Mapped to 5433 to avoid conflicts  |
| Ollama     | 11435 | Mapped to 11435 to avoid conflicts |

### Data Persistence

Database data is stored in a named Podman volume (`are-they-hiring_arethey-db-data`) and survives container restarts. To wipe the database and start fresh:

```bash
podman-compose --podman-path ./scripts/podman-remote.sh -f podman-compose.dev.yml down -v
```

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

### Pre-commit Hooks

Lint fixes and tests run automatically before every commit:

```bash
# Install hooks (one-time, after cloning)
uv run pre-commit install

# Run manually on all files
uv run pre-commit run --all-files
```

Hooks: ruff lint (auto-fix), ruff format, integration tests.

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

The Ollama image (`Containerfile.ollama`) is built automatically by `podman-compose` and includes the qwen2.5:1.5b model baked in.

## Configuration

Copy `.env.example` to `.env` and adjust:

```bash
cp .env.example .env
```

Key settings:

| Variable              | Default                | Description                      |
|-----------------------|------------------------|----------------------------------|
| `DATABASE_URL`        | `postgresql+asyncpg://arethey:changeme@...` | PostgreSQL connection |
| `OLLAMA_MODEL`        | `qwen2.5:1.5b`   | LLM model for classification     |
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

Two deployment methods are available:

### Raspberry Pi prerequisites

Before deploying on a Pi, verify Podman is using the `overlay` storage driver, not `vfs`. `vfs` makes container operations catastrophically slow (full layer copies on every start).

```bash
podman info | grep graphDriverName
```

If it reports `vfs`, switch to overlay. Edit `~/.config/containers/storage.conf`:

```toml
[storage]
driver = "overlay"

[storage.options.overlay]
mount_program = "/usr/bin/fuse-overlayfs"
```

Install `fuse-overlayfs` if needed (`sudo apt install fuse-overlayfs`), then reset storage:

```bash
podman system reset --force
podman info | grep graphDriverName  # should now report "overlay"
```

### Option A: podman-compose (works with Podman 4.3+)

Best for Raspberry Pi and older systems. Requires `podman-compose` installed (`pip install podman-compose`).

```bash
# Allow user-scope systemd units to keep running after SSH logout.
# Without this, the stack will stop when you disconnect.
sudo loginctl enable-linger $USER

# Build images and install systemd service
make install-compose

# Edit .env with real credentials
nano ~/.config/are-they-hiring/.env

# Start and enable on boot
systemctl --user start are-they-hiring-compose.service
systemctl --user enable are-they-hiring-compose.service

# View logs
journalctl --user -u are-they-hiring-compose.service -f

# Uninstall (preserves data and .env)
make uninstall-compose
```

### Option B: Quadlet units (requires Podman 4.4+)

Native systemd integration, no podman-compose needed.

```bash
# Build images and install quadlet units
make install

# Edit .env with real credentials
nano ~/.config/are-they-hiring/.env

# Start
systemctl --user start are-they-hiring-pod.service

# View logs
journalctl --user -u are-they-hiring-web.service -f

# Uninstall (preserves data and .env)
make uninstall
```

### GPU support

GPU acceleration is disabled by default. To enable on NVIDIA systems:
- **Quadlet:** Uncomment `AddDevice` and `OLLAMA_*` lines in `~/.config/containers/systemd/are-they-hiring-ollama.container`
- **Compose:** Add `devices: [nvidia.com/gpu=all]` and GPU env vars to the ollama service in `~/.config/are-they-hiring/compose.yml`

### Updating

After pulling new code:
```bash
make build-all
# Then restart: systemctl --user restart are-they-hiring-compose.service
# Or for quadlets: systemctl --user restart are-they-hiring-pod.service
```

## Architecture

```
PostgreSQL ← Web (FastAPI + Jinja2) → Browser
     ↑
Scraper (APScheduler) → Greenhouse/Ashby APIs
     ↓
Ollama (gemma3:270m, CPU/GPU) → Classification
```

- **Web**: FastAPI serves HTMX/Jinja2 pages with Chart.js and confetti
- **Scraper**: Fetches from Greenhouse (Anthropic, DeepMind, xAI), Ashby (OpenAI, Perplexity), and metacareers GraphQL (Meta — all teams, unfiltered)
- **Classifier**: Parallel Ollama requests to classify job titles as SWE or not
- **Database**: PostgreSQL with deduplication by (company, URL), first/last seen tracking

See `Implementation.md` for detailed design decisions and rationale.

## Roadmap

See [`docs/ROADMAP.md`](docs/ROADMAP.md) for the backlog of planned features and maintenance items.
