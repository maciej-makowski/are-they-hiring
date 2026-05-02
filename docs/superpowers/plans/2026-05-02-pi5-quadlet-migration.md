# Pi 5 Quadlet Deployment Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a quadlet-based deployment mode to `deploy/render.py` (the profile renderer from #42), use it to migrate the Pi 5 (`192.168.1.3`, podman 5) from podman-compose to native systemd quadlets while leaving Pi 4's compose-based deployment unchanged.

**Architecture:** Extend the `Profile` pydantic schema with a `deployment_mode: "compose" | "quadlet"` field (default `compose`). Add Jinja2 templates under `deploy/templates/quadlet/` for the five quadlet files (`.pod` + four `.container`), parameterised on the profile so `cpu_weight`, `nice`, `cpu_shares`, ollama tuning, etc. flow through the same way they do for compose. `deploy/render.py` dispatches the render/apply path by mode: compose stays unchanged; quadlet writes to `~/.config/containers/systemd/`, runs `systemctl --user daemon-reload`, restarts `are-they-hiring-pod.service`. A new `deploy/profiles/pi5.yml` carries Pi 5–appropriate values and selects `quadlet` mode.

**Tech stack:** Python (pydantic, jinja2 — already present), podman 5 quadlets, systemd user services + linger.

**Reference materials:**

- Existing quadlet stubs in [podman/systemd/](../../../podman/systemd/) — `are-they-hiring.pod`, `are-they-hiring-{db,ollama,web,scraper}.container`. These are already-working quadlet files (used today by `make install` / Option B in the README), and they're the structural starting point for the templates. The templates parameterise + extend them with profile knobs (Pi 4 deployment-hygiene fixes from #32 + tuning from #50).
- Existing compose-mode renderer: [deploy/render.py](../../../deploy/render.py) — the routing patterns, `unified_diff()`, `merge_secrets()`, hand-edit guard, and remote-apply via scp/ssh are reused.
- Existing golden-test pattern: [tests/unit/test_render.py](../../../tests/unit/test_render.py) — extend with quadlet cases.

---

## File structure

**Created:**

- `deploy/profiles/pi5.yml` — Pi 5 profile, `deployment_mode: quadlet`
- `deploy/templates/quadlet/are-they-hiring.pod.j2`
- `deploy/templates/quadlet/are-they-hiring-db.container.j2`
- `deploy/templates/quadlet/are-they-hiring-ollama.container.j2`
- `deploy/templates/quadlet/are-they-hiring-web.container.j2`
- `deploy/templates/quadlet/are-they-hiring-scraper.container.j2`
- `deploy/testdata/pi5-expected/.env`
- `deploy/testdata/pi5-expected/are-they-hiring.pod`
- `deploy/testdata/pi5-expected/are-they-hiring-db.container`
- `deploy/testdata/pi5-expected/are-they-hiring-ollama.container`
- `deploy/testdata/pi5-expected/are-they-hiring-web.container`
- `deploy/testdata/pi5-expected/are-they-hiring-scraper.container`
- `scripts/migrate-pi5-to-quadlet.sh` — one-shot helper that stops the live compose service before the first quadlet apply

**Modified:**

- `deploy/render.py` — add `deployment_mode` field, dispatch render/apply by mode, factor compose-vs-quadlet target paths
- `tests/unit/test_render.py` — add quadlet golden tests
- `tests/unit/test_profile_schema.py` — assert `deployment_mode` default + validation
- `Makefile` — add `make migrate-to-quadlet PROFILE=<name> [HOST=...]` (delegates to the script)
- `README.md` — add "Option C: Quadlet via profile renderer (Pi 5+)" subsection
- `Implementation.md` — decision-log entry

**Untouched on purpose:**

- `deploy/profiles/pi.yml` — Pi 4 stays compose mode
- `deploy/templates/compose.prod.yml.j2`, `deploy/templates/are-they-hiring-compose.service.j2` — compose path unchanged
- `Containerfile.{web,scraper,ollama}` — image build is mode-agnostic
- `podman/systemd/*.{pod,container}` — kept as reference for `make install` (Option B) and as the golden source for the templates' shape

---

## Chunk 1: Schema + render dispatcher skeleton

### Task 1.1: Add `deployment_mode` field to `Profile`

**Files:**
- Modify: `deploy/render.py:106` (Profile class)
- Test: `tests/unit/test_profile_schema.py` (new asserts)

- [ ] **Step 1: Write a failing test for the default**

In `tests/unit/test_profile_schema.py`, add:

