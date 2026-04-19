"""Profile-based deployment config renderer.

Reads a YAML profile from ``deploy/profiles/<name>.yml``, validates it against
a pydantic schema, renders three Jinja2 templates (``.env``, ``compose.yml``,
systemd unit), and either diffs the staged output against the live targets
(``render`` action) or applies it (``apply`` action).

Usage:
    python -m deploy.render --profile pi render
    python -m deploy.render --profile pi apply
    python -m deploy.render --profile pi apply --host cfiet@192.168.1.2

Design notes:
    * Secrets are never templated: the profile declares ``secrets_env_path``
      pointing at an untracked file (typically ``~/.config/are-they-hiring/
      secrets.env``). Its contents are merged into the rendered ``.env`` in
      the ``apply`` phase only, so rendered artefacts remain safe to commit
      / diff.
    * The renderer refuses to apply if the live ``compose.yml`` or systemd
      unit is newer than the repo's last git commit (hand-edits guard).
    * Remote deploys shell out to ``ssh``/``scp``; no paramiko.
"""

from __future__ import annotations

import argparse
import difflib
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field

# Paths -----------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
DEPLOY_DIR = REPO_ROOT / "deploy"
TEMPLATES_DIR = DEPLOY_DIR / "templates"
PROFILES_DIR = DEPLOY_DIR / "profiles"

# Render outputs in this order. Each entry: (template_name, live_path_fn).
# live_path_fn takes the HOME path and returns the live target path.
RENDER_TARGETS: list[tuple[str, str]] = [
    ("env.j2", ".config/are-they-hiring/.env"),
    ("compose.prod.yml.j2", ".config/are-they-hiring/compose.yml"),
    ("are-they-hiring-compose.service.j2", ".config/systemd/user/are-they-hiring-compose.service"),
]


# Profile schema --------------------------------------------------------


class _StrictModel(BaseModel):
    """Base model that rejects unknown keys so typos in profiles fail fast."""

    model_config = ConfigDict(extra="forbid")


class PostgresConfig(_StrictModel):
    user: str = "arethey"
    password: str = "CHANGE_ME_TO_A_STRONG_PASSWORD"
    db: str = "arethey"
    database_url: str = "postgresql+asyncpg://arethey:CHANGE_ME_TO_A_STRONG_PASSWORD@localhost:5432/arethey"


class OllamaConfig(_StrictModel):
    host: str = "http://ollama:11434"
    model: str = "qwen2.5:1.5b"
    keep_alive: str = "12h"
    num_threads: int = 2
    timeout_seconds: int = 300
    cpus: float | None = None
    cpu_shares: int | None = None


class ClassifyConfig(_StrictModel):
    concurrency: int = 2


class ScrapeConfig(_StrictModel):
    schedule: str = "06:00,12:00,18:00"
    retry_max: int = 3


class SystemdConfig(_StrictModel):
    cpu_weight: int = Field(default=100, ge=1, le=10000)
    io_weight: int = Field(default=100, ge=1, le=10000)
    nice: int = Field(default=0, ge=-20, le=19)
    timeout_start_sec: int = 300
    timeout_stop_sec: int = 180


class Profile(_StrictModel):
    """Top-level profile schema. One instance per deployment target."""

    host: str | None = None
    tz: str = "UTC"
    secrets_env_path: str | None = None
    postgres: PostgresConfig = Field(default_factory=PostgresConfig)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    classify: ClassifyConfig = Field(default_factory=ClassifyConfig)
    scrape: ScrapeConfig = Field(default_factory=ScrapeConfig)
    systemd: SystemdConfig = Field(default_factory=SystemdConfig)


# Loading and rendering -------------------------------------------------


def load_profile(profile_name: str, profiles_dir: Path = PROFILES_DIR) -> Profile:
    """Load and validate a profile by name (e.g. "pi")."""

    path = profiles_dir / f"{profile_name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    return Profile.model_validate(data)


