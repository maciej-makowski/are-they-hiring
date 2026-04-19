# Agent Guide

Rules for AI agents (and humans following the same conventions) working in this repo. Keep these in sync with the actual codebase — if a rule here no longer matches reality, fix the rule or fix the code.

## 1. Workflow: PRs only

- **Never commit directly to `master`.** Every change lands via a pull request.
- Branch naming: `feat/...`, `fix/...`, `docs/...`, `chore/...`, `ci/...`, `refactor/...`. One short segment, kebab-case.
- One PR = one logical change. If scope grows mid-branch, split it.
- PR titles describe the change as a statement (`"Add foo"`, not `"Adding foo"`).
- Agents **do not merge PRs** and **do not enable auto-merge**. The repo owner reviews and merges.
- Before pushing an existing branch, `git pull` first — the owner may have pushed changes via the GitHub UI.
- After a PR is merged, pull latest `master` before starting new work.

## 2. Commit hygiene

- Use a concise subject line (under ~70 chars) starting with the conventional-commit type: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`, `ci:`, `perf:`.
- Body explains the why, not the what. Diff shows the what.
- Pre-commit hooks must pass — do not skip them with `--no-verify` unless the repo owner explicitly tells you to. Hooks run: ruff check, ruff format, integration tests.
- Squash merge only (configured at the repo level — no action needed, just don't rebase-merge by hand).

## 3. Tests and linting

- Run `make test` before pushing. Runs `tests/unit/` (renderer / schema golden tests) and `tests/integration/` (scrapers, API, DB — all SQLite in-memory). No external services required.
- Run `make lint` to check formatting (covers `src/`, `tests/`, `deploy/`). `make lint-fix` auto-fixes.
- All new behaviour needs a test. Bug fixes need a regression test.
- CI runs tests + lint on every PR. The lint job will commit auto-fixes back to the branch; after that, `git pull` your branch before pushing again.

## 4. Documentation is part of the change

When a PR changes behaviour, the docs change in the same PR:

- `README.md` — setup, commands, configuration table.
- `Implementation.md` — design decisions, data model, architectural choices.
- `docs/ROADMAP.md` — open items. When completing a roadmap item, remove or cross it off here.
- `AGENTS.md` (this file) — conventions. Update when the rules change.
- Inline comments only where the *why* is non-obvious; don't document the what.

## 5. Tech stack quick reference

- **Python 3.14**, deps via `uv` (`pyproject.toml` + `uv.lock`).
- **Web:** FastAPI + Jinja2 + HTMX (vanilla JS for the interactive bits).
- **DB:** PostgreSQL + SQLAlchemy (async) + Alembic migrations.
- **LLM:** Ollama runs in its own container; model baked into image via `Containerfile.ollama`.
- **Scraper:** httpx against company job-board APIs (Greenhouse / Ashby), scheduled via APScheduler.
- **Containers:** Podman. Local dev via `podman-compose -f podman-compose.dev.yml`. Production via systemd quadlets or `podman-compose.prod.yml`.
- **Lint/format:** ruff. Rules configured in `pyproject.toml` under `[tool.ruff]`.

## 6. Environment gotchas

- If `$TOOLBOX_PATH` is set, you're inside a Fedora toolbox. `podman`, `git`, and `gh` typically need to be invoked as `toolbox run podman ...` / `toolbox run git ...` / `toolbox run gh ...`, OR `podman --remote` works for the container daemon.
- `podman-compose` from inside a toolbox needs a wrapper:
  ```
  podman-compose --podman-path ./scripts/podman-remote.sh -f podman-compose.dev.yml up -d
  ```
- Use the `Makefile` targets wherever possible (`make test`, `make dev`, `make build`, `make install-compose`, etc.) — they encode the correct flags.
- Data persists in named Podman volumes (`are-they-hiring_arethey-db-data`). `down -v` nukes it.

## 7. Parallel work

Multiple agents may work on this repo at the same time.

- Each agent takes a single roadmap item and opens its own branch.
- **Read `docs/ROADMAP.md` first.** It lists dependencies and flags which items overlap.
- Items marked as overlapping (e.g. "Telemetry" and "Observability dashboard") should not run in parallel without a coordination call first.
- If you need to touch the same file as another in-flight PR, rebase on top of it once it's merged rather than resolving conflicts twice.

## 8. GitHub interactions

- Use the `gh` CLI for everything — PRs, issues, API calls. Never the web UI if `gh` can do it.
- Each roadmap item has a linked GitHub issue (see `docs/ROADMAP.md`). Reference it in PR descriptions with `Closes #N`.
- To attach context (logs, screenshots, notes) for future work, paste into the issue rather than into the conversation — the issue is the durable record.

## 9. When things go wrong

- If a test fails locally but you don't understand why, **stop and investigate**. Do not disable the test or skip the hook.
- If you can't figure out the right fix within a reasonable window (say, 3 attempts), escalate: leave your WIP on the branch, open a draft PR with your current thinking, and surface the blocker.
- Never `git push --force` on `master` (branch protection blocks it anyway) and avoid force-push on your feature branch if it's shared.

## 10. Reading list

- [`README.md`](README.md) — start here for setup and running the app.
- [`Implementation.md`](Implementation.md) — design decisions and rationale.
- [`docs/ROADMAP.md`](docs/ROADMAP.md) — open items and dependencies.