```python
def test_profile_deployment_mode_defaults_to_compose():
    """Default deployment_mode must be 'compose' for backward compatibility
    with pi.yml and any existing third-party profile."""
    from deploy.render import Profile
    p = Profile.model_validate({"host": "x@y", "secrets_env_path": "/tmp/s"})
    assert p.deployment_mode == "compose"


def test_profile_deployment_mode_rejects_unknown_value():
    from deploy.render import Profile
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        Profile.model_validate(
            {"host": "x@y", "secrets_env_path": "/tmp/s", "deployment_mode": "k8s"}
        )
```

- [ ] **Step 2: Run, expect both to fail**

```bash
uv run pytest tests/unit/test_profile_schema.py -k deployment_mode -v
```

Expected: 2 failures (`AttributeError` and `ValidationError` not raised).

- [ ] **Step 3: Add the field**

In `deploy/render.py`, in the `Profile` class:

```python
from typing import Literal

class Profile(_StrictModel):
    # ... existing fields ...
    deployment_mode: Literal["compose", "quadlet"] = "compose"
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/unit/test_profile_schema.py -k deployment_mode -v
```

Expected: 2 passes.

- [ ] **Step 5: Commit**

```bash
git add deploy/render.py tests/unit/test_profile_schema.py
git commit -m "feat(deploy): add deployment_mode to Profile schema (compose|quadlet)"
```

---

### Task 1.2: Factor target paths and template subdir into helpers

The compose path currently hardcodes `~/.config/are-they-hiring/{compose.yml,.env}` and `~/.config/systemd/user/are-they-hiring-compose.service`. Quadlet needs `~/.config/are-they-hiring/.env` (shared) plus `~/.config/containers/systemd/{*.pod,*.container}`. Factor this into a small helper that takes the mode and returns the list of `(template_name, target_path)` tuples.

**Files:**
- Modify: `deploy/render.py` — extract path mapping
- Test: `tests/unit/test_render.py`

- [ ] **Step 1: Write a failing test for the compose mapping**

```python
def test_target_paths_compose():
    from deploy.render import target_paths
    p = Profile.model_validate({"host": "x@y", "secrets_env_path": "/tmp/s"})
    paths = target_paths(p, home=Path("/home/cfiet"))
    assert paths == {
        "env.j2": Path("/home/cfiet/.config/are-they-hiring/.env"),
        "compose.prod.yml.j2": Path("/home/cfiet/.config/are-they-hiring/compose.yml"),
        "are-they-hiring-compose.service.j2": Path(
            "/home/cfiet/.config/systemd/user/are-they-hiring-compose.service"
        ),
    }


def test_target_paths_quadlet():
    from deploy.render import target_paths
    p = Profile.model_validate(
        {"host": "x@y", "secrets_env_path": "/tmp/s", "deployment_mode": "quadlet"}
    )
    paths = target_paths(p, home=Path("/home/cfiet"))
    assert paths == {
        "env.j2": Path("/home/cfiet/.config/are-they-hiring/.env"),
        "quadlet/are-they-hiring.pod.j2": Path(
            "/home/cfiet/.config/containers/systemd/are-they-hiring.pod"
        ),
        "quadlet/are-they-hiring-db.container.j2": Path(
            "/home/cfiet/.config/containers/systemd/are-they-hiring-db.container"
        ),
        "quadlet/are-they-hiring-ollama.container.j2": Path(
            "/home/cfiet/.config/containers/systemd/are-they-hiring-ollama.container"
        ),
        "quadlet/are-they-hiring-web.container.j2": Path(
            "/home/cfiet/.config/containers/systemd/are-they-hiring-web.container"
        ),
        "quadlet/are-they-hiring-scraper.container.j2": Path(
            "/home/cfiet/.config/containers/systemd/are-they-hiring-scraper.container"
        ),
    }
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/unit/test_render.py -k target_paths -v
```

Expected: `ImportError: cannot import name 'target_paths'`.

- [ ] **Step 3: Implement `target_paths` in `deploy/render.py`**

```python
def target_paths(profile: Profile, home: Path) -> dict[str, Path]:
    """Return a mapping of template name (relative to deploy/templates/) →
    absolute target path on the host's filesystem, dispatching by deployment_mode.
    """
    common = {
        "env.j2": home / ".config" / "are-they-hiring" / ".env",
    }
    if profile.deployment_mode == "compose":
        return {
            **common,
            "compose.prod.yml.j2": home / ".config" / "are-they-hiring" / "compose.yml",
            "are-they-hiring-compose.service.j2": (
                home / ".config" / "systemd" / "user" / "are-they-hiring-compose.service"
            ),
        }
    if profile.deployment_mode == "quadlet":
        quadlet_dir = home / ".config" / "containers" / "systemd"
        return {
            **common,
            "quadlet/are-they-hiring.pod.j2": quadlet_dir / "are-they-hiring.pod",
            "quadlet/are-they-hiring-db.container.j2": (
                quadlet_dir / "are-they-hiring-db.container"
            ),
            "quadlet/are-they-hiring-ollama.container.j2": (
                quadlet_dir / "are-they-hiring-ollama.container"
            ),
            "quadlet/are-they-hiring-web.container.j2": (
                quadlet_dir / "are-they-hiring-web.container"
            ),
            "quadlet/are-they-hiring-scraper.container.j2": (
                quadlet_dir / "are-they-hiring-scraper.container"
            ),
        }
    raise RuntimeError(f"unhandled deployment_mode: {profile.deployment_mode}")
```

