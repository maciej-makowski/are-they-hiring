"""Train the SVM pre-filter used ahead of the LLM classifier.

Loads the compressed hand-labelled training set, embeds every title via a
local Ollama embedding model (default: all-minilm), trains a LinearSVC with
class_weight='balanced', picks the decision threshold that preserves the
target positive-class recall on a held-out split, and writes the model as a
compressed JSON pickle-alternative so runtime inference does not need sklearn.

Runtime deserialisation needs only plain Python + the embedding call;
sklearn/numpy are training-only deps (``[project.optional-dependencies].training``).

Usage:
    uv run --extra training python scripts/train_prefilter.py
    uv run --extra training python scripts/train_prefilter.py --eval-only
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import io
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, cross_val_predict
from sklearn.svm import LinearSVC

REPO_ROOT = Path(__file__).resolve().parent.parent
TRAINING_CSV = REPO_ROOT / "classifier" / "training_data.csv.gz"
MODEL_OUT = REPO_ROOT / "classifier" / "prefilter.json.gz"

DEFAULT_EMBEDDING_MODEL = "all-minilm"
DEFAULT_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
DEFAULT_TARGET_RECALL = 0.95
EMBED_BATCH_SIZE = 64


async def _embed_batch(client: httpx.AsyncClient, host: str, model: str, inputs: list[str]) -> list[list[float]]:
    response = await client.post(
        f"{host}/api/embed",
        json={"model": model, "input": inputs},
        timeout=120.0,
    )
    response.raise_for_status()
    body = response.json()
    embeddings = body.get("embeddings") or body.get("embedding")
    if embeddings is None:
        raise RuntimeError(f"unexpected embed response: {list(body)[:5]}")
    if isinstance(embeddings[0], float):
        # single-input response shape — normalise to list-of-lists
        embeddings = [embeddings]
    return embeddings


async def embed_all(titles: list[str], host: str, model: str, batch_size: int = EMBED_BATCH_SIZE) -> np.ndarray:
    async with httpx.AsyncClient() as client:
        out: list[list[float]] = []
        total_batches = (len(titles) + batch_size - 1) // batch_size
        for i in range(0, len(titles), batch_size):
            batch = titles[i : i + batch_size]
            embeddings = await _embed_batch(client, host, model, batch)
            out.extend(embeddings)
            batch_num = i // batch_size + 1
            print(
                f"  embedded {len(out)}/{len(titles)} titles (batch {batch_num}/{total_batches})",
                file=sys.stderr,
            )
    return np.array(out, dtype=np.float32)


def pick_threshold(scores: np.ndarray, y: np.ndarray, target_recall: float) -> float:
    """Return the largest decision-margin threshold whose positive-class recall is >= target.

    At inference, titles with ``score < threshold`` are rejected by the pre-filter
    (classified "definitely not SWE", skips the LLM). Titles with ``score >=
    threshold`` pass through to the LLM. Lowering the threshold means more titles
    pass through — higher recall on the positive class, less speedup.
    """
    pos_scores = np.sort(scores[y == 1])
    if len(pos_scores) == 0:
        return float(scores.min())
    # Keep at least `ceil(target_recall * n_pos)` positives passing through.
    # Picking the k-th smallest positive score as threshold guarantees exactly
    # (n_pos - k) positives have score >= threshold. We want recall >= target:
    #   (n_pos - k) / n_pos >= target  =>  k <= n_pos * (1 - target)
    n_pos = len(pos_scores)
    max_dropped = int(np.floor(n_pos * (1 - target_recall)))
    if max_dropped == 0:
        # No positive may be dropped; threshold must be at or below the smallest positive score.
        return float(pos_scores[0])
    return float(pos_scores[max_dropped - 1] + 1e-6 if max_dropped > 0 else pos_scores[0])


def cv_scores_and_threshold(
    X: np.ndarray, y: np.ndarray, target_recall: float, seed: int = 1
) -> tuple[np.ndarray, float]:
    """Run stratified 5-fold CV to get out-of-fold decision-function scores, and
    pick the threshold that preserves ``target_recall`` on those OOF scores.

    Tuning the threshold on training-set scores would be too optimistic: the
    model fits training tighter than held-out data, so training margins are
    larger than test margins, and a threshold that gives 95% recall on train
    typically gives much lower recall on test. Using OOF scores for threshold
    tuning matches the basis that inference uses at serve time.
    """
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=seed)
    clf = LinearSVC(class_weight="balanced", dual="auto", random_state=seed)
    oof_scores = cross_val_predict(clf, X, y, cv=skf, method="decision_function")
    threshold = pick_threshold(oof_scores, y, target_recall)
    return oof_scores, threshold


def cv_eval(X: np.ndarray, y: np.ndarray, target_recall: float, seed: int = 1) -> dict[str, Any]:
    oof_scores, threshold = cv_scores_and_threshold(X, y, target_recall, seed)
    y_pred = (oof_scores >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, y_pred).ravel()
    return {
        "tp": int(tp),
        "fp": int(fp),
        "tn": int(tn),
        "fn": int(fn),
        "precision": tp / (tp + fp) if tp + fp else 0.0,
        "recall": tp / (tp + fn) if tp + fn else 0.0,
        "accuracy": (tp + tn) / len(y),
        "llm_call_rate": (tp + fp) / len(y),
        "threshold": float(threshold),
    }


def train_final(X: np.ndarray, y: np.ndarray, threshold: float, seed: int = 1) -> LinearSVC:
    """Train the final model on the full dataset. The threshold is carried
    over from the OOF tuning — it lives on the same scale as the decision
    function that inference will call on, because inference applies the full
    model's decision function to a single new embedding."""
    clf = LinearSVC(class_weight="balanced", dual="auto", random_state=seed)
    clf.fit(X, y)
    return clf


