"""Tests for the SVM pre-filter runtime module and classifier integration."""

from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.classifier import prefilter


@pytest.fixture
def fake_model(tmp_path: Path) -> Path:
    """Write a tiny hand-crafted LinearSVC payload to a temp prefilter.json.gz.

    2-D embedding, one positive axis. Titles embedding [+1, 0] score above
    threshold (needs LLM); [-1, 0] score below (short-circuits to False)."""
    payload = {
        "schema_version": 1,
        "model_type": "linear_svc",
        "embedding_model": "fake-embed",
        "coef": [1.0, 0.0],
        "intercept": 0.0,
        "threshold": 0.0,
        "metadata": {"trained_at": "2026-04-19T00:00:00+00:00", "training_samples": 100},
    }
    path = tmp_path / "prefilter.json.gz"
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(payload).encode("utf-8"))
    path.write_bytes(buf.getvalue())
    return path


def test_load_prefilter(fake_model: Path) -> None:
    prefilter.load_prefilter.cache_clear()
    pf = prefilter.load_prefilter(fake_model)
    assert pf.embedding_model == "fake-embed"
    assert pf.coef == [1.0, 0.0]
    assert pf.intercept == 0.0
    assert pf.threshold == 0.0


def test_score_and_needs_llm(fake_model: Path) -> None:
    prefilter.load_prefilter.cache_clear()
    pf = prefilter.load_prefilter(fake_model)
    assert pf.score([1.0, 0.0]) == pytest.approx(1.0)
    assert pf.score([-1.0, 0.0]) == pytest.approx(-1.0)
    assert pf.needs_llm([1.0, 0.0]) is True
    assert pf.needs_llm([-1.0, 0.0]) is False


def test_score_dimension_mismatch(fake_model: Path) -> None:
    prefilter.load_prefilter.cache_clear()
    pf = prefilter.load_prefilter(fake_model)
    with pytest.raises(ValueError, match="dimension mismatch"):
        pf.score([1.0, 0.0, 0.0])


def test_real_shipped_model_loads() -> None:
    """The model committed at classifier/prefilter.json.gz must be loadable by
    the runtime without sklearn/numpy being available at import time."""
    prefilter.load_prefilter.cache_clear()
    pf = prefilter.load_prefilter()
    assert pf.embedding_model == "all-minilm"
    assert len(pf.coef) == 384  # all-minilm dim
    assert isinstance(pf.intercept, float)
    assert isinstance(pf.threshold, float)
    assert "trained_at" in pf.metadata
    assert pf.metadata.get("training_samples") == 1381


@pytest.mark.asyncio
async def test_should_call_llm_uses_threshold(fake_model: Path, httpx_mock) -> None:
    prefilter.load_prefilter.cache_clear()
    httpx_mock.add_response(
        url="http://fake-ollama/api/embed",
        json={"embeddings": [[1.0, 0.0], [-1.0, 0.0]]},
    )
    with patch.object(prefilter, "MODEL_PATH", fake_model):
        prefilter.load_prefilter.cache_clear()
        result = await prefilter.should_call_llm(["needs_llm", "short_circuit"], "http://fake-ollama")
    assert result == {"needs_llm": True, "short_circuit": False}
    prefilter.load_prefilter.cache_clear()


@pytest.mark.asyncio
async def test_should_call_llm_falls_through_on_embed_failure(fake_model: Path, httpx_mock) -> None:
    """Embedding-endpoint failure must not raise — pass every title to the LLM."""
    prefilter.load_prefilter.cache_clear()
    httpx_mock.add_response(url="http://fake-ollama/api/embed", status_code=500, text="boom")
    with patch.object(prefilter, "MODEL_PATH", fake_model):
        prefilter.load_prefilter.cache_clear()
        result = await prefilter.should_call_llm(["any_title", "another"], "http://fake-ollama")
    assert result == {"any_title": True, "another": True}
    prefilter.load_prefilter.cache_clear()


@pytest.mark.asyncio
async def test_should_call_llm_empty_input() -> None:
    assert await prefilter.should_call_llm([], "http://anywhere") == {}