- [ ] **Step 4: Refactor existing render/apply paths to use `target_paths()`**

Search `deploy/render.py` for hard-coded references like `compose.yml` and `are-they-hiring-compose.service`; replace each with a lookup against `target_paths(profile, home)` for the compose mode. Quadlet branch will remain dead code (no templates yet) for now — a defensive `FileNotFoundError` if any quadlet template is loaded is fine because the templates don't exist yet.

- [ ] **Step 5: Run the full unit test suite**

```bash
uv run pytest tests/unit/ -v
```

Expected: existing compose tests pass, new `target_paths` tests pass.

- [ ] **Step 6: Run the full integration suite to ensure no regression**

```bash
uv run pytest tests/integration/ -q
```

Expected: 92 (or current count) pass.

- [ ] **Step 7: Commit**

```bash
git add deploy/render.py tests/unit/test_render.py
git commit -m "refactor(deploy): factor target paths via target_paths() helper

Sets up per-mode dispatch without changing compose behaviour. Quadlet
branch wires the path map but the templates land in chunk 2."
```

---

## Chunk 2: Pod + DB container templates (simplest two)

### Task 2.1: `are-they-hiring.pod.j2` template

The pod is the simplest unit — just publishes port 8000 and is the parent for everything else. No profile knobs really apply to it on Pi 5 (no quotas, no priority — those go on individual containers).

**Files:**
- Create: `deploy/templates/quadlet/are-they-hiring.pod.j2`
- Create: `deploy/testdata/pi5-expected/are-they-hiring.pod`
- Test: `tests/unit/test_render.py` — golden compare

- [ ] **Step 1: Write the template**

```jinja
[Unit]
Description=Are They Hiring - Pod

[Pod]
PodName=are-they-hiring
PublishPort=8000:8000

[Install]
WantedBy=default.target
```

