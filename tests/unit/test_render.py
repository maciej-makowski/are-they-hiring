"""Golden-output tests for the deployment renderer.

These guard against template drift. When a template or profile changes, the
golden files under ``deploy/testdata/pi-expected/`` must be updated in the
same commit so the diff is reviewable.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from deploy.render import (
    OllamaConfig,
    Profile,
    SystemdConfig,
    hand_edit_check,
    load_profile,
    merge_secrets,
    orphan_keys,
    render_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
GOLDEN_DIR = REPO_ROOT / "deploy" / "testdata" / "pi-expected"


TEMPLATE_TO_GOLDEN = {
    "env.j2": "env",
    "compose.prod.yml.j2": "compose.prod.yml",
    "are-they-hiring-compose.service.j2": "are-they-hiring-compose.service",
}


@pytest.mark.parametrize("template_name,golden_name", list(TEMPLATE_TO_GOLDEN.items()))
def test_pi_profile_matches_golden(template_name: str, golden_name: str) -> None:
    profile = load_profile("pi")
    rendered = render_profile(profile)[template_name]
    expected = (GOLDEN_DIR / golden_name).read_text()
    assert rendered == expected, (
        f"rendered {template_name} differs from {golden_name}; "
        "if the change is intentional, regenerate the golden file."
    )


def test_baseline_profile_reproduces_legacy_env_example() -> None:
    """A default-ish profile must render identically to today's .env.example.

    Existing Pi deployments expect the rendered output to match what they
    already have on disk. If this breaks, we've introduced a drift that
    would cause an unexpected systemctl restart on the next deploy.
    """

    profile = Profile(ollama=OllamaConfig(cpus=3.0, cpu_shares=None))
    rendered = render_profile(profile)["env.j2"]
    legacy = (REPO_ROOT / "podman" / "systemd" / ".env.example").read_text()
    assert rendered == legacy


def test_baseline_profile_reproduces_legacy_compose() -> None:
    profile = Profile(ollama=OllamaConfig(cpus=3.0, cpu_shares=None))
    rendered = render_profile(profile)["compose.prod.yml.j2"]
    legacy = (REPO_ROOT / "podman-compose.prod.yml").read_text()
    assert rendered == legacy


def test_baseline_profile_reproduces_legacy_systemd_unit() -> None:
    profile = Profile(ollama=OllamaConfig(cpus=3.0, cpu_shares=None))
    rendered = render_profile(profile)["are-they-hiring-compose.service.j2"]
    legacy = (REPO_ROOT / "podman" / "systemd" / "are-they-hiring-compose.service").read_text()
    assert rendered == legacy


def test_cpu_priority_knobs_emit_systemd_directives() -> None:
    profile = Profile(systemd=SystemdConfig(cpu_weight=10, io_weight=10, nice=15))
    unit = render_profile(profile)["are-they-hiring-compose.service.j2"]
    assert "CPUWeight=10" in unit
    assert "IOWeight=10" in unit
    assert "Nice=15" in unit


def test_default_systemd_omits_cpu_priority_directives() -> None:
    """Defaults preserve today's unit file shape (no CPUWeight/IOWeight/Nice)."""

    profile = Profile()
    unit = render_profile(profile)["are-they-hiring-compose.service.j2"]
    assert "CPUWeight" not in unit
    assert "IOWeight" not in unit
    assert "Nice=" not in unit


def test_compose_drops_ollama_cpu_cap_when_null() -> None:
    profile = Profile(ollama=OllamaConfig(cpus=None))
    compose = render_profile(profile)["compose.prod.yml.j2"]
    assert "cpus:" not in compose


def test_compose_includes_cpu_shares_when_set() -> None:
    profile = Profile(ollama=OllamaConfig(cpus=None, cpu_shares=128))
    compose = render_profile(profile)["compose.prod.yml.j2"]
    assert "cpu_shares: 128" in compose


