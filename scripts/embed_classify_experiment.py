#!/usr/bin/env python3
"""Embedding + tiny classifier head experiment (refs issue #36).

Loads the hand-labelled ground-truth CSV, embeds every title via Ollama, trains
LogisticRegression and LinearSVC heads, and reports accuracy / precision / recall
for each (embedding_model, classifier_head) pair against an 80/20 stratified split.

The baseline to beat (qwen2.5:1.5b, LLM few-shot classifier, same 1381 titles):
    accuracy=97.8%  precision=69.8%  recall=72.5%

This script caches embeddings to disk keyed on (model, title) so reruns are fast,
and saves the fitted classifiers as pickles alongside the cache.

Usage:
    uv run python scripts/embed_classify_experiment.py \\
        --input /tmp/roles-to-label.csv \\
        --ollama-host http://pop-os.home.lan:11434 \\
        --models all-minilm nomic-embed-text mxbai-embed-large

Ollama's /api/embed endpoint is used (Ollama >= 0.1.45). One request per title,
served sequentially — pop-os GPU handles ~100 titles/s for the small models.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import pickle
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import confusion_matrix
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.preprocessing import normalize
from sklearn.svm import LinearSVC

DEFAULT_MODELS = ["all-minilm", "nomic-embed-text", "mxbai-embed-large"]
DEFAULT_OLLAMA_HOST = "http://pop-os.home.lan:11434"
DEFAULT_INPUT = "/tmp/roles-to-label.csv"
DEFAULT_CACHE_DIR = Path("scripts/cache")
DEFAULT_CONCURRENCY = 8
DEFAULT_TIMEOUT = 60.0
RANDOM_STATE = 42  # stable split across reruns

# nomic-embed-text is trained with task-prefixed inputs. "classification:" is the
# supported prefix for supervised-classification use (see Ollama nomic docs).
MODEL_INPUT_PREFIX = {
    "nomic-embed-text": "classification: ",
}


@dataclass
class EvalResult:
    model: str
    head: str
    accuracy: float
    precision: float
    recall: float
    tp: int
    fp: int
    tn: int
    fn: int
    dim: int
    train_n: int
    test_n: int

    def format_row(self) -> str:
        return (
            f"| {self.model:<18} | {self.head:<20} | "
            f"{self.accuracy * 100:6.2f}% | {self.precision * 100:6.2f}% | "
            f"{self.recall * 100:6.2f}% | {self.tp:>3} | {self.fp:>3} | "
            f"{self.tn:>4} | {self.fn:>3} | {self.dim:>4} |"
        )


def load_labels(path: Path) -> tuple[list[str], np.ndarray]:
    titles: list[str] = []
    labels: list[int] = []
    seen: set[str] = set()
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        required = {"title", "your_label"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV is missing required columns: {missing}")
        for row in reader:
            title = (row.get("title") or "").strip()
            label = (row.get("your_label") or "").strip().lower()
            if not title or label not in {"yes", "no"}:
                continue
            if title in seen:
                continue
            seen.add(title)
            titles.append(title)
            labels.append(1 if label == "yes" else 0)
    y = np.asarray(labels, dtype=np.int64)
    return titles, y


def cache_path_for(cache_dir: Path, model: str) -> Path:
    safe = model.replace("/", "_").replace(":", "_")
    prefix = MODEL_INPUT_PREFIX.get(model, "")
    # Keep the filename deterministic; embed the prefix state in a short suffix
    # so a prefix change invalidates the cache automatically.
    suffix = ""
    if prefix:
        suffix = "-p" + hashlib.sha1(prefix.encode()).hexdigest()[:6]
    return cache_dir / f"embeddings-{safe}{suffix}.npz"


def load_embedding_cache(path: Path) -> dict[str, np.ndarray]:
    if not path.exists():
        return {}
    with np.load(path, allow_pickle=False) as data:
        titles = data["titles"]
        vectors = data["vectors"]
    return {str(t): vectors[i] for i, t in enumerate(titles)}


def save_embedding_cache(path: Path, cache: dict[str, np.ndarray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    titles = np.array(list(cache.keys()), dtype=str)
    vectors = np.stack(list(cache.values())).astype(np.float32)
    np.savez(path, titles=titles, vectors=vectors)


async def _embed_one(
    client: httpx.AsyncClient,
    host: str,
    model: str,
    title: str,
) -> tuple[str, np.ndarray]:
    prefix = MODEL_INPUT_PREFIX.get(model, "")
    response = await client.post(
        f"{host}/api/embed",
        json={"model": model, "input": f"{prefix}{title}"},
    )
    response.raise_for_status()
    payload = response.json()
    # /api/embed returns {"embeddings": [[...]], ...}; /api/embeddings returns
    # {"embedding": [...]}. Support both for forward/backward compatibility.
    if "embeddings" in payload:
        vector = np.asarray(payload["embeddings"][0], dtype=np.float32)
    elif "embedding" in payload:
        vector = np.asarray(payload["embedding"], dtype=np.float32)
    else:
        raise RuntimeError(f"Unexpected embed response for model={model}: {list(payload)[:5]}")
    return title, vector


async def embed_titles(
    titles: list[str],
    model: str,
    host: str,
    cache: dict[str, np.ndarray],
    concurrency: int,
    timeout: float,
) -> dict[str, np.ndarray]:
    missing = [t for t in titles if t not in cache]
    if not missing:
        return cache

    print(f"    embedding {len(missing)}/{len(titles)} titles (cache hit: {len(titles) - len(missing)})")
    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    total = len(missing)
    start = time.time()

    async def _wrap(client: httpx.AsyncClient, title: str) -> None:
        nonlocal completed
        async with semaphore:
            try:
                t, vec = await _embed_one(client, host, model, title)
            except Exception as exc:
                print(f"      error embedding {title!r}: {exc}")
                raise
        cache[t] = vec
        completed += 1
        if completed % 100 == 0 or completed == total:
            elapsed = time.time() - start
            rate = completed / elapsed if elapsed > 0 else 0
            print(f"      progress: {completed}/{total} ({rate:.1f} titles/s)")

    async with httpx.AsyncClient(timeout=timeout) as client:
        await asyncio.gather(*[_wrap(client, t) for t in missing])

    return cache


def _confusion_parts(y_true: np.ndarray, y_pred: np.ndarray) -> tuple[int, int, int, int]:
    # confusion_matrix labels order: [0, 1] -> rows truth, cols pred
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = cm.ravel()
    return int(tp), int(fp), int(tn), int(fn)


def evaluate_head(
    model: str,
    head_label: str,
    X_train: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_test: np.ndarray,
    head,
    out_pickle: Path,
) -> EvalResult:
    head.fit(X_train, y_train)
    y_pred = head.predict(X_test)
    tp, fp, tn, fn = _confusion_parts(y_test, y_pred)
    accuracy = (tp + tn) / max(tp + fp + tn + fn, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    out_pickle.parent.mkdir(parents=True, exist_ok=True)
    with open(out_pickle, "wb") as f:
        pickle.dump(head, f)
    return EvalResult(
        model=model,
        head=head_label,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        dim=int(X_train.shape[1]),
        train_n=int(X_train.shape[0]),
        test_n=int(X_test.shape[0]),
    )


def ensure_model_available(host: str, model: str, timeout: float) -> None:
    """Best-effort pull: if the embedding model isn't loaded on the Ollama host,
    ask Ollama to pull it. Pulls are idempotent. Blocks until completion."""
    try:
        resp = httpx.get(f"{host}/api/tags", timeout=10)
        resp.raise_for_status()
        names = {m["name"] for m in resp.json().get("models", [])}
    except Exception as exc:
        print(f"    warning: could not list models on {host}: {exc}")
        names = set()
    needed = model if ":" in model else f"{model}:latest"
    if model in names or needed in names:
        return
    print(f"    pulling {model} on {host} (one-time)...")
    with httpx.Client(timeout=timeout) as client:
        r = client.post(f"{host}/api/pull", json={"name": model, "stream": False})
        r.raise_for_status()


def _safe_model_slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "_")


def _cv_metrics(X: np.ndarray, y: np.ndarray, make_head) -> tuple[int, int, int, int]:
    """Aggregate confusion parts across stratified 5-fold CV predictions.

    We union the out-of-fold predictions and compute a single confusion matrix.
    This is the standard small-dataset approach to stabilise precision/recall when
    positives are rare (51/1381 here)."""
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    tp = fp = tn = fn = 0
    for tr_idx, te_idx in kf.split(X, y):
        head = make_head()
        head.fit(X[tr_idx], y[tr_idx])
        y_pred = head.predict(X[te_idx])
        a, b, c, d = _confusion_parts(y[te_idx], y_pred)
        tp += a
        fp += b
        tn += c
        fn += d
    return tp, fp, tn, fn


def _cv_threshold_sweep(X: np.ndarray, y: np.ndarray) -> list[tuple[float, int, int, int, int]]:
    """Aggregate out-of-fold LR probabilities across 5-fold CV, then sweep the
    decision threshold. Returns [(threshold, tp, fp, tn, fn), ...]."""
    kf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    proba = np.zeros(len(y), dtype=np.float64)
    for tr_idx, te_idx in kf.split(X, y):
        head = LogisticRegression(C=1.0, max_iter=5000, solver="liblinear", random_state=RANDOM_STATE)
        head.fit(X[tr_idx], y[tr_idx])
        proba[te_idx] = head.predict_proba(X[te_idx])[:, 1]
    rows = []
    for thr in [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50]:
        y_pred = (proba >= thr).astype(np.int64)
        tp, fp, tn, fn = _confusion_parts(y, y_pred)
        rows.append((thr, tp, fp, tn, fn))
    return rows


def _print_result(tag: str, res: EvalResult) -> None:
    print(
        f"    {tag} "
        f"acc={res.accuracy * 100:5.2f}% "
        f"prec={res.precision * 100:5.2f}% "
        f"rec={res.recall * 100:5.2f}% "
        f"(tp={res.tp} fp={res.fp} fn={res.fn})"
    )


def _eval_from_counts(
    model: str, head_label: str, tp: int, fp: int, tn: int, fn: int, dim: int, train_n: int, test_n: int
) -> EvalResult:
    accuracy = (tp + tn) / max(tp + fp + tn + fn, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    return EvalResult(
        model=model,
        head=head_label,
        accuracy=accuracy,
        precision=precision,
        recall=recall,
        tp=tp,
        fp=fp,
        tn=tn,
        fn=fn,
        dim=dim,
        train_n=train_n,
        test_n=test_n,
    )


async def run_experiment(
    csv_path: Path,
    ollama_host: str,
    models: list[str],
    cache_dir: Path,
    concurrency: int,
    timeout: float,
    l2_normalize: bool,
    cv: bool,
) -> list[EvalResult]:
    titles, y = load_labels(csv_path)
    print(f"Loaded {len(titles)} labelled titles ({int(y.sum())} yes / {len(y) - int(y.sum())} no)")

    train_titles, test_titles, y_train, y_test = train_test_split(
        titles,
        y,
        test_size=0.2,
        random_state=RANDOM_STATE,
        stratify=y,
    )
    print(
        f"Split: train={len(train_titles)} (yes={int(y_train.sum())}) test={len(test_titles)} (yes={int(y_test.sum())})"
    )
    if l2_normalize:
        print("Embeddings will be L2-normalized before fitting.")
    if cv:
        print("Also running stratified 5-fold CV for stabilised precision/recall.")

    def make_lr():
        return LogisticRegression(
            C=1.0,
            class_weight="balanced",
            max_iter=5000,
            solver="liblinear",
            random_state=RANDOM_STATE,
        )

    def make_svm():
        return LinearSVC(
            C=1.0,
            class_weight="balanced",
            max_iter=5000,
            random_state=RANDOM_STATE,
        )

    def make_lr_nobal():
        return LogisticRegression(
            C=1.0,
            max_iter=5000,
            solver="liblinear",
            random_state=RANDOM_STATE,
        )

    def make_svm_nobal():
        return LinearSVC(
            C=1.0,
            max_iter=5000,
            random_state=RANDOM_STATE,
        )

    results: list[EvalResult] = []
    for model in models:
        print(f"\n=== {model} ===")
        ensure_model_available(ollama_host, model, timeout=600.0)
        cache_path = cache_path_for(cache_dir, model)
        cache = load_embedding_cache(cache_path)
        cache = await embed_titles(titles, model, ollama_host, cache, concurrency=concurrency, timeout=timeout)
        save_embedding_cache(cache_path, cache)

        X_all = np.stack([cache[t] for t in titles]).astype(np.float32)
        X_train = np.stack([cache[t] for t in train_titles]).astype(np.float32)
        X_test = np.stack([cache[t] for t in test_titles]).astype(np.float32)
        if l2_normalize:
            X_all = normalize(X_all)
            X_train = normalize(X_train)
            X_test = normalize(X_test)

        slug = _safe_model_slug(model)
        lr_pickle = cache_dir / f"classifier-{slug}-lr.pkl"
        res_lr = evaluate_head(model, "LogisticRegression", X_train, X_test, y_train, y_test, make_lr(), lr_pickle)
        _print_result("LogReg ", res_lr)
        results.append(res_lr)

        svm_pickle = cache_dir / f"classifier-{slug}-svm.pkl"
        res_svm = evaluate_head(model, "LinearSVC", X_train, X_test, y_train, y_test, make_svm(), svm_pickle)
        _print_result("SVM    ", res_svm)
        results.append(res_svm)

        # Also try the unbalanced heads — they trade recall for precision, which is
        # what the baseline actually optimises for.
        lr_nb_pickle = cache_dir / f"classifier-{slug}-lr-nobal.pkl"
        res_lr_nb = evaluate_head(
            model,
            "LogisticRegression (no class_weight)",
            X_train,
            X_test,
            y_train,
            y_test,
            make_lr_nobal(),
            lr_nb_pickle,
        )
        _print_result("LR-nb  ", res_lr_nb)
        results.append(res_lr_nb)

        svm_nb_pickle = cache_dir / f"classifier-{slug}-svm-nobal.pkl"
        res_svm_nb = evaluate_head(
            model,
            "LinearSVC (no class_weight)",
            X_train,
            X_test,
            y_train,
            y_test,
            make_svm_nobal(),
            svm_nb_pickle,
        )
        _print_result("SVM-nb ", res_svm_nb)
        results.append(res_svm_nb)

        if cv:
            for label, factory in [
                ("LogisticRegression (5-fold CV)", make_lr),
                ("LinearSVC (5-fold CV)", make_svm),
                ("LogisticRegression no-balance (5-fold CV)", make_lr_nobal),
                ("LinearSVC no-balance (5-fold CV)", make_svm_nobal),
            ]:
                tp, fp, tn, fn = _cv_metrics(X_all, y, factory)
                res = _eval_from_counts(
                    model,
                    label,
                    tp,
                    fp,
                    tn,
                    fn,
                    dim=int(X_all.shape[1]),
                    train_n=int(len(y) * 0.8),
                    test_n=int(len(y)),
                )
                _print_result(f"CV[{label[:30]:<30}]", res)
                results.append(res)

            # Threshold sweep on no-balance LR probabilities — shows the full
            # precision/recall frontier for this embedding, rather than just the
            # operating point sklearn's default decision rule picks.
            print("    threshold sweep (LR no-balance, 5-fold CV):")
            print(f"      {'thr':>5}  {'acc':>7}  {'prec':>7}  {'recall':>7}  {'tp':>3}  {'fp':>3}  {'fn':>3}")
            for thr, tp, fp, tn, fn in _cv_threshold_sweep(X_all, y):
                acc = (tp + tn) / max(tp + fp + tn + fn, 1)
                prec = tp / max(tp + fp, 1)
                rec = tp / max(tp + fn, 1)
                line = (
                    f"      {thr:>5.2f}  {acc * 100:6.2f}%  "
                    f"{prec * 100:6.2f}%  {rec * 100:6.2f}%  "
                    f"{tp:>3}  {fp:>3}  {fn:>3}"
                )
                print(line)
                results.append(
                    _eval_from_counts(
                        model,
                        f"LR-thr={thr:.2f} (5-fold CV)",
                        tp,
                        fp,
                        tn,
                        fn,
                        dim=int(X_all.shape[1]),
                        train_n=int(len(y) * 0.8),
                        test_n=int(len(y)),
                    )
                )

    return results


def write_results_json(results: list[EvalResult], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [
        {
            "model": r.model,
            "head": r.head,
            "accuracy": r.accuracy,
            "precision": r.precision,
            "recall": r.recall,
            "tp": r.tp,
            "fp": r.fp,
            "tn": r.tn,
            "fn": r.fn,
            "dim": r.dim,
            "train_n": r.train_n,
            "test_n": r.test_n,
        }
        for r in results
    ]
    path.write_text(json.dumps(payload, indent=2) + "\n")


def print_summary(results: list[EvalResult]) -> None:
    print("\n" + "=" * 110)
    print("SUMMARY (80/20 stratified hold-out, seed=42)")
    print("=" * 110)
    header = (
        f"| {'model':<18} | {'head':<20} | "
        f"{'acc':>7} | {'prec':>7} | {'recall':>7} | "
        f"{'tp':>3} | {'fp':>3} | {'tn':>4} | {'fn':>3} | {'dim':>4} |"
    )
    sep = "|" + "|".join(["-" * (len(s) + 2) for s in header.strip("|").split("|")]) + "|"
    print(header)
    print(sep)
    for r in results:
        print(r.format_row())
    print(
        "\nBaseline to beat (qwen2.5:1.5b LLM few-shot, same 1381 labels, full set):\n"
        "  accuracy=97.8%  precision=69.8%  recall=72.5%"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(DEFAULT_INPUT))
    parser.add_argument("--ollama-host", default=DEFAULT_OLLAMA_HOST)
    parser.add_argument("--models", nargs="+", default=DEFAULT_MODELS)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    parser.add_argument(
        "--l2-normalize",
        action="store_true",
        help="L2-normalize embeddings before fitting (standard for cosine-style heads).",
    )
    parser.add_argument(
        "--cv",
        action="store_true",
        help="Also report stratified 5-fold CV metrics (more stable than the single 80/20 split).",
    )
    parser.add_argument(
        "--results-json",
        type=Path,
        default=Path("scripts/cache/results.json"),
        help="Where to write the raw JSON results",
    )
    args = parser.parse_args(argv)

    if not args.input.exists():
        print(f"input CSV not found: {args.input}", file=sys.stderr)
        return 2

    results = asyncio.run(
        run_experiment(
            csv_path=args.input,
            ollama_host=args.ollama_host,
            models=args.models,
            cache_dir=args.cache_dir,
            concurrency=args.concurrency,
            timeout=args.timeout,
            l2_normalize=args.l2_normalize,
            cv=args.cv,
        )
    )
    print_summary(results)
    write_results_json(results, args.results_json)
    print(f"\nResults JSON written to {args.results_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