(Note: this one happens to have no Jinja substitution — it's identical for any quadlet profile. Kept as `.j2` for consistency with the rest.)

- [ ] **Step 2: Write the matching golden file**

`deploy/testdata/pi5-expected/are-they-hiring.pod`:

```
[Unit]
Description=Are They Hiring - Pod

[Pod]
PodName=are-they-hiring
PublishPort=8000:8000

[Install]
WantedBy=default.target
```

- [ ] **Step 3: Add a parametrised golden test**

In `tests/unit/test_render.py`, add a fixture/loader that takes a `(profile_name, template_name, expected_filename)` triple and renders + compares:

```python
@pytest.mark.parametrize("template,expected", [
    ("quadlet/are-they-hiring.pod.j2", "are-they-hiring.pod"),
])
def test_pi5_quadlet_render_matches_golden(template, expected):
    from deploy.render import render_template, load_profile
    profile = load_profile("pi5")  # placeholder profile from chunk 5
    rendered = render_template(template, profile)
    expected_path = Path("deploy/testdata/pi5-expected") / expected
    assert rendered == expected_path.read_text()
```

(You'll need a stub `pi5.yml` with the minimum required fields to keep this test green before chunk 5 lands. Add a temporary `tests/unit/fixtures/pi5-stub.yml` if you don't want to touch `deploy/profiles/pi5.yml` yet.)

- [ ] **Step 4: Run, expect failure**

```bash
uv run pytest tests/unit/test_render.py -k pi5_quadlet -v
```

Expected: profile not found OR template not found.

- [ ] **Step 5: Add the stub profile, run, expect pass**

```bash
uv run pytest tests/unit/test_render.py -k pi5_quadlet -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add deploy/templates/quadlet/are-they-hiring.pod.j2 \
        deploy/testdata/pi5-expected/are-they-hiring.pod \
        tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): pod template + golden test"
```

---

### Task 2.2: `are-they-hiring-db.container.j2` template

DB container is profile-driven on `EnvironmentFile` (the rendered `.env`) and `Volume` (named volume reuse from compose mode for migration parity). Restart policy: `on-failure` (lessons from #32 — `Restart=always` fights stop sequences).

**Files:**
- Create: `deploy/templates/quadlet/are-they-hiring-db.container.j2`
- Create: `deploy/testdata/pi5-expected/are-they-hiring-db.container`

- [ ] **Step 1: Write the template**

```jinja
[Unit]
Description=Are They Hiring - PostgreSQL
Requires=are-they-hiring-pod.service
After=are-they-hiring-pod.service

[Container]
Image=docker.io/postgres:16
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env
Volume=are-they-hiring-db-data:/var/lib/postgresql/data
HealthCmd=pg_isready -U {{ postgres.user }}
HealthInterval=5s
HealthTimeout=5s
HealthRetries=10

[Service]
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Write the matching golden file**

Render mentally with `postgres.user = arethey` (default in pi5.yml stub). Save the resolved file at `deploy/testdata/pi5-expected/are-they-hiring-db.container`.

- [ ] **Step 3: Extend the parametrised test**

```python
@pytest.mark.parametrize("template,expected", [
    ("quadlet/are-they-hiring.pod.j2", "are-they-hiring.pod"),
    ("quadlet/are-they-hiring-db.container.j2", "are-they-hiring-db.container"),
])
def test_pi5_quadlet_render_matches_golden(template, expected):
    ...
```

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/unit/test_render.py -k pi5_quadlet -v
```

- [ ] **Step 5: Commit**

```bash
git add deploy/templates/quadlet/are-they-hiring-db.container.j2 \
        deploy/testdata/pi5-expected/are-they-hiring-db.container \
        tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): db container template"
```

---

## Chunk 3: Ollama, web, scraper container templates

### Task 3.1: `are-they-hiring-ollama.container.j2`

This template has the most knobs — every Ollama tuning field on the profile (cpus, cpu_shares, env_file) flows in. Lessons from #32 + #50: `EnvironmentFile=%h/.config/.../.env` is the right way to feed `OLLAMA_*` vars; do NOT also add an `Environment=OLLAMA_HOST=...` because the .env already sets it correctly.

**Files:**
- Create: `deploy/templates/quadlet/are-they-hiring-ollama.container.j2`
- Create: `deploy/testdata/pi5-expected/are-they-hiring-ollama.container`

- [ ] **Step 1: Write the template**

```jinja
[Unit]
Description=Are They Hiring - Ollama LLM ({{ ollama.model }} bundled)
Requires=are-they-hiring-pod.service
After=are-they-hiring-pod.service

[Container]
Image=localhost/are-they-hiring-ollama:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env
{%- if ollama.cpus is not none %}
PodmanArgs=--cpus={{ ollama.cpus }}
{%- endif %}
{%- if ollama.cpu_shares is not none %}
PodmanArgs=--cpu-shares={{ ollama.cpu_shares }}
{%- endif %}
# Uncomment for NVIDIA GPU acceleration:
#AddDevice=nvidia.com/gpu=all
#Environment=OLLAMA_VULKAN=1
#Environment=OLLAMA_GPU_LAYERS=-1

[Service]
Restart=on-failure
RestartSec=30
TimeoutStartSec={{ systemd.timeout_start_sec }}
TimeoutStopSec={{ systemd.timeout_stop_sec }}
{%- if systemd.cpu_weight != 100 %}
CPUWeight={{ systemd.cpu_weight }}
{%- endif %}
{%- if systemd.io_weight != 100 %}
IOWeight={{ systemd.io_weight }}
{%- endif %}
{%- if systemd.nice != 0 %}
Nice={{ systemd.nice }}
{%- endif %}

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Render and write the golden file**

For pi5.yml stub (assume Pi 5 defaults: cpus=null, cpu_shares=null, cpu_weight=100, nice=0 → no overrides emitted):

```
[Unit]
Description=Are They Hiring - Ollama LLM (qwen2.5:1.5b bundled)
Requires=are-they-hiring-pod.service
After=are-they-hiring-pod.service

[Container]
Image=localhost/are-they-hiring-ollama:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env
# Uncomment for NVIDIA GPU acceleration:
#AddDevice=nvidia.com/gpu=all
#Environment=OLLAMA_VULKAN=1
#Environment=OLLAMA_GPU_LAYERS=-1

[Service]
Restart=on-failure
RestartSec=30
TimeoutStartSec=300
TimeoutStopSec=180

[Install]
WantedBy=default.target
```

(Tweak the stub profile if Pi 5 carries non-default values for these.)

- [ ] **Step 3: Extend the parametrised test**

Add `("quadlet/are-they-hiring-ollama.container.j2", "are-they-hiring-ollama.container")` to the parametrize list.

- [ ] **Step 4: Run, expect pass**

```bash
uv run pytest tests/unit/test_render.py -k pi5_quadlet -v
```

- [ ] **Step 5: Commit**

```bash
git add deploy/templates/quadlet/are-they-hiring-ollama.container.j2 \
        deploy/testdata/pi5-expected/are-they-hiring-ollama.container \
        tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): ollama container template with profile knobs"
```

---

### Task 3.2: `are-they-hiring-web.container.j2`

**Files:**
- Create: `deploy/templates/quadlet/are-they-hiring-web.container.j2`
- Create: `deploy/testdata/pi5-expected/are-they-hiring-web.container`

- [ ] **Step 1: Write the template**

```jinja
[Unit]
Description=Are They Hiring - Web (FastAPI)
Requires=are-they-hiring-db.service are-they-hiring-ollama.service
After=are-they-hiring-db.service are-they-hiring-ollama.service

[Container]
Image=localhost/are-they-hiring-web:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env

[Service]
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

- [ ] **Step 2: Write the golden file** (identical content for the stub profile)

- [ ] **Step 3: Extend the parametrised test list**

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add deploy/templates/quadlet/are-they-hiring-web.container.j2 \
        deploy/testdata/pi5-expected/are-they-hiring-web.container \
        tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): web container template"
