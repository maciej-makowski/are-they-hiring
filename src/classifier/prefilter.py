"""Runtime SVM pre-filter that runs ahead of the LLM classifier.

Loads the compressed JSON model committed at ``classifier/prefilter.json.gz``,
fetches an embedding for each title from Ollama's embedding endpoint, computes
``dot(coef, embedding) + intercept``, and returns whether the title needs an
LLM call.

Inference uses only ``httpx`` + pure-Python dot product. ``scikit-learn`` /
``numpy`` are training-only dependencies.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent.parent.parent / "classifier" / "prefilter.json.gz"
EMBED_BATCH_SIZE = 64


@dataclass
class Prefilter:
    embedding_model: str
    coef: list[float]
    intercept: float
    threshold: float
    metadata: dict[str, Any]

    def score(self, embedding: list[float]) -> float:
        """Compute the LinearSVC decision-function margin for a single embedding."""
        if len(embedding) != len(self.coef):
            raise ValueError(f"embedding dimension mismatch: expected {len(self.coef)}, got {len(embedding)}")
        return sum(c * e for c, e in zip(self.coef, embedding, strict=True)) + self.intercept

    def needs_llm(self, embedding: list[float]) -> bool:
        """Titles with score below the threshold are rejected ('definitely not SWE',
        LLM is skipped). Titles at-or-above the threshold pass through to the LLM."""
        return self.score(embedding) >= self.threshold


@lru_cache(maxsize=1)
def load_prefilter(path: Path | None = None) -> Prefilter:
    path = path if path is not None else MODEL_PATH
    with gzip.open(path, "rb") as f:
        payload = json.loads(f.read().decode("utf-8"))
    if payload.get("schema_version") != 1:
        raise RuntimeError(f"unsupported prefilter schema version: {payload.get('schema_version')}")
    if payload.get("model_type") != "linear_svc":
        raise RuntimeError(f"unsupported prefilter model_type: {payload.get('model_type')}")
    return Prefilter(
        embedding_model=payload["embedding_model"],
        coef=list(payload["coef"]),
        intercept=float(payload["intercept"]),
        threshold=float(payload["threshold"]),
        metadata=dict(payload.get("metadata", {})),
    )


async def _embed_batch(client: httpx.AsyncClient, host: str, model: str, inputs: list[str]) -> list[list[float]]:
    response = await client.post(
        f"{host}/api/embed",
        json={"model": model, "input": inputs},
        timeout=60.0,
    )
    response.raise_for_status()
    body = response.json()
    embeddings = body.get("embeddings") or body.get("embedding")
    if embeddings is None:
        raise RuntimeError(f"unexpected embed response keys: {list(body)[:5]}")
    if isinstance(embeddings[0], float):
        embeddings = [embeddings]
    return embeddings


async def should_call_llm(
    titles: list[str],
    ollama_host: str,
    batch_size: int = EMBED_BATCH_SIZE,
) -> dict[str, bool]:
    """Return ``{title: needs_llm}`` for each input title.

    ``needs_llm[title] == True`` means the pre-filter could not confidently
    reject this title and the caller should ask the LLM. ``False`` means the
    pre-filter classifies this title as not-SWE with high confidence.

    If the embedding call or model load fails, every title is mapped to
    ``True`` so the caller falls through to the LLM uniformly. The failure is
    logged at WARN level but never raises; the LLM-only path is always a
    safe default.
    """
    if not titles:
        return {}

    try:
        prefilter = load_prefilter()
    except Exception as e:
        logger.warning("pre-filter model load failed; falling through to LLM. (%s)", e)
        return dict.fromkeys(titles, True)

    try:
        async with httpx.AsyncClient() as client:
            embeddings: list[list[float]] = []
            for i in range(0, len(titles), batch_size):
                batch = titles[i : i + batch_size]
                embeddings.extend(await _embed_batch(client, ollama_host, prefilter.embedding_model, batch))
    except Exception as e:
        logger.warning(
            "pre-filter embedding call failed (%s: %s); falling through to LLM for %d titles.",
            type(e).__name__,
            e,
            len(titles),
        )
        return dict.fromkeys(titles, True)

    return {title: prefilter.needs_llm(emb) for title, emb in zip(titles, embeddings, strict=True)}


async def main() -> None:
    """Smoke test: embed and score a small sample."""
    import os
    import sys

    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    sample = sys.argv[1:] or [
        "Senior Software Engineer",
        "Product Designer",
        "Research Engineer, Pre-training",
        "Account Executive, Startups",
        "Full Stack Software Engineer, Growth",
    ]
    result = await should_call_llm(sample, host)
    pf = load_prefilter()
    print(f"model: {pf.embedding_model} threshold={pf.threshold:.4f}")
    for title, needs in result.items():
        print(f"  {'LLM' if needs else 'skip':>4}  {title}")


if __name__ == "__main__":
    asyncio.run(main())