def _jinja_env(templates_dir: Path = TEMPLATES_DIR) -> Environment:
    return Environment(
        loader=FileSystemLoader(templates_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )


def render_profile(
    profile: Profile,
    templates_dir: Path = TEMPLATES_DIR,
) -> dict[str, str]:
    """Render every template for ``profile``. Returns {template_name: text}."""

    env = _jinja_env(templates_dir)
    context = profile.model_dump()
    return {tmpl: env.get_template(tmpl).render(**context) for tmpl, _ in RENDER_TARGETS}


# .env parsing / secret merging ----------------------------------------


def _parse_env_text(text: str) -> dict[str, str]:
    """Parse a dotenv-style file into a key->value dict.

    Ignores blank lines and comments. Values are not quoted/unquoted — they
    are preserved verbatim. Only the first ``=`` is used as the separator.
    """

    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value
    return out


def merge_secrets(env_text: str, secrets_path: Path | None) -> str:
    """Return ``env_text`` with any keys from ``secrets_path`` overriding.

    If a secret key already exists in the rendered env, the secret value
    replaces the rendered value in-place (preserves comments / ordering).
    Secret keys not present get appended at the end under a banner.
    """

    if secrets_path is None or not secrets_path.exists():
        return env_text

    secrets = _parse_env_text(secrets_path.read_text())
    if not secrets:
        return env_text

    lines = env_text.splitlines(keepends=True)
    replaced: set[str] = set()
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in secrets and key not in replaced:
            trailing_newline = "\n" if raw.endswith("\n") else ""
            lines[i] = f"{key}={secrets[key]}{trailing_newline}"
            replaced.add(key)

    out = "".join(lines)
    extras = [k for k in secrets if k not in replaced]
    if extras:
        if not out.endswith("\n"):
            out += "\n"
        out += "\n# --- merged from secrets_env_path ---\n"
        for k in extras:
            out += f"{k}={secrets[k]}\n"
    return out


def orphan_keys(live_env_path: Path, rendered_env_text: str) -> list[str]:
    """Return keys present in the live .env file but missing from rendered."""

    if not live_env_path.exists():
        return []
    live_keys = set(_parse_env_text(live_env_path.read_text()))
    rendered_keys = set(_parse_env_text(rendered_env_text))
    return sorted(live_keys - rendered_keys)


# Diffing & hand-edit guard --------------------------------------------


def unified_diff(a_text: str, b_text: str, a_name: str, b_name: str) -> str:
    diff = difflib.unified_diff(
        a_text.splitlines(keepends=True),
        b_text.splitlines(keepends=True),
        fromfile=a_name,
        tofile=b_name,
    )
    return "".join(diff)


def _repo_last_commit_time(repo_path: Path = REPO_ROOT) -> float | None:
    """Return the Unix mtime of the most recent git commit, or None on failure."""

    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "log", "-1", "--format=%ct"],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except subprocess.CalledProcessError, FileNotFoundError, ValueError:
        return None


def hand_edit_check(live_path: Path, repo_last_commit_ts: float | None) -> bool:
    """Return True if ``live_path`` was hand-edited after repo's last commit.

    Returns False (no hand edit detected) if the file doesn't exist or the
    commit timestamp is unavailable.
    """

    if repo_last_commit_ts is None or not live_path.exists():
        return False
    return live_path.stat().st_mtime > repo_last_commit_ts + 1


# Apply -----------------------------------------------------------------


@dataclass
class RenderResult:
    """Rendered artefacts for one profile."""

    profile: Profile
    rendered: dict[str, str]  # template_name -> rendered text

    def env_text(self) -> str:
        return self.rendered["env.j2"]

    def compose_text(self) -> str:
        return self.rendered["compose.prod.yml.j2"]

    def service_text(self) -> str:
        return self.rendered["are-they-hiring-compose.service.j2"]


def _home() -> Path:
    return Path(os.path.expanduser("~"))


def _target_path(template_name: str, home: Path) -> Path:
    relative = dict(RENDER_TARGETS)[template_name]
    return home / relative


def _write_staging(result: RenderResult, staging_dir: Path) -> dict[str, Path]:
    """Write rendered files into ``staging_dir``. Returns {template: path}."""

    staging_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    filenames = {
        "env.j2": "env",
        "compose.prod.yml.j2": "compose.prod.yml",
        "are-they-hiring-compose.service.j2": "are-they-hiring-compose.service",
    }
    for template_name, _ in RENDER_TARGETS:
        path = staging_dir / filenames[template_name]
        path.write_text(result.rendered[template_name])
        paths[template_name] = path
    return paths