```

---

### Task 3.3: `are-they-hiring-scraper.container.j2`

The scraper has the same shape as web (no port publish, same env_file, depends on db + ollama). It also doesn't carry CPU-prio knobs of its own — those live on ollama since that's the heavy worker.

**Files:**
- Create: `deploy/templates/quadlet/are-they-hiring-scraper.container.j2`
- Create: `deploy/testdata/pi5-expected/are-they-hiring-scraper.container`

- [ ] **Step 1: Write the template**

```jinja
[Unit]
Description=Are They Hiring - Scraper (APScheduler + httpx)
Requires=are-they-hiring-db.service are-they-hiring-ollama.service
After=are-they-hiring-db.service are-they-hiring-ollama.service

[Container]
Image=localhost/are-they-hiring-scraper:latest
Pod=are-they-hiring.pod
EnvironmentFile=%h/.config/are-they-hiring/.env

[Service]
Restart=on-failure
RestartSec=30

[Install]
WantedBy=default.target
```

- [ ] **Steps 2-4** as above.

- [ ] **Step 5: Commit**

```bash
git add deploy/templates/quadlet/are-they-hiring-scraper.container.j2 \
        deploy/testdata/pi5-expected/are-they-hiring-scraper.container \
        tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): scraper container template"
```

---

## Chunk 4: Apply logic + full-render golden test + .env golden

### Task 4.1: Apply logic for quadlet mode

The compose `apply` runs `systemctl --user daemon-reload && systemctl --user restart are-they-hiring-compose.service`. Quadlet needs:

1. `mkdir -p ~/.config/containers/systemd` (in case it doesn't exist yet on a fresh box)
2. Write the rendered files
3. `systemctl --user daemon-reload` (regenerates the runtime service units)
4. `systemctl --user restart are-they-hiring-pod.service` — the pod restart cascades to the container services

**Files:**
- Modify: `deploy/render.py` — add quadlet branch in `apply()`
- Test: `tests/unit/test_render.py`

- [ ] **Step 1: Write a failing test for the quadlet apply command sequence**

Mock `subprocess.run` and assert the command sequence:

```python
def test_apply_quadlet_runs_correct_systemctl_sequence(tmp_path, monkeypatch):
    from deploy.render import apply
    profile = load_profile_with_overrides({"deployment_mode": "quadlet"})

    runs = []
    def fake_run(cmd, **kwargs):
        runs.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)
    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr("deploy.render.HOME", tmp_path)

    apply(profile)

    # mkdir -p containers/systemd, then daemon-reload, then restart the pod
    assert any("daemon-reload" in " ".join(c) for c in runs)
    assert any("restart" in " ".join(c) and "are-they-hiring-pod.service" in " ".join(c) for c in runs)
    # And the daemon-reload must come before the restart
    reload_idx = next(i for i, c in enumerate(runs) if "daemon-reload" in " ".join(c))
    restart_idx = next(i for i, c in enumerate(runs) if "are-they-hiring-pod.service" in " ".join(c))
    assert reload_idx < restart_idx
