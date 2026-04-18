# Roadmap

Backlog of larger features we want to tackle.

Each item has a linked GitHub issue — attach context (logs, screenshots, examples) there rather than to this document. This file is the high-level shape; issues hold the ongoing details.

Each item lists rough scope, dependencies, and any open questions. Items aren't strictly ordered — pick based on current needs.

---

## 1. Classifier tuning harness (MLE pipeline) — [#17](https://github.com/maciej-makowski/are-they-hiring/issues/17)

**Goal:** systematically improve classification accuracy on a bigger/better-tuned prompt or model by comparing candidates against a trusted reference.

**Shape:**
- Custom Ollama MODELFILEs with few-shot examples/counter-examples drawn from the existing dataset.
- Experiment harness that can run many model/prompt combinations in parallel and produce comparable reports.
- Outputs go to structured files (JSONL/CSV), never to the production DB.
- Each experiment starts by snapshotting the current set of postings to a file so the experiment is reproducible on the same data.
- Split dataset into train (~10%) + eval. Use the training set against reference models (Anthropic Claude, OpenAI GPT, Google Gemini) to generate "source of truth" labels.
- Report starts with summary comparison per candidate model, drills down per-batch and per-posting.

**Open questions:**
- Build on existing tooling (promptfoo, DSPy, LangSmith, Braintrust) vs homegrown pandas/JSONL?
- How to handle the cost of reference-model calls (Claude/GPT/Gemini aren't free).
- Where does the harness live — same repo, separate repo, notebook-style vs script-style?
- How do we take a tuned MODELFILE from experiment to production?

**Needs:** dedicated brainstorming session before any code. This is the biggest item.

**Not blocking anything else.**

---

## 2. Telemetry & structured logging — [#18](https://github.com/maciej-makowski/are-they-hiring/issues/18)

**Goal:** better visibility into the running app, especially on the Pi where things are opaque.

**Shape:**
- Switch from stdlib `logging.basicConfig` to `structlog` for structured (JSON) log lines.
- Add request IDs via FastAPI middleware; propagate through DB queries, Ollama calls, scrape runs.
- Instrument key paths with timings:
  - Fetch duration per company
  - Classification latency per title
  - DB query timings (SQLAlchemy event hooks)
- Optional: OpenTelemetry traces with a local Jaeger or direct export.

**Open questions:**
- Log destination: stdout (journald picks it up) or forward somewhere?
- Metrics format: Prometheus endpoint vs just structured logs?
- How much overhead are we willing to accept on the Pi?

**Overlaps with (5)** — telemetry captures most of what the observability dashboard wants to display. Consider doing them together, with the schema work of (5) feeding data into (2)'s pipeline.

---

## 3. Raspberry Pi crash investigation — [#19](https://github.com/maciej-makowski/are-they-hiring/issues/19)

**Goal:** find and fix the cause of app crashes on the Pi.

**Shape:**
- Collect `journalctl --user -u are-they-hiring-compose.service` around crash times.
- Look for OOM-killer hits (`dmesg | grep -i oom`), Postgres WAL errors, Ollama segfaults, Python stack traces.
- Correlate with system resource usage (memory pressure, swap activity) at the time of crash.

**Likely suspects:**
- Memory pressure: Ollama (488 MB loaded) + Postgres + scraper Python runtime on a 4 GB Pi with 200 MB swap.
- Ollama model unload/reload thrashing if `OLLAMA_KEEP_ALIVE` didn't take effect.
- Container restart loop if health checks are too aggressive.

**Needs:** user to provide systemd logs before we can dig in.

**Blocks nothing; would benefit from (2) for future crashes but not this one.**

---

## 4. Integration test coverage for UI states — [#20](https://github.com/maciej-makowski/are-they-hiring/issues/20)

**Goal:** catch regressions in the nuanced state handling on home page and day detail.

**Shape:**
- Seed fixtures covering all state combinations:
  - No scrape / scrape running / scrape succeeded / scrape failed
  - No postings / postings fetched but unclassified / postings fetched and classified with no SWE / classified with SWE
  - Mix across companies (one succeeded, one failed, one still running)
- One integration test per state, asserting the rendered HTML matches expectations (e.g. `hero-classifying`, `hero-no`, `day-status-amber`).
- Additional coverage for failure modes:
  - All three scrapers failed — what does home show?
  - Some classifications partially applied vs none
  - Scrape run with non-zero `postings_found` but zero after dedup
  - Stale postings (long since last seen) on calendar

**Open questions:**
- Prefer pytest fixtures/factories or a seed SQL file?
- Snapshot HTML in golden files, or assert specific CSS classes/text?

Also re-validate the Playwright E2E suite as part of this work — it hasn't been run against the current UI since the calendar + classifying-state changes landed.

**Relatively self-contained. Independent from the others.**

---

## 5. Admin observability dashboard — [#21](https://github.com/maciej-makowski/are-they-hiring/issues/21)

**Goal:** surface operational state in the UI — not just for the user, but for us when something goes wrong.

**Shape:**
- Per-scrape-run detail page: company, attempts, timings, errors, final result.
- Aggregate dashboard: success/failure counts, average durations, error-rate over time.
- Classification event log: record each classification attempt to a new table (title, model, timestamp, duration, result) and surface it.
- Charts over time: scrape success rate, classification throughput, pending classification queue depth.
- Longer-range trend chart of SWE postings (weekly/monthly) — complements the 30-day calendar on the home page.

**Open questions:**
- New table or extend `scrape_runs`?
- Data retention — keep everything forever or prune after N days?
- Which charts actually need historical data vs point-in-time?

**Overlaps heavily with (2).** Telemetry produces the raw data; this surfaces it. Either do telemetry → dashboard sequentially, or design the schema together up front.

---

## 6. More companies — [#22](https://github.com/maciej-makowski/are-they-hiring/issues/22)

**Goal:** expand the scraper coverage beyond the original three.

**Candidates:**
- ~~xAI~~ (done — Greenhouse scraper landed 2026-04-18)
- Meta AI (FAIR)
- Mistral
- Cohere
- ~~Perplexity~~ (done — Ashby scraper landed 2026-04-18)
- Inflection (if still hiring independently)

**Shape:**
- Each company is a new scraper subclass. Most use Greenhouse or Ashby — same parsers as existing ones.
- Refactor `SCRAPERS` registry to be discovered/configurable rather than hardcoded.
- Home page copy update — "Is Big AI still hiring Software Engineers?" already generic enough, but company list in subtitles may need tweaks.

**Open questions:**
- Where does "Big AI" end? Stay at the frontier labs, or include applied-AI startups?
- Do we add all at once or grow gradually?

**Independent. Small-to-medium per company, multiplies with list length.**

---

## 7. Public internet deployment — [#26](https://github.com/maciej-makowski/are-they-hiring/issues/26)

**Goal:** make the app reachable from the internet on a proper domain (e.g. `aretheyhiringse.maciek.dev`) with HTTPS, while keeping the attack surface small.

**Options to evaluate:**

- **A. RPi at home + Cloudflare Tunnel.** Free; uses existing hardware; no inbound ports exposed; CF handles HTTPS/DDoS. Downside: depends on home internet and Pi reliability (see #19). Quick-tunnel already works end-to-end.
- **B. Small VPS (Hetzner CAX11, ARM64 4 GB, ~€4/mo).** Always-on, dedicated; ARM images already work. Requires standard server hardening (SSH keys only, fail2ban, unattended-upgrades, firewall, backups).
- **C. VPS with GPU (~€40/mo+).** Faster classification; overkill for this app's load.
- **D. PaaS (Fly.io, Railway, Render).** Zero-ops, but Ollama doesn't fit well — would push classification to a cloud LLM and change the architecture.
- **E. Hybrid: cheap VPS + cloud LLM API.** No Ollama to babysit; recurring per-request cost; external dependency.

**Security considerations (regardless of option):**
- HTTPS-only + HSTS.
- Strong Postgres password (`.env` template already prompts).
- Decide: is `/scrapes` admin page public, or does it need basic auth?
- Secrets never in git — rely on systemd `EnvironmentFile` or equivalent.
- Postgres volume backups.
- Rate limiting / bot protection (CF covers most of this in option A).

**Open questions:**
- Domain: `aretheyhiringse.maciek.dev` (already discussed).
- DNS provider: stay with current registrar (CNAME to CF) or move to Cloudflare DNS.
- Does the UI stay fully public, or lock down the admin views?

**Recommendation:** start with (A), move to (B) if the Pi proves unreliable.

**Depends on:** (3) being resolved before (A) is production-ready.

---

## 8. Per-day posting observation tracking — [#30](https://github.com/maciej-makowski/are-they-hiring/issues/30)

**Goal:** record which specific days we observed each posting, rather than inferring presence from a `[first_seen_date, last_seen_date]` range.

**Shape:**
- New `posting_observation(posting_id, date, scrape_run_id)` table with composite key `(posting_id, date)`.
- Written on every `upsert_postings` call — new *and* re-seen postings both get a row.
- Calendar / home-state queries use observations where available.
- `first_seen_date` / `last_seen_date` become denormalised cache columns or are dropped.

**Why it matters:** today, if scraping was skipped on a day in the middle of a posting's range, the calendar and home-state queries still treat the posting as active on that day. Can't distinguish observed from inferred. Blocks churn metrics, honest calendar semantics, and dashboards that need per-day truth.

**Open questions:**
- Backfill strategy for existing postings — mark as inferred?
- Storage / retention policy (O(postings × days) rows).
- Design schema jointly with (2) + (5) so dashboards are built against it from day one.

**Related:** (2), (5). Not blocking anything else today.

---

## Polish & maintenance backlog

Smaller items that don't warrant their own top-level entry:

- **Sound effects.** [#23](https://github.com/maciej-makowski/are-they-hiring/issues/23) — Replace empty placeholder MP3s in `src/web/static/sounds/` with actual audio.
- **Classifier prompt refinement.** [#24](https://github.com/maciej-makowski/are-they-hiring/issues/24) — Iterate on the prompt string to fix obvious mis-classifications. Cheap alternative to the full harness (1).

---

## Dependencies and suggested order

- **(3)** is blocking (app is crashing) and small — do first once logs are available.
- **(4)** is independent and safe to start anytime.
- **(2)** and **(5)** overlap; decide whether to do them together or sequence 2 → 5.
- **(1)** is the biggest. Needs brainstorming before any code. Can wait until the infrastructure work is stable.
- **(6)** and the polish items can be picked up any time as filler work.
- **(8)** is independent; best designed jointly with (2) and (5) to avoid schema churn.
- **(7)** is gated on (3) for option A (home Pi must be stable first), independent otherwise.