def cmd_render(profile: Profile, *, home: Path | None = None) -> int:
    """Render the profile, diff vs live targets, print diffs. Does not apply."""

    home = home or _home()
    result = RenderResult(profile=profile, rendered=render_profile(profile))

    print(f"Rendering profile -> staging diff vs {home}", file=sys.stderr)
    any_diff = False
    for template_name, _ in RENDER_TARGETS:
        live = _target_path(template_name, home)
        rendered = result.rendered[template_name]
        live_text = live.read_text() if live.exists() else ""
        diff = unified_diff(live_text, rendered, f"{live} (live)", f"{template_name} (rendered)")
        if diff:
            any_diff = True
            print(diff)

    orphans = orphan_keys(_target_path("env.j2", home), result.env_text())
    if orphans:
        print(
            f"WARNING: live .env has keys not in the profile: {', '.join(orphans)}",
            file=sys.stderr,
        )

    if not any_diff:
        print("No differences between rendered output and live targets.", file=sys.stderr)
    return 0


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def cmd_apply(
    profile: Profile,
    *,
    host: str | None = None,
    home: Path | None = None,
    skip_restart: bool = False,
) -> int:
    """Render and install. Local by default; remote if ``host`` is set.

    Refuses to apply if any live target is newer than the repo's last commit.
    """

    home = home or _home()
    result = RenderResult(profile=profile, rendered=render_profile(profile))

    # Hand-edit guard (local only; for remote the hand-edit check would need
    # to run on the remote box — out of scope for v1).
    if host is None:
        repo_ts = _repo_last_commit_time()
        for template_name, _ in RENDER_TARGETS:
            live = _target_path(template_name, home)
            if hand_edit_check(live, repo_ts):
                live_text = live.read_text()
                rendered = result.rendered[template_name]
                diff = unified_diff(live_text, rendered, f"{live} (hand-edited)", f"{template_name} (rendered)")
                print(
                    f"ERROR: {live} is newer than the repo's last commit — refusing to overwrite.",
                    file=sys.stderr,
                )
                print(diff, file=sys.stderr)
                return 2

    # Merge secrets into the rendered .env.
    secrets_path = Path(os.path.expanduser(profile.secrets_env_path)) if profile.secrets_env_path else None
    env_text = merge_secrets(result.env_text(), secrets_path)

    # Orphan warning based on live .env.
    orphans_path = _target_path("env.j2", home) if host is None else None
    if orphans_path is not None:
        orphans = orphan_keys(orphans_path, env_text)
        if orphans:
            print(
                f"WARNING: live .env has keys not in the profile: {', '.join(orphans)}",
                file=sys.stderr,
            )

    # Stage files in a temp dir (post secret merge).
    with tempfile.TemporaryDirectory() as staging_raw:
        staging = Path(staging_raw)
        result.rendered["env.j2"] = env_text  # use merged version
        staged_paths = _write_staging(result, staging)

        if host is None:
            _apply_local(staged_paths, home, skip_restart=skip_restart)
        else:
            _apply_remote(staged_paths, host, skip_restart=skip_restart)

    return 0


def _apply_local(staged_paths: dict[str, Path], home: Path, *, skip_restart: bool = False) -> None:
    for template_name, rel in RENDER_TARGETS:
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(staged_paths[template_name], target)
        print(f"wrote {target}", file=sys.stderr)

    if skip_restart:
        return
    _run(["systemctl", "--user", "daemon-reload"])
    _run(["systemctl", "--user", "restart", "are-they-hiring-compose.service"])


def _apply_remote(staged_paths: dict[str, Path], host: str, *, skip_restart: bool = False) -> None:
    # Use ~ in the remote path; ssh expands it in the remote shell.
    for template_name, rel in RENDER_TARGETS:
        remote_path = f"~/{rel}"
        remote_dir = os.path.dirname(rel)
        _run(["ssh", host, f"mkdir -p ~/{remote_dir}"])
        _run(["scp", str(staged_paths[template_name]), f"{host}:{remote_path}"])
        print(f"wrote {host}:{remote_path}", file=sys.stderr)

    if skip_restart:
        return
    _run(
        [
            "ssh",
            host,
            "systemctl --user daemon-reload && systemctl --user restart are-they-hiring-compose.service",
        ]
    )


# CLI --------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Profile-based deployment config renderer.")
    parser.add_argument("--profile", required=True, help="Profile name (e.g. 'pi')")
    sub = parser.add_subparsers(dest="action", required=True)

    sub.add_parser("render", help="Render templates and diff against live targets.")

    apply = sub.add_parser("apply", help="Render, copy to targets, restart service.")
    apply.add_argument("--host", default=None, help="Remote host (e.g. user@1.2.3.4)")
    apply.add_argument("--skip-restart", action="store_true", help="Skip daemon-reload + restart (useful in tests)")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    profile = load_profile(args.profile)

    if args.action == "render":
        return cmd_render(profile)
    if args.action == "apply":
        return cmd_apply(profile, host=args.host, skip_restart=args.skip_restart)
    parser.error(f"Unknown action: {args.action}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