```

- [ ] **Step 2: Run, expect failure**

```bash
uv run pytest tests/unit/test_render.py -k apply_quadlet -v
```

- [ ] **Step 3: Implement quadlet branch in `apply()`**

In `deploy/render.py`, where the compose branch runs `daemon-reload` + `restart are-they-hiring-compose.service`, add:

```python
if profile.deployment_mode == "quadlet":
    # Containers/systemd directory may not exist on a fresh box.
    quadlet_dir = home / ".config" / "containers" / "systemd"
    quadlet_dir.mkdir(parents=True, exist_ok=True)
    # ... write rendered files via target_paths() ...
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "restart", "are-they-hiring-pod.service"])
```

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Run all integration + unit tests**

```bash
uv run pytest tests/unit/ tests/integration/ -q
```

- [ ] **Step 6: Commit**

```bash
git add deploy/render.py tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): apply path — daemon-reload + pod restart"
```

---

### Task 4.2: Quadlet apply over `--host` (remote)

Compose mode already supports `apply --host user@1.2.3.4` via shelling out to `ssh`/`scp`. Quadlet path needs the same — write rendered files via scp to the right remote dir, then `ssh user@host 'systemctl --user daemon-reload && systemctl --user restart are-they-hiring-pod.service'`.

**Files:**
- Modify: `deploy/render.py`

- [ ] **Step 1: Write a failing test for remote quadlet apply**

Mock `subprocess.run`, capture all `ssh`/`scp` commands, assert the remote dirs are correct (`~/.config/containers/systemd/...`).

- [ ] **Step 2: Run, expect failure**

- [ ] **Step 3: Implement** — extend the existing `--host` branch to use `target_paths(profile, home=PurePosixPath("~"))` (the remote home is unknown locally, leave the path as `~/...` and let the remote shell expand it). The remote `mkdir -p ~/.config/containers/systemd` step is needed before scp.

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add deploy/render.py tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): support apply --host for quadlet mode"
```

---

### Task 4.3: Hand-edit guard for quadlet files

The compose mode refuses to overwrite `~/.config/are-they-hiring/compose.yml` if its mtime is newer than the repo's last git commit. Apply the same logic to the quadlet target files. The check is per-file; if any quadlet file fails the check, the apply aborts before writing anything.

**Files:**
- Modify: `deploy/render.py`

- [ ] **Step 1: Write a test that hand-edits a quadlet target and expects apply to refuse**

- [ ] **Step 2: Run, expect failure (guard not enforced for quadlet yet)**

- [ ] **Step 3: Implement — generalise the existing guard to iterate over all targets returned by `target_paths()`**

- [ ] **Step 4: Run, expect pass**

- [ ] **Step 5: Commit**

```bash
git add deploy/render.py tests/unit/test_render.py
git commit -m "feat(deploy/quadlet): extend hand-edit guard to quadlet targets"
```

---

### Task 4.4: `.env` golden for pi5

The pi5 profile shares `env.j2` with pi.yml, so the `.env` content is the same shape — but values differ (model, threading, etc.). Add `deploy/testdata/pi5-expected/.env` reflecting the pi5 stub profile.

**Files:**
- Create: `deploy/testdata/pi5-expected/.env`
- Test: `tests/unit/test_render.py`

- [ ] **Step 1: Render the env.j2 with the pi5 stub profile, save as the golden file**
- [ ] **Step 2: Add `("env.j2", ".env")` to the parametrize list**
- [ ] **Step 3: Run, expect pass**
- [ ] **Step 4: Commit**

```bash
git add deploy/testdata/pi5-expected/.env tests/unit/test_render.py
git commit -m "test(deploy/quadlet): pi5 .env golden"
```

---

## Chunk 5: Real `pi5.yml` profile + migration script

### Task 5.1: `deploy/profiles/pi5.yml`

Replace the stub profile from chunk 2 with the real one. Inherit Pi 4 values where they make sense; relax where the 16 GB Pi 5 has headroom.

**Files:**
- Create (or replace stub): `deploy/profiles/pi5.yml`
- Update goldens accordingly: `deploy/testdata/pi5-expected/*`

- [ ] **Step 1: Write `deploy/profiles/pi5.yml`**

```yaml
# Raspberry Pi 5 (16 GB, podman 5) deployment profile.
#
# Native quadlet mode — render.py emits files under
# ~/.config/containers/systemd/ and starts via the .pod service.
# Pi 4 stays on pi.yml (compose mode); see #51 / #50 for context.

host: cfiet@192.168.1.3

tz: UTC

secrets_env_path: ~/.config/are-they-hiring/secrets.env

deployment_mode: quadlet

postgres:
  user: arethey
  password: CHANGE_ME_TO_A_STRONG_PASSWORD
  db: arethey
  database_url: postgresql+asyncpg://arethey:CHANGE_ME_TO_A_STRONG_PASSWORD@localhost:5432/arethey

ollama:
  host: http://ollama:11434
  model: qwen2.5:1.5b      # bumped to gemma3:4b-it-qat in #52, separate PR
  keep_alive: 12h
  num_threads: 4           # Pi 5 has 4 fast Cortex-A76 cores; use them all
  num_parallel: null
  context_length: 4096
  flash_attention: true    # Pi 4 lessons in #50 — keep on, harmless on Pi 5
  kv_cache_type: q8_0
  timeout_seconds: 300
  cpus: null               # 16 GB box — no need for a hard CPU cap
  cpu_shares: null

classify:
  concurrency: 1           # serial for stability, parity with Pi 4 final config

scrape:
  schedule: "06:00,12:00,18:00"
  retry_max: 3

systemd:
  # Pi 5 has plenty of headroom; no need to yield to OS by default.
  cpu_weight: 100
  io_weight: 100
  nice: 0
  timeout_start_sec: 300
  timeout_stop_sec: 180
```

