# Roadmap

Backlog of larger features we want to tackle, beyond the small polish items in the README's "Next Steps" section.

Each item lists rough scope, dependencies, and any open questions. Items aren't strictly ordered — pick based on current needs.

---

## 1. Classifier tuning harness (MLE pipeline)

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

## 2. Telemetry & structured logging

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

## 3. Raspberry Pi crash investigation

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

## 4. Integration test coverage for UI states

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

**Relatively self-contained. Independent from the others.**

---

## 5. Admin observability dashboard

**Goal:** surface operational state in the UI — not just for the user, but for us when something goes wrong.

**Shape:**
- Per-scrape-run detail page: company, attempts, timings, errors, final result.
- Aggregate dashboard: success/failure counts, average durations, error-rate over time.
- Classification event log: record each classification attempt to a new table (title, model, timestamp, duration, result) and surface it.
- Charts over time: scrape success rate, classification throughput, pending classification queue depth.

**Open questions:**
- New table or extend `scrape_runs`?
- Data retention — keep everything forever or prune after N days?
- Which charts actually need historical data vs point-in-time?

**Overlaps heavily with (2).** Telemetry produces the raw data; this surfaces it. Either do telemetry → dashboard sequentially, or design the schema together up front.

---

## Dependencies and suggested order

- **(3)** is blocking (app is crashing) and small — do first once logs are available.
- **(4)** is independent and safe to start anytime.
- **(2)** and **(5)** overlap; decide whether to do them together or sequence 2 → 5.
- **(1)** is the biggest. Needs brainstorming before any code. Can wait until the infrastructure work is stable.