def test_merge_secrets_replaces_in_place(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("POSTGRES_PASSWORD=realpass\n")
    rendered = "POSTGRES_USER=arethey\nPOSTGRES_PASSWORD=PLACEHOLDER\n"
    merged = merge_secrets(rendered, secrets)
    assert "POSTGRES_PASSWORD=realpass" in merged
    assert "PLACEHOLDER" not in merged
    # Unrelated keys preserved.
    assert "POSTGRES_USER=arethey" in merged


def test_merge_secrets_appends_new_keys(tmp_path: Path) -> None:
    secrets = tmp_path / "secrets.env"
    secrets.write_text("EXTRA_KEY=42\n")
    rendered = "POSTGRES_USER=arethey\n"
    merged = merge_secrets(rendered, secrets)
    assert "EXTRA_KEY=42" in merged
    assert "merged from secrets_env_path" in merged


def test_merge_secrets_no_file(tmp_path: Path) -> None:
    rendered = "POSTGRES_USER=arethey\n"
    assert merge_secrets(rendered, tmp_path / "missing.env") == rendered


def test_merge_secrets_none_path() -> None:
    rendered = "POSTGRES_USER=arethey\n"
    assert merge_secrets(rendered, None) == rendered


def test_orphan_keys_warns_on_drift(tmp_path: Path) -> None:
    live = tmp_path / ".env"
    live.write_text("POSTGRES_USER=arethey\nLEGACY_KEY=1\n")
    rendered = "POSTGRES_USER=arethey\n"
    assert orphan_keys(live, rendered) == ["LEGACY_KEY"]


def test_orphan_keys_empty_when_live_missing(tmp_path: Path) -> None:
    assert orphan_keys(tmp_path / "missing", "POSTGRES_USER=arethey\n") == []


def test_hand_edit_check_flags_newer_file(tmp_path: Path) -> None:
    live = tmp_path / "compose.yml"
    live.write_text("...")
    # Simulate: commit was 1000s ago, file mtime set to now.
    import time

    now = time.time()
    commit_ts = now - 1000
    # mtime default is now, which is commit_ts + 1000 > commit_ts + 1.
    assert hand_edit_check(live, commit_ts) is True


def test_hand_edit_check_ignores_missing_file(tmp_path: Path) -> None:
    assert hand_edit_check(tmp_path / "missing", 0.0) is False


def test_hand_edit_check_ignores_missing_commit_ts(tmp_path: Path) -> None:
    live = tmp_path / "x"
    live.write_text("a")
    assert hand_edit_check(live, None) is False


def test_cmd_apply_writes_all_three_targets(tmp_path: Path) -> None:
    """End-to-end: cmd_apply(skip_restart=True) creates every target file."""

    from deploy.render import cmd_apply, load_profile

    profile = load_profile("pi")
    profile.secrets_env_path = None  # don't touch the real secrets file

    rc = cmd_apply(profile, host=None, home=tmp_path, skip_restart=True)
    assert rc == 0
    assert (tmp_path / ".config/are-they-hiring/.env").exists()
    assert (tmp_path / ".config/are-they-hiring/compose.yml").exists()
    assert (tmp_path / ".config/systemd/user/are-they-hiring-compose.service").exists()


def test_cmd_apply_merges_secrets(tmp_path: Path) -> None:
    """cmd_apply substitutes values from secrets_env_path in the rendered .env.

    Users put both POSTGRES_PASSWORD and the matching DATABASE_URL in their
    local secrets.env (or replace the DATABASE_URL upstream). The renderer
    does a per-line key= override; it does not rewrite values embedded in
    other values.
    """

    from deploy.render import cmd_apply, load_profile

    secrets = tmp_path / "secrets.env"
    secrets.write_text(
        "POSTGRES_PASSWORD=hunter2\nDATABASE_URL=postgresql+asyncpg://arethey:hunter2@localhost:5432/arethey\n"
    )

    profile = load_profile("pi")
    profile.secrets_env_path = str(secrets)

    cmd_apply(profile, host=None, home=tmp_path, skip_restart=True)
    env_text = (tmp_path / ".config/are-they-hiring/.env").read_text()
    assert "POSTGRES_PASSWORD=hunter2" in env_text
    assert "DATABASE_URL=postgresql+asyncpg://arethey:hunter2@" in env_text
    assert "CHANGE_ME_TO_A_STRONG_PASSWORD" not in env_text