- [ ] **Step 2: Re-render and update goldens**

Some goldens may have differed slightly between the stub and the real profile. Re-render each template with the real profile, diff against golden, update where intended.

- [ ] **Step 3: Run unit tests**

```bash
uv run pytest tests/unit/ -v
```

Expected: all pass with the updated goldens.

- [ ] **Step 4: Commit**

```bash
git add deploy/profiles/pi5.yml deploy/testdata/pi5-expected/
git commit -m "feat(deploy): add pi5.yml profile (quadlet mode)"
```

---

### Task 5.2: `scripts/migrate-pi5-to-quadlet.sh` + Makefile target

Migration is a one-shot: stop and disable the running compose service, then `make deploy PROFILE=pi5 HOST=...` lays down the quadlets. Encapsulate the stop-disable steps in a script so the operator doesn't forget either.

**Files:**
- Create: `scripts/migrate-pi5-to-quadlet.sh`
- Modify: `Makefile`

- [ ] **Step 1: Write the script**

```bash
#!/usr/bin/env bash
# One-shot migration from Pi 4–style compose deployment to native quadlets.
# Run on a host that currently has the are-they-hiring-compose.service unit
# active. Idempotent: re-running on an already-migrated box is a no-op.
set -euo pipefail

HOST="${1:-}"
if [[ -z "$HOST" ]]; then
  echo "Usage: $0 user@host" >&2
  exit 2
fi

echo "### stopping + disabling the existing compose service ###"
ssh "$HOST" '
  set -e
  if systemctl --user is-enabled are-they-hiring-compose.service >/dev/null 2>&1; then
    systemctl --user disable --now are-they-hiring-compose.service
  fi
  # Remove the now-stale unit file so it does not confuse future deploys.
  rm -f ~/.config/systemd/user/are-they-hiring-compose.service
  systemctl --user daemon-reload
'

echo "### deploying quadlet profile ###"
make deploy PROFILE=pi5 HOST="$HOST"

echo "### migration complete; verifying ###"
ssh "$HOST" '
  podman ps --format "table {{.Names}} {{.Status}}"
  curl -sS -o /dev/null -w "web local: %{http_code}\n" http://localhost:8000/
'
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x scripts/migrate-pi5-to-quadlet.sh
```

- [ ] **Step 3: Add Makefile target**

```makefile
migrate-to-quadlet:
	@if [ -z "$(HOST)" ]; then \
	  echo "Usage: make migrate-to-quadlet HOST=user@host"; exit 2; \
	fi
	./scripts/migrate-pi5-to-quadlet.sh $(HOST)
```

