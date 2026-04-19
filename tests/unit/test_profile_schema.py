"""Pydantic validation edge cases for the deploy profile schema."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from deploy.render import (
    OllamaConfig,
    Profile,
    SystemdConfig,
    load_profile,
)


def test_defaults_are_sensible() -> None:
    profile = Profile()
    assert profile.tz == "UTC"
    assert profile.ollama.model == "qwen2.5:1.5b"
    assert profile.ollama.cpus is None
    assert profile.ollama.cpu_shares is None
    assert profile.systemd.cpu_weight == 100
    assert profile.systemd.io_weight == 100
    assert profile.systemd.nice == 0
    assert profile.systemd.timeout_start_sec == 300
    assert profile.systemd.timeout_stop_sec == 180


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"bogus_key": "oops"})


def test_unknown_nested_key_rejected() -> None:
    with pytest.raises(ValidationError):
        Profile.model_validate({"ollama": {"typo_key": "oops"}})


def test_nice_range_enforced() -> None:
    with pytest.raises(ValidationError):
        SystemdConfig(nice=100)
    with pytest.raises(ValidationError):
        SystemdConfig(nice=-100)


def test_cpu_weight_range_enforced() -> None:
    with pytest.raises(ValidationError):
        SystemdConfig(cpu_weight=0)
    with pytest.raises(ValidationError):
        SystemdConfig(cpu_weight=100_000)


def test_ollama_cpus_accepts_none_and_float() -> None:
    assert OllamaConfig(cpus=None).cpus is None
    assert OllamaConfig(cpus=3.0).cpus == 3.0


def test_load_profile_raises_on_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_profile("does-not-exist", profiles_dir=tmp_path)


def test_load_profile_roundtrip(tmp_path: Path) -> None:
    profile_path = tmp_path / "foo.yml"
    profile_path.write_text(
        yaml.safe_dump(
            {
                "host": "user@1.2.3.4",
                "tz": "Europe/London",
                "ollama": {"model": "gemma3:270m", "cpus": 2.0, "cpu_shares": 64},
                "systemd": {"cpu_weight": 10, "nice": 15},
            }
        )
    )
    profile = load_profile("foo", profiles_dir=tmp_path)
    assert profile.host == "user@1.2.3.4"
    assert profile.tz == "Europe/London"
    assert profile.ollama.model == "gemma3:270m"
    assert profile.ollama.cpus == 2.0
    assert profile.ollama.cpu_shares == 64
    assert profile.systemd.cpu_weight == 10
    assert profile.systemd.nice == 15


def test_secrets_env_path_preserved() -> None:
    profile = Profile.model_validate({"secrets_env_path": "~/secrets.env"})
    assert profile.secrets_env_path == "~/secrets.env"


def test_host_optional() -> None:
    assert Profile().host is None
    assert Profile(host="user@host").host == "user@host"
