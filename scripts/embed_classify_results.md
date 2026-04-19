# Embedding + classifier-head prototype — results (refs #36)

Prototype for issue [#36](https://github.com/maciej-makowski/are-they-hiring/issues/36):
can a pretrained embedding model + a tiny sklearn head beat the current
`qwen2.5:1.5b` LLM few-shot classifier (#35) on the 1381 hand-labelled titles?

Produced by `scripts/embed_classify_experiment.py`. Reproduce with:

```bash
uv run python scripts/embed_classify_experiment.py \
  --input /tmp/roles-to-label.csv \
  --l2-normalize --cv
```

Baseline to beat (qwen2.5:1.5b, chat+few-shot, full 1381 set):

> **accuracy=97.8%   precision=69.8%   recall=72.5%**

## Setup

- 1381 unique titles, 51 positives (~3.7%), 1330 negatives.
- Embeddings via Ollama `/api/embed` on `http://pop-os.home.lan:11434` (GPU).
- Sklearn heads: `LogisticRegression`, `LinearSVC`. Each tried with and without
  `class_weight="balanced"`.
- Two eval modes per combination:
  - **80/20 holdout** (seed=42, stratified) — matches the qwen baseline's eval.
  - **Stratified 5-fold CV (union of OOF predictions)** — stabilises
    precision/recall given that only ~10 positives land in a single 80/20 test
    split.
- Embeddings L2-normalized before fitting.
- `nomic-embed-text` inputs are prefixed with `"classification: "` (the
  task prefix Nomic's docs recommend for supervised classification).

## Candidate embedding models

| Model | Ollama disk size | Dim | Pi-viable? |
| --- | --- | --- | --- |
| `all-minilm`         | 46 MB  |  384 | Yes — trivial. |
| `nomic-embed-text`   | 274 MB |  768 | Yes. |
| `mxbai-embed-large`  | 670 MB | 1024 | Yes, tight. |
| `bge-m3`             | 1.2 GB | 1024 | Skipped — multilingual bloat, marginal size concern on 8 GB Pi alongside qwen2.5:1.5b and Postgres. |

Tiny sklearn pickles (10–20 KB each) are a rounding error on top of the
embedding model weights.

## Headline results (5-fold CV, L2-normalized, class_weight="balanced")

| Embedding model    | Head | Accuracy | Precision | Recall | tp | fp | fn | Dim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-minilm         | LogisticRegression | 94.28% | 38.71% | 94.12% |  48 |  76 |  3 |  384 |
| all-minilm         | LinearSVC          | 97.39% | 60.00% | 88.24% |  45 |  30 |  6 |  384 |
| nomic-embed-text   | LogisticRegression | 57.71% |  5.95% | 70.59% |  36 | 569 | 15 |  768 |
| nomic-embed-text   | LinearSVC          | 60.25% |  6.32% | 70.59% |  36 | 534 | 15 |  768 |
| mxbai-embed-large  | LogisticRegression | 91.53% | 29.63% | 94.12% |  48 | 114 |  3 | 1024 |
| mxbai-embed-large  | LinearSVC          | 96.23% | 49.45% | 88.24% |  45 |  46 |  6 | 1024 |

With `class_weight="balanced"` the heads are recall-biased. Accuracy is on par
with the baseline for the SVC variants, recall clearly beats the baseline (88%
vs 72.5%), but precision is substantially lower.

## Headline results (5-fold CV, L2-normalized, NO class balancing)

| Embedding model    | Head | Accuracy | Precision | Recall | tp | fp | fn | Dim |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| all-minilm         | LogisticRegression | 96.31% |  0.00% |  0.00% |   0 |  0 | 51 |  384 |
| **all-minilm**     | **LinearSVC**      | **97.90%** | **89.29%** | **49.02%** | **25** | **3** | **26** | **384** |
| nomic-embed-text   | LogisticRegression | 96.31% |  0.00% |  0.00% |   0 |  0 | 51 |  768 |
| nomic-embed-text   | LinearSVC          | 96.31% |  0.00% |  0.00% |   0 |  0 | 51 |  768 |
| mxbai-embed-large  | LogisticRegression | 96.31% |  0.00% |  0.00% |   0 |  0 | 51 | 1024 |
| mxbai-embed-large  | LinearSVC          | 97.39% | 82.61% | 37.25% |  19 |  4 | 32 | 1024 |

LogisticRegression without class balancing collapses to the majority class on
this ~4% positive rate. LinearSVC's hinge loss survives the imbalance.
**all-minilm + LinearSVC (no-balance) is the precision winner.**

## Precision/recall frontier (LR, no-balance, 5-fold CV, threshold swept)

### all-minilm (384d, 46 MB)

| Threshold | Accuracy | Precision | Recall | tp | fp | fn |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 84.94% | 19.46% | 98.04% | 50 | 207 |  1 |
| 0.10 | 94.42% | 39.34% | 94.12% | 48 |  74 |  3 |
| 0.15 | 96.74% | 54.69% | 68.63% | 35 |  29 | 16 |
| **0.20** | **97.47%** | **73.53%** | **49.02%** | **25** | **9** | **26** |
| 0.25 | 97.18% | 80.00% | 31.37% | 16 |   4 | 35 |
| 0.30 | 96.67% | 72.73% | 15.69% |  8 |   3 | 43 |

### mxbai-embed-large (1024d, 670 MB)

| Threshold | Accuracy | Precision | Recall | tp | fp | fn |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.05 | 83.71% | 18.25% | 98.04% | 50 | 224 |  1 |
| 0.10 | 94.13% | 37.70% | 90.20% | 46 |  76 |  5 |
| 0.15 | 96.74% | 54.84% | 66.67% | 34 |  28 | 17 |
| 0.20 | 96.81% | 62.96% | 33.33% | 17 |  10 | 34 |

### nomic-embed-text (768d, 274 MB)

Collapses to predict-all-zero at every threshold tested. Across the whole
sweep the best positive call is 5 false positives, 0 true positives. **This
embedding is not useful for the task**, with or without the recommended
`classification:` prefix.

## Comparison vs qwen2.5:1.5b baseline

| Configuration | Accuracy | Precision | Recall | Notes |
| --- | ---: | ---: | ---: | --- |
| **Baseline** qwen2.5:1.5b few-shot | **97.8%** | **69.8%** | **72.5%** | 1.5 B-parameter chat model, ~60 s to classify 1381 titles. |
| all-minilm + LinearSVC (no-balance, CV) | 97.9% | **89.3%** | 49.0% | **Precision +19.5 pp**, recall −23.5 pp. |
| all-minilm + LR, thr=0.20 (no-bal, CV) | 97.5% | 73.5% | 49.0% | Precision +3.7 pp, recall −23.5 pp. |
| all-minilm + LinearSVC (balanced, CV) | 97.4% | 60.0% | **88.2%** | Precision −9.8 pp, recall +15.7 pp. |
| mxbai-embed-large + LinearSVC (no-balance, CV) | 97.4% | 82.6% | 37.3% | Precision +12.8 pp, recall −35.2 pp. |

## Interpretation

- `all-minilm` (46 MB, 384-dim) is the clear winner among the three candidates.
  `mxbai-embed-large` is strictly worse despite being 14× larger, and
  `nomic-embed-text` is non-functional for this task in any configuration we
  tested.
- **The embedding approach can't match the baseline on both metrics
  simultaneously.** At every operating point the precision-recall curve stays
  Pareto-below the LLM baseline: we can cleanly beat it on one axis but not
  both at once.
  - Maximise precision (no class balancing + SVC): 89% precision at 49% recall
    — much stricter classifier than the baseline.
  - Maximise recall (balanced SVC): 88% recall at 60% precision — much noisier
    classifier than the baseline.
- The interesting operating point is *where the overall F1 is best* — which
  for all-minilm falls around the balanced-SVC result (F1 ≈ 0.71). The LLM
  baseline's F1 is ≈ 0.71 too. **The two approaches are roughly F1-equivalent,
  with different operating-point tradeoffs.**

## Pi viability

`all-minilm` at 46 MB is free real-estate on the Pi compared to the current
`qwen2.5:1.5b` at ~940 MB. Inference cost is negligible (embedding is a
single forward pass through a ~22 M-parameter bi-encoder; on pop-os GPU we
measured ~190 titles/s, which is CPU-bound on the Pi but still faster than
the current LLM path's ~16 titles/s). The sklearn head pickle is ~15 KB.

So Pi-wise: yes, easily. The bottleneck is quality, not cost.

## Recommendation: don't ship as a straight replacement

- The current qwen2.5:1.5b classifier at 69.8% precision / 72.5% recall is
  Pareto-optimal among the configurations we tested — no embedding variant
  dominates it on both metrics.
- 51 positive labels is tight for a 384-to-1024-dim classifier. The Pareto gap
  vs the LLM might close with 2–3× more labels, but that's a research bet.
- Where the embedding approach **is** interesting is as a **fast pre-filter**:
  the balanced variant catches 88% of positives with 60% precision in
  sub-millisecond time per title. A candidate architecture would run the
  embedding head first and only send titles it marks `yes` to the LLM for a
  precision check. That would cut LLM calls on the negative class by 98%
  (1300/1330) while only missing ~6/51 positives — worth a follow-up
  experiment but out of scope for this PR.

### Next steps if we want to pursue this

1. Collect more labels (target: 200+ positives) before re-running.
2. Try the two-stage pipeline (embedding screen → LLM verify) against the
   baseline on latency + accuracy.
3. Revisit `nomic-embed-text` with instruct-formatted input — the current
   failure mode is suspicious enough that it warrants a closer look, but
   all-minilm already covers the space.

## Artifacts

- Script: [`scripts/embed_classify_experiment.py`](embed_classify_experiment.py)
- Cached embeddings and classifier pickles: `scripts/cache/*.npz`, `scripts/cache/*.pkl`
- Raw JSON results: `scripts/cache/results.json`