- [ ] **Step 4: Smoke-test the script on a throwaway VM/dev box** (or document that it's only been tested on the live Pi 5 in the next chunk).

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate-pi5-to-quadlet.sh Makefile
git commit -m "feat(deploy): migrate-to-quadlet helper script + make target"
```

---

## Chunk 6: Pi 5 cutover + docs

### Task 6.1: Live cutover on Pi 5

This is the actual production switch. Do it AFTER chunks 1–5 have landed (or at least are passing locally + in CI on the branch).

**Pre-check:**

- [ ] **Step 1: Verify Pi 5 currently runs the compose stack**

```bash
ssh cfiet@192.168.1.3 'systemctl --user status are-they-hiring-compose.service --no-pager | head -10 && podman ps --format "{{.Names}}"'
```

Expected: 4 containers running (`are-they-hiring_{db,ollama,web,scraper}_1` or similar).

- [ ] **Step 2: Snapshot the current DB volume (safety)**

```bash
ssh cfiet@192.168.1.3 'podman run --rm \
  -v are-they-hiring_arethey-db-data:/data:ro \
  -v ~/:/backup \
  alpine tar czf /backup/db-pre-quadlet-migration.tgz /data'
```

(Restore path documented in case anything breaks: `tar xzf db-pre-quadlet-migration.tgz` into a fresh volume.)

**Cutover:**

- [ ] **Step 3: Run the migration script**

```bash
make migrate-to-quadlet HOST=cfiet@192.168.1.3
```

Expected output: stop+disable of compose service, fresh quadlet apply, daemon-reload, pod restart, container listing showing 4 containers up.

- [ ] **Step 4: Verify all four containers are healthy**

```bash
ssh cfiet@192.168.1.3 'podman ps --format "table {{.Names}} {{.Status}}"'
```

Expected: 4 rows, db `(healthy)`, others `Up`.

- [ ] **Step 5: Verify web responds locally and through the tunnel**

```bash
ssh cfiet@192.168.1.3 'curl -sS -o /dev/null -w "local %{http_code} %{time_total}s\n" http://localhost:8000/'
curl -sS -o /dev/null -w "public %{http_code} %{time_total}s\n" https://aretheyhiring.maciej.dev/
```

Expected: 200 / 200.

- [ ] **Step 6: Verify scraper started cleanly**

```bash
ssh cfiet@192.168.1.3 'podman logs --tail 30 are-they-hiring-scraper-1 2>&1 | tail -15'
```

Look for "Starting scrape scheduler...", "Added job ... at 06:00", etc.

- [ ] **Step 7: Reboot test (optional but high-confidence)**

```bash
ssh cfiet@192.168.1.3 'sudo reboot'
# wait 60s
ssh cfiet@192.168.1.3 'podman ps --format "table {{.Names}} {{.Status}}"'
curl -sS -o /dev/null -w "post-reboot public %{http_code}\n" https://aretheyhiring.maciej.dev/
```

Expected: stack comes back up automatically (linger + WantedBy=default.target on the .pod and .container files), public probe returns 200.

- [ ] **Step 8: Note the cutover in the PR description**

Time to start, time to stable, any glitches encountered.

---

### Task 6.2: README "Option C" + Implementation.md decision log

**Files:**
- Modify: `README.md` (add Option C)
- Modify: `Implementation.md` (add decision-log entry)

- [ ] **Step 1: Add README Option C**

After Option B (Quadlet units, manual `make install`), insert "Option C: Quadlet via profile renderer (Pi 5+)" describing:

- Prerequisite: podman 5+
- `make migrate-to-quadlet HOST=user@host` for the one-time cutover
- `make deploy PROFILE=pi5 HOST=user@host` for subsequent updates
- Where the quadlet files live (`~/.config/containers/systemd/`)
- How to inspect the generated systemd units (`systemctl --user list-units 'are-they-hiring-*'`)

- [ ] **Step 2: Add Implementation.md decision-log entry**

Brief entry under the existing decisions section: "12. Pi 5 deployment (revised 2026-05-XX)" with rationale (16 GB headroom, podman 5 native quadlets, no compose-wrapper indirection, one source of truth via the profile renderer from #42).

- [ ] **Step 3: Run all tests once more**

```bash
uv run pytest tests/unit/ tests/integration/ -q
uv run ruff check src/ tests/ scripts/ deploy/
uv run ruff format --check src/ tests/ scripts/ deploy/
```

Expected: all green.

- [ ] **Step 4: Commit**

```bash
git add README.md Implementation.md
git commit -m "docs: pi 5 quadlet deployment (Option C) + decision log"
```

---

### Task 6.3: Open the PR

- [ ] **Step 1: Push the branch**

```bash
git push -u origin feat/pi5-quadlet-deployment
```

- [ ] **Step 2: Open the PR**

```bash
toolbox run gh pr create --repo maciej-makowski/are-they-hiring \
  --title "feat(deploy): Pi 5 quadlet deployment via profile renderer (#51)" \
  --body "<see template below>"
```

PR body should cover:

- Closes #51
- Summary: deployment_mode field, 5 quadlet templates, pi5.yml, migration script, README Option C
- Cutover notes from Task 6.1 step 8
- Test plan: unit + integration green; live Pi 5 cutover verified; reboot test passed
- Migration is reversible — `make install-compose` on Pi 5 (after disabling pod service) restores the compose path. Pi 4 untouched.

- [ ] **Step 3: Confirm CI green; do NOT merge** (per `~/.claude/CLAUDE.md`)

---

## Notes for the executor

- @superpowers:test-driven-development — every chunk uses TDD; do not skip the failing-test step.
- @superpowers:verification-before-completion — after the live cutover (Task 6.1) DO NOT mark "done" until both the local and public curls return 200.
- @superpowers:executing-plans (or @superpowers:subagent-driven-development if subagents are available) — drives the per-task review loop.
- The compose mode behaviour MUST stay byte-identical for `pi.yml`. If you find yourself touching `compose.prod.yml.j2` or `are-they-hiring-compose.service.j2`, stop — that's not in scope for this plan.
- If the hand-edit guard refuses to apply on Pi 5 because someone hand-edited a stale quadlet file, the right move is to delete the stale files and re-run apply — same pattern as we hit on Pi 4 in #50's session.
- The Containerfile.{web,scraper,ollama} images are the same on both Pi 4 and Pi 5; no per-mode image work.

---