def write_model(
    clf: LinearSVC,
    threshold: float,
    target_recall: float,
    cv: dict[str, Any],
    embedding_model: str,
    training_samples: int,
    out_path: Path,
) -> None:
    payload = {
        "schema_version": 1,
        "model_type": "linear_svc",
        "embedding_model": embedding_model,
        "coef": clf.coef_[0].astype(float).tolist(),
        "intercept": float(clf.intercept_[0]),
        "threshold": float(threshold),
        "metadata": {
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "training_samples": training_samples,
            "target_recall": target_recall,
            "cv_precision": round(cv["precision"], 4),
            "cv_recall": round(cv["recall"], 4),
            "cv_accuracy": round(cv["accuracy"], 4),
            "cv_llm_call_rate": round(cv["llm_call_rate"], 4),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(json.dumps(payload).encode("utf-8"))
    out_path.write_bytes(buf.getvalue())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--embedding-model",
        default=DEFAULT_EMBEDDING_MODEL,
        help=f"Ollama embedding model (default: {DEFAULT_EMBEDDING_MODEL})",
    )
    parser.add_argument(
        "--ollama-host",
        default=DEFAULT_OLLAMA_HOST,
        help=f"Ollama host (default: {DEFAULT_OLLAMA_HOST})",
    )
    parser.add_argument(
        "--target-recall",
        type=float,
        default=DEFAULT_TARGET_RECALL,
        help=f"Positive-class recall the threshold must preserve (default: {DEFAULT_TARGET_RECALL})",
    )
    parser.add_argument(
        "--eval-only",
        action="store_true",
        help="Re-run CV eval against the committed model and print metrics. Does not retrain.",
    )
    args = parser.parse_args()

    print(f"Loading training data from {TRAINING_CSV}", file=sys.stderr)
    df = pd.read_csv(TRAINING_CSV)
    df["is_swe"] = df["is_swe"].astype(bool)
    titles = df["title"].tolist()
    y = df["is_swe"].astype(int).to_numpy()
    print(f"  {len(titles)} titles, {int(y.sum())} positive, {int((1 - y).sum())} negative", file=sys.stderr)

    print(f"Embedding via {args.ollama_host} model={args.embedding_model} ...", file=sys.stderr)
    X = asyncio.run(embed_all(titles, args.ollama_host, args.embedding_model))
    print(f"  embedded: {X.shape}", file=sys.stderr)

    if args.eval_only:
        cv = cv_eval(X, y, args.target_recall)
        print(json.dumps(cv, indent=2))
        return

    print(f"5-fold CV at target_recall={args.target_recall} ...", file=sys.stderr)
    cv = cv_eval(X, y, args.target_recall)
    threshold = cv["threshold"]
    print(
        f"  CV: precision={cv['precision']:.1%} recall={cv['recall']:.1%} "
        f"accuracy={cv['accuracy']:.1%} llm_call_rate={cv['llm_call_rate']:.1%} "
        f"threshold={threshold:.4f}",
        file=sys.stderr,
    )

    print("Training final model on full set ...", file=sys.stderr)
    clf = train_final(X, y, threshold)
    print(f"  coef shape: {clf.coef_.shape}, intercept: {clf.intercept_[0]:.4f}", file=sys.stderr)

    write_model(
        clf,
        threshold,
        args.target_recall,
        cv,
        embedding_model=args.embedding_model,
        training_samples=len(titles),
        out_path=MODEL_OUT,
    )
    size = MODEL_OUT.stat().st_size
    print(f"Wrote {MODEL_OUT} ({size} bytes, {size / 1024:.1f} KiB)", file=sys.stderr)


if __name__ == "__main__":
    main()
