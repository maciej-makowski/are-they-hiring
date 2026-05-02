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

The Ollama image (`Containerfile.ollama`) is built automatically by `podman-compose` and bakes in both models the classifier uses: `qwen2.5:1.5b` (LLM confirm stage) and `all-minilm` (SVM pre-filter embeddings).

## Classifier pre-filter

A LinearSVC pre-filter runs before the LLM on the classification path (see issue #45, `src/classifier/prefilter.py`, `classifier/prefilter.json.gz`). Titles the SVM classifies as confidently-not-SWE short-circuit to `False` without an LLM call; the rest fall through to qwen2.5:1.5b. Cuts LLM call volume ~5× during reclassify.

The model ships as a compressed JSON file (~4 KiB) alongside the training data (`classifier/training_data.csv.gz`). Retrain on demand:

```bash
make retrain-prefilter       # rebuilds classifier/prefilter.json.gz
make eval-prefilter          # re-runs CV without writing a new model
```

Toggle off with `CLASSIFIER_PREFILTER_ENABLED=false` for LLM-only classification.

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

Three deployment methods are available — pick one based on the host's Podman version:

- **Option A** (Podman 4.3+): podman-compose under a single systemd service. Pi 4 runs this.
- **Option B** (Podman 4.4+): static quadlet units committed in `podman/systemd/`, installed via `make install`. Manual `.env` editing.
- **Option C** (Podman 5+, recommended): native quadlets rendered from a profile (`deploy/profiles/pi5.yml`). Pi 5 runs this.

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

#### Profile-based deploy (recommended)

Per-environment configuration lives in `deploy/profiles/<name>.yml` and is rendered into the `.env`, `compose.yml`, and systemd unit via Jinja2 templates. Secrets stay in a separate file outside the repo (`secrets_env_path:` in the profile, pointing at e.g. `~/.config/are-they-hiring/secrets.env`).

```bash
# Allow user-scope systemd units to keep running after SSH logout.
sudo loginctl enable-linger $USER

# Build images first (one-off)
make build-all

# Preview what will be deployed (renders + diffs, does not apply)
make deploy-render PROFILE=pi

# Apply locally (renders, writes to ~/.config/..., reloads + restarts)
make deploy PROFILE=pi

# Or deploy over SSH from your dev machine to the Pi
make deploy PROFILE=pi HOST=cfiet@192.168.1.2

# View logs
journalctl --user -u are-they-hiring-compose.service -f

# Uninstall (preserves data and .env)
make uninstall-compose
```

The renderer:
- Validates the profile against a pydantic schema (typos in YAML fail fast).
- Merges in secrets from `secrets_env_path` at apply time (never templated into committed files).
- Warns if the live `.env` has orphan keys that aren't in the profile.
- Refuses to overwrite if the live `compose.yml` or systemd unit has been hand-edited since the repo's last commit.

See `deploy/profiles/pi.yml` for the current Pi profile — that's where you tweak `OLLAMA_MODEL`, CPU prioritisation, scrape schedule, etc.

#### Legacy flow (deprecated)

`make install-compose` still works but is deprecated — it copies the static `podman-compose.prod.yml` and `.env.example` without any env-specific rendering.

```bash
make install-compose
nano ~/.config/are-they-hiring/.env
systemctl --user start are-they-hiring-compose.service
systemctl --user enable are-they-hiring-compose.service
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

### Option C: Quadlet via profile renderer (Podman 5+, recommended)

Same idea as Option A but emits **native quadlet files** (`.pod` + `.container`) under `~/.config/containers/systemd/` instead of a `compose.yml` + wrapper service. No `podman-compose` indirection at runtime; the pod starts via its own systemd unit and cascades to the four containers. Requires Podman 5+ for the quadlet feature-set used (pod `PublishPort=`, container `Pod=` reference).

```bash
# Allow user-scope systemd units to keep running after SSH logout (one-time).
sudo loginctl enable-linger $USER

# Build images on the target host (one-off; the pod references localhost/are-they-hiring-{web,scraper,ollama}:latest).
make build-all

# Preview the rendered quadlets (diffs against live ~/.config/containers/systemd/...).
make deploy-render PROFILE=pi5

# Apply locally (writes quadlets, daemon-reload, restart pod).
make deploy PROFILE=pi5

# Or apply over SSH from a dev box.
make deploy PROFILE=pi5 HOST=cfiet@192.168.1.3
```

**One-time migration from Option A** (the Pi 5's path — it ran compose first):

```bash
make migrate-to-quadlet HOST=cfiet@192.168.1.3
```

The script stops + disables `are-they-hiring-compose.service`, **copies the DB volume from `are-they-hiring_arethey-db-data` (compose project-prefixed) to `are-they-hiring-db-data` (quadlet name)**, removes the stale compose unit + `compose.yml`, then runs `make deploy PROFILE=pi5 HOST=...`. Idempotent — re-running on a migrated box is a no-op.

The volume rename is the load-bearing step. podman-compose names volumes `<project>_<volume>`, but the quadlet `db.container` declares `Volume=are-they-hiring-db-data:/var/lib/postgresql/data` — a different name. Without the copy step the new pod would start against an empty volume and Postgres would auto-init from scratch (data loss).

**Inspect after deploy:**

```bash
# Containers managed by the pod
podman ps --format 'table {{.Names}} {{.Status}}'

# Generated systemd units (regenerated on every daemon-reload from the .container/.pod files)
systemctl --user list-units 'are-they-hiring-*'

# Pod-level logs
journalctl --user -u are-they-hiring-pod.service -f
```

See `deploy/profiles/pi5.yml` for the Pi 5 tuning (4-thread Cortex-A76 cores, `flash_attention=true`, `kv_cache_type=q8_0`, no CPU cap).

### Public access via Cloudflare Tunnel

To expose the running stack on a public hostname (HTTPS, no inbound ports forwarded on the router) attach a Cloudflare Tunnel. The tunnel runs as its own system-scope `cloudflared.service`, separate from the user-scope podman service that hosts the app.

**Prerequisite:** the chosen domain (e.g. `maciej.dev`) must be using Cloudflare nameservers. Tunnel won't work if the zone's NS records still point at another DNS host.

**One-time setup on a fresh Pi:**

```bash
# 1. Install cloudflared (arm64 deb)
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb \
     -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb

# 2. Browser auth — copy the URL it prints, click through, pick the zone
cloudflared tunnel login

# 3. Create the named tunnel (writes ~/.cloudflared/<TUNNEL_UUID>.json)
cloudflared tunnel create are-they-hiring

# 4. Add the public CNAME record
cloudflared tunnel route dns are-they-hiring aretheyhiring.maciej.dev

# 5. Stage credentials + config in /etc/cloudflared (system service reads from here)
TUNNEL_UUID=$(ls ~/.cloudflared/*.json | head -1 | xargs -n1 basename | sed 's/.json$//')
sudo mkdir -p /etc/cloudflared
sudo cp ~/.cloudflared/${TUNNEL_UUID}.json /etc/cloudflared/
sudo chmod 600 /etc/cloudflared/${TUNNEL_UUID}.json
sudo tee /etc/cloudflared/config.yml > /dev/null <<EOF
tunnel: are-they-hiring
credentials-file: /etc/cloudflared/${TUNNEL_UUID}.json
ingress:
  - hostname: aretheyhiring.maciej.dev
    service: http://localhost:8000
  - service: http_status:404
EOF

# 6. Install + enable the systemd service
sudo cloudflared service install
sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared

# 7. Verify
sudo systemctl is-active cloudflared       # → active
curl -I https://aretheyhiring.maciej.dev/   # → 200
```

**Two gotchas worth remembering:**

- **`credentials-file:` must point at `/etc/cloudflared/...`**, not `~/.cloudflared/...`. The system service runs as root and reads from `/etc`. If you skip step 5 and only have the user-scope copy, the service starts but can't authenticate.
- **Run `sudo cloudflared service install` after** the config + creds are in `/etc/cloudflared/`. The installer reads them at install time and bails out otherwise.

**Recovery on a reinstalled Pi:** if the host was reflashed but the tunnel record still exists at Cloudflare (visible via `cloudflared tunnel list` once authed in step 2), you can skip step 3 — `cloudflared tunnel create` will fail "already exists" and the existing UUID + JSON cred can be re-staged into `/etc/cloudflared`. DNS routing (step 4) is also idempotent. We did exactly this when 192.168.1.2 got rebuilt.

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
