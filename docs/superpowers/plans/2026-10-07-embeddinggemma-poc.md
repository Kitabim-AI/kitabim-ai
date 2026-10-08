# EmbeddingGemma 2 Local Embedding PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether EmbeddingGemma 2 (text encoder only, CPU) retrieves Uyghur book passages nearly as well as `gemini-embedding-2`, and produce a GO/NO-GO report.

**Architecture:** A self-contained Python package `egpoc` under `scripts/poc/embeddinggemma/`, run inside a CPU-only Docker container with the repo mounted. It reuses backend-core's `clean_uyghur_text` and `chunking_service` (imported, never modified), writes only to a throwaway `poc` Postgres schema in the local DB, evaluates with exact cosine search in NumPy, and renders `docs/poc/embeddinggemma/REPORT.md`.

**Tech Stack:** Python 3.13, CPU PyTorch, sentence-transformers, asyncpg + pgvector, NumPy, google-genai / Gemini REST, pytest.

**Spec:** `docs/superpowers/specs/2026-10-07-embeddinggemma-poc-design.md`

## Global Constraints

- No changes to `packages/`, `services/`, `apps/`, or `packages/backend-core/migrations/`. The PoC only *imports* `app.utils.text.clean_uyghur_text`, `app.services.chunking_service.chunking_service`, `app.core.config.settings`, `app.utils.observability.{log_json, configure_logging}`.
- Writes only to schema `poc` in the local DB. Never write to `public.chunks` or any prod table. Never connect to prod.
- CPU only: no MPS/CUDA. Gemma runs in float32 (model card: "Do not use float16").
- Gemma loaded text-only: `config_kwargs={"vision_config": None, "audio_config": None}`; queries `prompt_name="SearchQuery"`, documents `prompt_name="Document"`.
- Gemini baseline: `gemini-embedding-2`, `outputDimensionality=3072`, no `task_type`, interactive `batchEmbedContents` / `embedContent` — same request shape as `GeminiEmbeddings` in `packages/backend-core/app/llm/models.py`.
- No `print()` — use `log_json(logger, level, "message", key=value)` after `configure_logging()`.
- Test volumes: ئانا يۇرت `631481d3a7e9`, `683238d33c15`, `f0a9bc581a27`; لېيىغان بۇلاق `dbd310c05e85`, `b3b122b72df7`, `f24b85bcf8a2`, `336119148ffb`, `9c88386eaae3`, `efb8b34926ba`, `b7e6e5b5bb19`.
- Seed `7` everywhere randomness is used. Distractor budget ~40,000 chunks. Stop if offset fallback rate > 5%.
- Go/no-go: Recall@25 ≥ 95% of Gemini's (both question sets, pool scope); nDCG@10 drop ≤ 0.03; 500-page book ≤ 30 min; query p95 < 150 ms.
- Commit only the files a task names — the working tree has an unrelated modified `apps/frontend/src/config.ts` that must never be staged.
- `data/` is already gitignored repo-wide; all generated artifacts go in `scripts/poc/embeddinggemma/data/`.

## File Structure

```
scripts/poc/embeddinggemma/
  Dockerfile              CPU image (torch CPU + sentence-transformers + DB/Gemini clients)
  requirements.poc.txt    Python deps for the image
  run.sh                  docker build + run wrapper (CPU/RAM limits, env, mounts)
  pytest.ini              PoC-local pytest config
  README.md               How to run each stage
  egpoc/
    __init__.py
    config.py             All constants from the spec
    db.py                 asyncpg connection with pgvector registered; schema setup
    schema.sql            poc schema DDL
    offsets.py            Locate chunk text inside cleaned page text (pure)
    vectors.py            Normalize / truncate / exact top-k (pure)
    metrics.py            success@k, MRR, nDCG, aggregation (pure)
    filters.py            Uyghur word split, trigram overlap, script check (pure)
    prompts.py            Question-generation and relevance-judge prompts
    gemini.py             Gemini embeddings (REST) + JSON generation (google-genai)
    gemma.py              EmbeddingGemma 2 text-only CPU embedder
    pool.py               Split books, select distractors, build poc.chunks (CLI)
    questions.py          Synthetic question generation + review export/apply (CLI)
    sanity.py             Stage 0 go/no-go (CLI)
    embed_pool.py         Fill emb_gemma / emb_gemini (CLI, resumable)
    queries.py            Query-embedding cache
    pool_index.py         In-memory pool matrices + ranking + relevance masks
    real_questions.py     Sample logged global questions (CLI)
    judge.py              Pooled blind relevance judging (CLI)
    evaluate.py           Compute all metrics -> data/results.json (CLI)
    bench.py              CPU throughput / latency / RAM -> data/bench.json (CLI)
    report.py             Go/no-go decision + REPORT.md rendering (CLI)
  tests/
    test_smoke.py  test_offsets.py  test_vectors.py  test_metrics.py  test_filters.py
    test_questions.py  test_pool.py  test_sanity.py  test_pool_index.py  test_report.py
docs/poc/embeddinggemma/REPORT.md   (generated in Task 14)
```

All commands below are run from the repo root `/Users/Omarjan/Projects/kitabim-ai`. `PT` is shorthand for:

```bash
./scripts/poc/embeddinggemma/run.sh pytest -c scripts/poc/embeddinggemma/pytest.ini
```

---

### Task 1: Container, package skeleton, smoke test

**Files:**
- Create: `scripts/poc/embeddinggemma/Dockerfile`, `requirements.poc.txt`, `run.sh`, `pytest.ini`, `README.md`
- Create: `scripts/poc/embeddinggemma/egpoc/__init__.py`, `egpoc/config.py`
- Test: `scripts/poc/embeddinggemma/tests/test_smoke.py`

**Interfaces:**
- Produces: `egpoc.config` constants used by every later task (names below are final).

- [ ] **Step 0: Branch**

```bash
git checkout -b poc/embeddinggemma
```

- [ ] **Step 1: Write `requirements.poc.txt`**

```
asyncpg==0.31.0
pgvector==0.4.2
numpy
aiohttp
google-genai
python-dotenv
sentence-transformers
transformers
pytest
pytest-asyncio
```

- [ ] **Step 2: Write `Dockerfile`**

```dockerfile
FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# CPU-only torch first so sentence-transformers does not pull a GPU build.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch

COPY requirements.poc.txt /tmp/requirements.poc.txt
RUN pip install --no-cache-dir -r /tmp/requirements.poc.txt

WORKDIR /repo
```

- [ ] **Step 3: Write `run.sh`** and `chmod +x` it

```bash
#!/usr/bin/env bash
# Run a command inside the CPU-only PoC container with the repo mounted at /repo.
# Usage: ./scripts/poc/embeddinggemma/run.sh python -m egpoc.sanity
# CPU/RAM limits default to 4 CPUs / 8 GB until the prod worker spec is confirmed.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
POC="$ROOT/scripts/poc/embeddinggemma"
IMAGE="kitabim-egpoc:local"
CPUS="${POC_CPUS:-4}"
MEMORY="${POC_MEMORY:-8g}"

docker build -q -t "$IMAGE" "$POC" >/dev/null

DB_URL="$(grep -E '^DATABASE_URL=' "$ROOT/.env" | cut -d= -f2- | sed -E 's/(127\.0\.0\.1|localhost)/host.docker.internal/')"
TTY_FLAG=""
if [ -t 1 ]; then TTY_FLAG="-t"; fi

exec docker run --rm -i $TTY_FLAG \
  --cpus "$CPUS" --memory "$MEMORY" \
  --env-file "$ROOT/.env" \
  -e DATABASE_URL="$DB_URL" \
  -e OMP_NUM_THREADS="$CPUS" \
  -e POC_CPUS="$CPUS" \
  -e POC_MEMORY="$MEMORY" \
  -e HF_HOME=/hf \
  -e PYTHONPATH=/repo/packages/backend-core:/repo/scripts/poc/embeddinggemma \
  -v kitabim-egpoc-hf:/hf \
  -v "$ROOT":/repo \
  -w /repo \
  "$IMAGE" "$@"
```

- [ ] **Step 4: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
```

- [ ] **Step 5: Write `egpoc/__init__.py`** (empty file) **and `egpoc/config.py`**

```python
"""PoC constants. Values are copied from the design spec — change them there first."""

from pathlib import Path

POC_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = POC_DIR / "data"
REPO_ROOT = POC_DIR.parents[2]
REPORT_PATH = REPO_ROOT / "docs" / "poc" / "embeddinggemma" / "REPORT.md"

STRATEGY = "current"
SEED = 7

TEST_TITLES = ("ئانا يۇرت", "لېيىغان بۇلاق")
TEST_BOOK_IDS = (
    "631481d3a7e9", "683238d33c15", "f0a9bc581a27",
    "dbd310c05e85", "b3b122b72df7", "f24b85bcf8a2", "336119148ffb",
    "9c88386eaae3", "efb8b34926ba", "b7e6e5b5bb19",
)
DISTRACTOR_CHUNK_BUDGET = 40_000
MAX_FALLBACK_RATE = 0.05

MIN_PASSAGE_CHARS = 200
SANITY_N = 50
SYNTHETIC_TARGET = 300
SYNTHETIC_OVERSAMPLE = 330
REVIEW_N = 30
MAX_REVIEW_FLAG_RATE = 0.20
REAL_TARGET = 200
TRIGRAM_REJECT = 0.40
LLM_CONCURRENCY = 8

GEMMA_MODEL_ID = "google/embeddinggemma-2"
GEMMA_DIMS = (768, 512, 256)
GEMINI_EMBED_MODEL = "gemini-embedding-2"
GEMINI_DIM = 3072
GEMINI_EMBED_BATCH = 50
GEN_MODEL = "gemini-3.1-flash-lite"

# variant name -> (poc.chunks column, dimension)
VARIANTS = {
    "gemini": ("emb_gemini", GEMINI_DIM),
    "gemma768": ("emb_gemma", 768),
    "gemma512": ("emb_gemma", 512),
    "gemma256": ("emb_gemma", 256),
}
K_VALUES = (5, 10, 25)
TOP_K = 25

SANITY_MIN_TOP1 = 0.70
SANITY_MIN_RATIO = 0.80
BYTE_FALLBACK_WARN = 0.20

RECALL_RATIO_MIN = 0.95
NDCG_MAX_DROP = 0.03
BOOK_MINUTES_MAX = 30.0
QUERY_P95_MS_MAX = 150.0
BENCH_PAGES = 500
BENCH_DOC_SAMPLE = 2000
BENCH_QUERY_SAMPLE = 200
```

- [ ] **Step 6: Write the smoke test `tests/test_smoke.py`**

```python
from app.services.chunking_service import chunking_service
from app.utils.text import clean_uyghur_text

from egpoc import config


def test_backend_core_chunker_importable():
    text = clean_uyghur_text("بىرىنچى ئابزاس.\n\nئىككىنچى ئابزاس.")
    assert chunking_service.split_text(text)


def test_test_books_configured():
    assert len(config.TEST_BOOK_IDS) == 10
    assert config.REPORT_PATH.parts[-3:] == ("poc", "embeddinggemma", "REPORT.md")
```

- [ ] **Step 7: Build and run**

Run: `PT -q`  (first run builds the image — several minutes)
Expected: `2 passed`

- [ ] **Step 8: Write `README.md`**

```markdown
# EmbeddingGemma 2 PoC

Spec: `docs/superpowers/specs/2026-10-07-embeddinggemma-poc-design.md`
Plan: `docs/superpowers/plans/2026-10-07-embeddinggemma-poc.md`

Everything runs CPU-only in Docker: `./scripts/poc/embeddinggemma/run.sh <command>`.
Override limits with `POC_CPUS=8 POC_MEMORY=16g ./scripts/poc/...` to match the prod worker VM.
Generated files live in `scripts/poc/embeddinggemma/data/` (gitignored).

| Stage | Command |
|---|---|
| Tests | `run.sh pytest -c scripts/poc/embeddinggemma/pytest.ini -q` |
| 0 Sanity | `run.sh python -m egpoc.sanity` |
| 1 Pool | `run.sh python -m egpoc.pool build` |
| 1 Embed | `run.sh python -m egpoc.embed_pool gemma` / `gemini` |
| 2 Synthetic | `run.sh python -m egpoc.questions build` → `export-review` → edit `data/review.csv` → `apply-review` |
| 2 Real | `run.sh python -m egpoc.real_questions` → `run.sh python -m egpoc.judge` |
| 3 Evaluate | `run.sh python -m egpoc.evaluate` |
| 3 Bench | `run.sh python -m egpoc.bench` |
| Report | `run.sh python -m egpoc.report` |

Cleanup: `psql "$DATABASE_URL" -c 'DROP SCHEMA poc CASCADE'` and `docker volume rm kitabim-egpoc-hf`.
```

- [ ] **Step 9: Commit**

```bash
git add scripts/poc/embeddinggemma/Dockerfile scripts/poc/embeddinggemma/requirements.poc.txt \
  scripts/poc/embeddinggemma/run.sh scripts/poc/embeddinggemma/pytest.ini scripts/poc/embeddinggemma/README.md \
  scripts/poc/embeddinggemma/egpoc/__init__.py scripts/poc/embeddinggemma/egpoc/config.py \
  scripts/poc/embeddinggemma/tests/test_smoke.py
git commit -m "chore(poc): scaffold EmbeddingGemma PoC container and config"
```

---

### Task 2: Chunk offset location

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/offsets.py`
- Test: `scripts/poc/embeddinggemma/tests/test_offsets.py`

**Interfaces:**
- Produces: `Span(start: int, end: int, exact: bool)` (frozen dataclass); `locate_chunks(page_text: str, chunks: list[str]) -> list[Span]` — one span per chunk, same order. `exact=False` means fallback to the whole page `(0, len(page_text))`.

- [ ] **Step 1: Write the failing tests**

```python
from egpoc.offsets import Span, locate_chunks


def test_exact_substrings_with_overlap():
    page = "aaa bbb ccc"
    assert locate_chunks(page, ["aaa bbb", "bbb ccc"]) == [Span(0, 7, True), Span(4, 11, True)]


def test_repeated_text_advances_past_previous_start():
    page = "x y x y"
    assert locate_chunks(page, ["x y", "x y"]) == [Span(0, 3, True), Span(4, 7, True)]


def test_whitespace_normalized_match_maps_to_original_offsets():
    page = "aaa\n\nbbb ccc"
    assert locate_chunks(page, ["aaa bbb"]) == [Span(0, 8, True)]


def test_unlocatable_chunk_falls_back_to_whole_page():
    page = "aaa bbb"
    assert locate_chunks(page, ["zzz"]) == [Span(0, 7, False)]


def test_uyghur_text():
    page = "مەن كىتاب ئوقۇدۇم.\n\nئۇ ناھايىتى قىزىقارلىق ئىدى."
    spans = locate_chunks(page, ["ئۇ ناھايىتى قىزىقارلىق ئىدى."])
    assert page[spans[0].start:spans[0].end] == "ئۇ ناھايىتى قىزىقارلىق ئىدى."


def test_empty_chunks():
    assert locate_chunks("abc", []) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `PT tests/test_offsets.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'egpoc.offsets'`

- [ ] **Step 3: Implement `egpoc/offsets.py`**

```python
"""Locate each chunk's character range inside the cleaned page text it was split from."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    exact: bool


def _normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Collapse whitespace runs to one space; map each normalized index to its original index."""
    chars: list[str] = []
    index: list[int] = []
    for i, ch in enumerate(text):
        if ch.isspace():
            if chars and chars[-1] == " ":
                continue
            chars.append(" ")
        else:
            chars.append(ch)
        index.append(i)
    return "".join(chars), index


def locate_chunks(page_text: str, chunks: list[str]) -> list[Span]:
    norm_page, norm_map = _normalize_with_map(page_text)
    spans: list[Span] = []
    cursor = -1  # start of the previous located chunk; overlap means the next one starts after it
    for chunk in chunks:
        pos = page_text.find(chunk, cursor + 1)
        if pos == -1:
            pos = page_text.find(chunk)
        if pos != -1:
            spans.append(Span(pos, pos + len(chunk), True))
            cursor = pos
            continue
        norm_chunk = _normalize_with_map(chunk)[0].strip()
        npos = norm_page.find(norm_chunk) if norm_chunk else -1
        if npos != -1:
            start = norm_map[npos]
            end = norm_map[npos + len(norm_chunk) - 1] + 1
            spans.append(Span(start, end, True))
            cursor = start
            continue
        spans.append(Span(0, len(page_text), False))
    return spans
```

- [ ] **Step 4: Run tests**

Run: `PT tests/test_offsets.py -q`
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/offsets.py scripts/poc/embeddinggemma/tests/test_offsets.py
git commit -m "feat(poc): locate chunk offsets within cleaned page text"
```

---

### Task 3: Vector math and retrieval metrics

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/vectors.py`, `egpoc/metrics.py`
- Test: `scripts/poc/embeddinggemma/tests/test_vectors.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces:
  - `l2_normalize(m: np.ndarray) -> np.ndarray` (rows, or a single vector)
  - `truncate_normalize(m: np.ndarray, dim: int) -> np.ndarray` (float32)
  - `top_k(doc_matrix: np.ndarray, query: np.ndarray, k: int, mask: np.ndarray | None = None) -> np.ndarray` — row indices, best first; masked-out rows never returned
  - `success_at_k(rels: list[bool], k: int) -> float`, `mrr_at_k(rels, k) -> float`, `ndcg_at_k(rels, k, n_relevant: int) -> float`, `first_hit_rank(rels) -> int | None` (1-based)
  - `aggregate(per_query: list[tuple[list[bool], int]]) -> dict[str, float]` with keys `success@5`, `success@10`, `success@25`, `mrr@10`, `ndcg@10`, `n`

- [ ] **Step 1: Write failing tests `tests/test_vectors.py`**

```python
import numpy as np

from egpoc.vectors import l2_normalize, top_k, truncate_normalize


def test_l2_normalize_rows_and_zero_row():
    m = l2_normalize(np.array([[3.0, 4.0], [0.0, 0.0]]))
    assert np.allclose(m[0], [0.6, 0.8])
    assert np.allclose(m[1], [0.0, 0.0])


def test_truncate_normalize_renormalizes():
    m = truncate_normalize(np.array([[3.0, 4.0, 12.0]]), 2)
    assert m.dtype == np.float32
    assert np.allclose(m, [[0.6, 0.8]])


def test_top_k_orders_best_first():
    docs = np.array([[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071]])
    assert top_k(docs, np.array([1.0, 0.0]), 2).tolist() == [0, 2]


def test_top_k_respects_mask_and_small_candidate_set():
    docs = np.array([[1.0, 0.0], [0.0, 1.0], [0.7071, 0.7071]])
    mask = np.array([False, True, True])
    assert top_k(docs, np.array([1.0, 0.0]), 5, mask).tolist() == [2, 1]
```

- [ ] **Step 2: Write failing tests `tests/test_metrics.py`**

```python
import math

from egpoc.metrics import aggregate, first_hit_rank, mrr_at_k, ndcg_at_k, success_at_k

RELS = [False, True, False]


def test_success_at_k():
    assert success_at_k(RELS, 1) == 0.0
    assert success_at_k(RELS, 2) == 1.0


def test_mrr_and_first_hit():
    assert mrr_at_k(RELS, 10) == 0.5
    assert mrr_at_k(RELS, 1) == 0.0
    assert first_hit_rank(RELS) == 2
    assert first_hit_rank([False]) is None


def test_ndcg_single_relevant():
    assert math.isclose(ndcg_at_k(RELS, 10, 1), 1 / math.log2(3))


def test_ndcg_zero_relevant_is_zero():
    assert ndcg_at_k([False], 10, 0) == 0.0


def test_aggregate_means():
    out = aggregate([([True], 1), ([False, True], 1)])
    assert out["n"] == 2
    assert out["success@5"] == 1.0
    assert out["mrr@10"] == 0.75
```

- [ ] **Step 3: Run to verify failure**

Run: `PT tests/test_vectors.py tests/test_metrics.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `egpoc/vectors.py`**

```python
"""Exact cosine retrieval over L2-normalized matrices."""

import numpy as np


def l2_normalize(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=-1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def truncate_normalize(m: np.ndarray, dim: int) -> np.ndarray:
    """Matryoshka truncation: keep the first `dim` components, then re-normalize."""
    return l2_normalize(np.asarray(m, dtype=np.float32)[..., :dim])


def top_k(doc_matrix: np.ndarray, query: np.ndarray, k: int, mask: np.ndarray | None = None) -> np.ndarray:
    scores = doc_matrix @ query
    if mask is not None:
        scores = np.where(mask, scores, -np.inf)
    k = min(k, int(np.isfinite(scores).sum()))
    if k == 0:
        return np.empty(0, dtype=np.int64)
    idx = np.argpartition(-scores, k - 1)[:k]
    return idx[np.argsort(-scores[idx], kind="stable")]
```

- [ ] **Step 5: Implement `egpoc/metrics.py`**

```python
"""Binary-relevance ranking metrics."""

import math

from egpoc.config import K_VALUES


def success_at_k(rels: list[bool], k: int) -> float:
    return 1.0 if any(rels[:k]) else 0.0


def first_hit_rank(rels: list[bool]) -> int | None:
    for i, r in enumerate(rels):
        if r:
            return i + 1
    return None


def mrr_at_k(rels: list[bool], k: int) -> float:
    rank = first_hit_rank(rels[:k])
    return 1.0 / rank if rank else 0.0


def ndcg_at_k(rels: list[bool], k: int, n_relevant: int) -> float:
    ideal_n = min(k, n_relevant)
    if ideal_n == 0:
        return 0.0
    dcg = sum(1.0 / math.log2(i + 2) for i, r in enumerate(rels[:k]) if r)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_n))
    return dcg / idcg


def aggregate(per_query: list[tuple[list[bool], int]]) -> dict[str, float]:
    n = len(per_query)
    out: dict[str, float] = {"n": n}
    for k in K_VALUES:
        out[f"success@{k}"] = sum(success_at_k(r, k) for r, _ in per_query) / n
    out["mrr@10"] = sum(mrr_at_k(r, 10) for r, _ in per_query) / n
    out["ndcg@10"] = sum(ndcg_at_k(r, 10, nr) for r, nr in per_query) / n
    return out
```

- [ ] **Step 6: Run tests**

Run: `PT tests/test_vectors.py tests/test_metrics.py -q`
Expected: `9 passed`

- [ ] **Step 7: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/vectors.py scripts/poc/embeddinggemma/egpoc/metrics.py \
  scripts/poc/embeddinggemma/tests/test_vectors.py scripts/poc/embeddinggemma/tests/test_metrics.py
git commit -m "feat(poc): add exact cosine top-k and retrieval metrics"
```

---

### Task 4: Uyghur text filters

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/filters.py`
- Test: `scripts/poc/embeddinggemma/tests/test_filters.py`

**Interfaces:**
- Produces: `uyghur_words(text: str) -> list[str]`, `trigram_overlap(question: str, passage: str) -> float` (share of the question's word trigrams found in the passage; 0.0 if the question has < 3 words), `has_latin(text: str) -> bool`, `is_arabic_script(text: str) -> bool` (≥ 50% of letters in the Arabic Unicode blocks).

- [ ] **Step 1: Write failing tests**

```python
from egpoc.filters import has_latin, is_arabic_script, trigram_overlap, uyghur_words


def test_uyghur_words_strips_uyghur_punctuation():
    assert uyghur_words("ئۇ كىم؟ مەن، سەن.") == ["ئۇ", "كىم", "مەن", "سەن"]


def test_trigram_overlap_identical_and_disjoint():
    text = "مەن بۈگۈن مەكتەپكە باردىم"
    assert trigram_overlap(text, text) == 1.0
    assert trigram_overlap("بىر ئىككى ئۈچ تۆت", text) == 0.0


def test_trigram_overlap_short_question_is_zero():
    assert trigram_overlap("كىم ئۇ", "كىم ئۇ") == 0.0


def test_script_checks():
    assert has_latin("ئۇ kim")
    assert not has_latin("ئۇ كىم")
    assert is_arabic_script("ئانا يۇرت قانداق كىتاب؟")
    assert not is_arabic_script("what is ana yurt")
```

- [ ] **Step 2: Run to verify failure**

Run: `PT tests/test_filters.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `egpoc/filters.py`**

```python
"""Lightweight Uyghur text checks used to filter generated and logged questions."""

import re

_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)
_LATIN = re.compile(r"[A-Za-z]")
_ARABIC = re.compile(r"[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]")


def uyghur_words(text: str) -> list[str]:
    return [w for w in _NON_WORD.split(text) if w]


def _trigrams(words: list[str]) -> set[tuple[str, ...]]:
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def trigram_overlap(question: str, passage: str) -> float:
    q = _trigrams(uyghur_words(question))
    if not q:
        return 0.0
    return len(q & _trigrams(uyghur_words(passage))) / len(q)


def has_latin(text: str) -> bool:
    return bool(_LATIN.search(text))


def is_arabic_script(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _ARABIC.match(c)) / len(letters) >= 0.5
```

- [ ] **Step 4: Run tests**

Run: `PT tests/test_filters.py -q`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/filters.py scripts/poc/embeddinggemma/tests/test_filters.py
git commit -m "feat(poc): add Uyghur word, trigram-overlap and script filters"
```

---

### Task 5: Embedders (Gemma CPU, Gemini REST) and JSON generation

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/gemma.py`, `egpoc/gemini.py`

**Interfaces:**
- Consumes: `egpoc.vectors.l2_normalize`, config constants.
- Produces:
  - `GemmaEmbedder()` with `.load_seconds: float`, `.param_count: int`, `.embed_documents(texts: list[str], batch_size: int = 32) -> np.ndarray` (n×768, normalized float32), `.embed_queries(texts: list[str], batch_size: int = 32) -> np.ndarray`, `.embed_query(text: str) -> np.ndarray` (768), `.tokenize(text: str) -> list[str]`
  - `GeminiEmbedder` async context manager with `await .embed_documents(texts) -> np.ndarray` (n×3072, normalized) and `await .embed_query(text) -> np.ndarray`
  - `async generate_json(prompt: str, temperature: float) -> dict`

These wrap external models, so they are verified by a live check (Step 4) rather than unit tests.

- [ ] **Step 1: Implement `egpoc/gemma.py`**

```python
"""EmbeddingGemma 2, text encoder only, CPU float32."""

import time

import numpy as np
import torch
from sentence_transformers import SentenceTransformer

from egpoc.config import GEMMA_MODEL_ID

_REQUIRED_PROMPTS = {"SearchQuery", "Document"}


class GemmaEmbedder:
    def __init__(self) -> None:
        started = time.perf_counter()
        self.model = SentenceTransformer(
            GEMMA_MODEL_ID,
            device="cpu",
            config_kwargs={"vision_config": None, "audio_config": None},
        )
        self.load_seconds = time.perf_counter() - started
        dtype = next(self.model.parameters()).dtype
        if dtype != torch.float32:
            raise RuntimeError(f"expected float32 weights on CPU, got {dtype}")
        missing = _REQUIRED_PROMPTS - set(self.model.prompts)
        if missing:
            raise RuntimeError(f"model prompts missing {sorted(missing)}; available {sorted(self.model.prompts)}")

    @property
    def param_count(self) -> int:
        return sum(p.numel() for p in self.model.parameters())

    def _encode(self, texts: list[str], prompt_name: str, batch_size: int) -> np.ndarray:
        vecs = self.model.encode(
            texts,
            prompt_name=prompt_name,
            batch_size=batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return vecs.astype(np.float32)

    def embed_documents(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self._encode(texts, "Document", batch_size)

    def embed_queries(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        return self._encode(texts, "SearchQuery", batch_size)

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([text], "SearchQuery", 1)[0]

    def tokenize(self, text: str) -> list[str]:
        return self.model.tokenizer.tokenize(text)
```

- [ ] **Step 2: Implement `egpoc/gemini.py`**

```python
"""Gemini baseline embeddings (same request shape as GeminiEmbeddings in backend-core) and JSON generation."""

import asyncio
import json
import logging

import aiohttp
import numpy as np
from google import genai
from google.genai import errors, types

from app.core.config import settings
from app.utils.observability import log_json
from egpoc.config import GEMINI_DIM, GEMINI_EMBED_MODEL, GEN_MODEL
from egpoc.vectors import l2_normalize

logger = logging.getLogger("egpoc.gemini")

_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
_RETRY_STATUS = {429, 500, 502, 503, 504}
_ATTEMPTS = 6


async def _post(session: aiohttp.ClientSession, url: str, body: dict) -> dict:
    for attempt in range(_ATTEMPTS):
        async with session.post(url, json=body, params={"key": settings.gemini_api_key}) as resp:
            if resp.status in _RETRY_STATUS and attempt < _ATTEMPTS - 1:
                log_json(logger, logging.WARNING, "Gemini retry", status=resp.status, attempt=attempt)
                await asyncio.sleep(min(60, 2 ** attempt))
                continue
            resp.raise_for_status()
            return await resp.json()
    raise RuntimeError("unreachable")


def _request(text: str) -> dict:
    return {
        "model": f"models/{GEMINI_EMBED_MODEL}",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": GEMINI_DIM,
    }


class GeminiEmbedder:
    async def __aenter__(self) -> "GeminiEmbedder":
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._session.close()

    async def embed_documents(self, texts: list[str]) -> np.ndarray:
        data = await _post(
            self._session,
            f"{_BASE}/{GEMINI_EMBED_MODEL}:batchEmbedContents",
            {"requests": [_request(t) for t in texts]},
        )
        return l2_normalize(np.array([e["values"] for e in data["embeddings"]], dtype=np.float32))

    async def embed_query(self, text: str) -> np.ndarray:
        data = await _post(self._session, f"{_BASE}/{GEMINI_EMBED_MODEL}:embedContent", _request(text))
        return l2_normalize(np.array(data["embedding"]["values"], dtype=np.float32))


_client: genai.Client | None = None


def _genai() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


async def generate_json(prompt: str, temperature: float) -> dict:
    """Single-shot structured generation (raw generate_content, not an ADK agent)."""
    for attempt in range(5):
        try:
            resp = await _genai().aio.models.generate_content(
                model=GEN_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json", temperature=temperature
                ),
            )
            return json.loads(resp.text)
        except (json.JSONDecodeError, errors.APIError) as exc:
            log_json(logger, logging.WARNING, "generate_json retry", attempt=attempt, error=str(exc)[:200])
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError("generate_json failed after 5 attempts")
```

- [ ] **Step 3: Write a live check script `egpoc/check_models.py`**

```python
"""Live check: both embedders load and return sane vectors. Run once after Task 5."""

import asyncio
import logging

import numpy as np

from app.utils.observability import configure_logging, log_json
from egpoc.gemini import GeminiEmbedder, generate_json
from egpoc.gemma import GemmaEmbedder

logger = logging.getLogger("egpoc.check_models")
DOCS = ["ئانا يۇرت زوردۇن سابىرنىڭ رومانى.", "بۈگۈن ھاۋا ناھايىتى ئىسسىق."]
QUERY = "ئانا يۇرت رومانىنى كىم يازغان؟"


async def main() -> None:
    configure_logging()
    gemma = GemmaEmbedder()
    d = gemma.embed_documents(DOCS)
    q = gemma.embed_query(QUERY)
    log_json(logger, logging.INFO, "gemma", params=gemma.param_count, load_s=round(gemma.load_seconds, 1),
             shape=list(d.shape), scores=[round(float(s), 3) for s in d @ q])
    async with GeminiEmbedder() as gem:
        gd = await gem.embed_documents(DOCS)
        gq = await gem.embed_query(QUERY)
    log_json(logger, logging.INFO, "gemini", shape=list(gd.shape), scores=[round(float(s), 3) for s in gd @ gq])
    out = await generate_json('Return JSON {"ok": true}', 0.0)
    log_json(logger, logging.INFO, "generate_json", out=out)
    assert d.shape == (2, 768) and gd.shape == (2, 3072)
    assert np.isfinite(d).all() and np.isfinite(gd).all()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run the live check**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.check_models`
Expected: logs for `gemma` with `params` between 250,000,000 and 300,000,000, `shape [2, 768]`, first score > second; `gemini` with `shape [2, 3072]`; `generate_json` with `{"ok": true}`.

If `config_kwargs` text-only loading raises or `params` is ~740M, the installed sentence-transformers/transformers does not support text-only loading yet: remove `config_kwargs`, re-run, and record "full multimodal weights loaded; RAM figures are an upper bound" in `scripts/poc/embeddinggemma/README.md` under a `## Notes` heading. Embeddings for text are unaffected.

Record installed versions: `./scripts/poc/embeddinggemma/run.sh pip freeze | grep -iE '^(torch|transformers|sentence-transformers)=='` and add them to README `## Notes`.

- [ ] **Step 5: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/gemma.py scripts/poc/embeddinggemma/egpoc/gemini.py \
  scripts/poc/embeddinggemma/egpoc/check_models.py scripts/poc/embeddinggemma/README.md
git commit -m "feat(poc): add CPU EmbeddingGemma and Gemini baseline embedders"
```

---

### Task 6: Prompts and question generator

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/prompts.py`, `egpoc/questions.py` (generator function only; CLI added in Task 10)
- Test: `scripts/poc/embeddinggemma/tests/test_questions.py`

**Interfaces:**
- Consumes: `generate_json`, `trigram_overlap`, `has_latin`, `is_arabic_script`.
- Produces: `QUESTION_PROMPT`, `JUDGE_PROMPT` (placeholders `{{PASSAGE}}`, `{{QUESTION}}`); `async generate_question(passage: str, llm: Callable[[str, float], Awaitable[dict]] = generate_json) -> str | None`.

- [ ] **Step 1: Invoke `/prompt-engineer`** and have it review the two prompt drafts in Step 4 for correct Uyghur Arabic-script output. Apply its edits to the prompt text only; keep the `{{PASSAGE}}` / `{{QUESTION}}` placeholders and the JSON keys `question` / `relevant` unchanged.

- [ ] **Step 2: Write failing tests**

```python
from egpoc.questions import generate_question

PASSAGE = "نۇرى مىڭبېگىگە ھەيران بولۇپ قارىدى، قارا ساقال بۇرۇتى تولىمۇ يىرىك ئىدى."


def fake_llm(*answers):
    calls = []

    async def llm(prompt, temperature):
        calls.append((prompt, temperature))
        return {"question": answers[len(calls) - 1]}

    return llm, calls


async def test_accepts_paraphrased_question():
    llm, calls = fake_llm("نۇرى كىمگە ھەيرانلىق بىلەن باقتى؟")
    assert await generate_question(PASSAGE, llm) == "نۇرى كىمگە ھەيرانلىق بىلەن باقتى؟"
    assert PASSAGE in calls[0][0]


async def test_retries_copy_then_gives_up():
    copied = "نۇرى مىڭبېگىگە ھەيران بولۇپ قارىدى"
    llm, calls = fake_llm(copied, copied)
    assert await generate_question(PASSAGE, llm) is None
    assert [t for _, t in calls] == [0.7, 1.0]


async def test_rejects_latin_output():
    llm, _ = fake_llm("Who did Nuri look at?", "نۇرى كىمگە قارىدى؟")
    assert await generate_question(PASSAGE, llm) == "نۇرى كىمگە قارىدى؟"
```

- [ ] **Step 3: Run to verify failure**

Run: `PT tests/test_questions.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement `egpoc/prompts.py`** (draft; Step 1's review may adjust wording)

```python
"""LLM prompts. Placeholders are substituted with str.replace, so JSON braces are literal."""

QUESTION_PROMPT = """You are building a retrieval test set for a Uyghur digital library.

Read the passage below (Uyghur, Arabic script). Write ONE question that a library reader might ask and that this passage answers.

Rules:
- Write the question in standard Uyghur Arabic script only. No Latin, Cyrillic, Chinese or English.
- Do not copy phrases from the passage. Use your own words and synonyms. Use a person's or place's name only if the question cannot be understood without it.
- The question must be answerable from this passage alone.
- Do not refer to "the passage", "the text" or "the book".

Return JSON: {"question": "<Uyghur question>"}

Passage:
<<<
{{PASSAGE}}
>>>"""

JUDGE_PROMPT = """You are judging search results for a Uyghur digital library.

Question (Uyghur):
<<<
{{QUESTION}}
>>>

Candidate passage (Uyghur):
<<<
{{PASSAGE}}
>>>

Is this passage relevant: does it contain information that directly helps answer the question? A passage that only shares topic words but does not help answer the question is NOT relevant.

Return JSON: {"relevant": true} or {"relevant": false}"""
```

- [ ] **Step 5: Implement the generator in `egpoc/questions.py`**

```python
"""Synthetic question generation for the retrieval test set."""

from collections.abc import Awaitable, Callable

from egpoc.config import TRIGRAM_REJECT
from egpoc.filters import has_latin, is_arabic_script, trigram_overlap
from egpoc.gemini import generate_json
from egpoc.prompts import QUESTION_PROMPT

Llm = Callable[[str, float], Awaitable[dict]]


def _acceptable(question: str, passage: str) -> bool:
    return (
        bool(question)
        and not has_latin(question)
        and is_arabic_script(question)
        and trigram_overlap(question, passage) <= TRIGRAM_REJECT
    )


async def generate_question(passage: str, llm: Llm = generate_json) -> str | None:
    """One Uyghur question per passage; one retry at a higher temperature if the first is rejected."""
    prompt = QUESTION_PROMPT.replace("{{PASSAGE}}", passage)
    for temperature in (0.7, 1.0):
        out = await llm(prompt, temperature)
        question = str(out.get("question", "")).strip()
        if _acceptable(question, passage):
            return question
    return None
```

- [ ] **Step 6: Run tests**

Run: `PT tests/test_questions.py -q`
Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/prompts.py scripts/poc/embeddinggemma/egpoc/questions.py \
  scripts/poc/embeddinggemma/tests/test_questions.py
git commit -m "feat(poc): add question-generation and judge prompts with filtered generator"
```

---

### Task 7: Book splitting and Stage 0 sanity check (GATE)

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/db.py`, `egpoc/pool.py` (splitting functions only; build CLI added in Task 8), `egpoc/sanity.py`
- Test: `scripts/poc/embeddinggemma/tests/test_sanity.py`

**Interfaces:**
- Consumes: `locate_chunks`, `GemmaEmbedder`, `GeminiEmbedder`, `generate_question`, `uyghur_words`.
- Produces:
  - `async connect() -> asyncpg.Connection` (pgvector registered)
  - `PoolChunk(book_id: str, page_number: int, chunk_index: int, text: str, span: Span)` frozen dataclass
  - `split_page(page_text: str) -> list[tuple[str, Span]]`
  - `async book_chunks(conn, book_id: str) -> list[PoolChunk]` — non-TOC pages, ordered
  - `top1_accuracy(q: np.ndarray, d: np.ndarray) -> float` (row i of q matches row i of d)
  - `byte_fallback_share(tokens: list[str]) -> float`
  - `data/sanity.json` with keys `n`, `gemma_top1`, `gemini_top1`, `tokens_per_word`, `byte_fallback_share`, `passed`

- [ ] **Step 1: Write failing tests `tests/test_sanity.py`**

```python
import numpy as np

from egpoc.pool import split_page
from egpoc.sanity import byte_fallback_share, top1_accuracy


def test_top1_accuracy():
    d = np.eye(3, dtype=np.float32)
    q = np.array([[1, 0, 0], [0, 0, 1], [0, 0, 1]], dtype=np.float32)
    assert top1_accuracy(q, d) == 2 / 3


def test_byte_fallback_share():
    assert byte_fallback_share(["▁ئانا", "<0xD8>", "<0xA6>", "▁يۇرت"]) == 0.5
    assert byte_fallback_share([]) == 0.0


def test_split_page_spans_point_at_chunk_text():
    page = "بىرىنچى ئابزاس بۇ يەردە.\n\nئىككىنچى ئابزاس بۇ يەردە."
    pieces = split_page(page)
    assert pieces
    for text, span in pieces:
        assert span.exact
```

- [ ] **Step 2: Run to verify failure**

Run: `PT tests/test_sanity.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `egpoc/db.py`**

```python
"""Local DB access for the PoC. Only the `poc` schema is ever written."""

from pathlib import Path

import asyncpg
from pgvector.asyncpg import register_vector

from app.core.config import settings

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


async def connect() -> asyncpg.Connection:
    conn = await asyncpg.connect(settings.database_url)
    await register_vector(conn)
    return conn


async def ensure_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL.read_text())
```

- [ ] **Step 4: Implement splitting in `egpoc/pool.py`**

```python
"""Pool construction: re-split books with today's chunker into poc.chunks."""

from dataclasses import dataclass

import asyncpg

from app.services.chunking_service import chunking_service
from app.utils.text import clean_uyghur_text
from egpoc.offsets import Span, locate_chunks


@dataclass(frozen=True)
class PoolChunk:
    book_id: str
    page_number: int
    chunk_index: int
    text: str
    span: Span


def split_page(page_text: str) -> list[tuple[str, Span]]:
    """Exactly what ChunkingJob does today, plus each chunk's location in the cleaned text."""
    clean = clean_uyghur_text(page_text or "")
    chunks = chunking_service.split_text(clean)
    return list(zip(chunks, locate_chunks(clean, chunks)))


async def book_chunks(conn: asyncpg.Connection, book_id: str) -> list[PoolChunk]:
    rows = await conn.fetch(
        """
        SELECT page_number, text FROM pages
        WHERE book_id = $1 AND text IS NOT NULL AND COALESCE(is_toc, false) = false
        ORDER BY page_number
        """,
        book_id,
    )
    out: list[PoolChunk] = []
    for row in rows:
        for idx, (text, span) in enumerate(split_page(row["text"])):
            out.append(PoolChunk(book_id, row["page_number"], idx, text, span))
    return out
```

- [ ] **Step 5: Implement `egpoc/sanity.py`**

```python
"""Stage 0: can EmbeddingGemma 2 match Uyghur questions to their passages at all?"""

import asyncio
import json
import logging
import random
import re
import sys

import numpy as np

from app.utils.observability import configure_logging, log_json
from egpoc.config import (DATA_DIR, LLM_CONCURRENCY, MIN_PASSAGE_CHARS, SANITY_MIN_RATIO, SANITY_MIN_TOP1,
                          SANITY_N, SEED, TEST_BOOK_IDS, BYTE_FALLBACK_WARN)
from egpoc.db import connect
from egpoc.filters import uyghur_words
from egpoc.gemini import GeminiEmbedder
from egpoc.gemma import GemmaEmbedder
from egpoc.pool import book_chunks
from egpoc.questions import generate_question

logger = logging.getLogger("egpoc.sanity")
_BYTE_TOKEN = re.compile(r"^<0x[0-9A-Fa-f]{2}>$")
QUESTIONS_PATH = DATA_DIR / "sanity_questions.jsonl"
RESULT_PATH = DATA_DIR / "sanity.json"


def top1_accuracy(q: np.ndarray, d: np.ndarray) -> float:
    return float(np.mean(np.argmax(q @ d.T, axis=1) == np.arange(len(q))))


def byte_fallback_share(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return sum(1 for t in tokens if _BYTE_TOKEN.match(t)) / len(tokens)


async def _pairs() -> list[dict]:
    if QUESTIONS_PATH.exists():
        return [json.loads(line) for line in QUESTIONS_PATH.read_text().splitlines()]
    conn = await connect()
    try:
        chunks = [c for b in TEST_BOOK_IDS for c in await book_chunks(conn, b)
                  if c.span.exact and len(c.text) >= MIN_PASSAGE_CHARS]
    finally:
        await conn.close()
    sample = random.Random(SEED).sample(chunks, SANITY_N + 10)
    sem = asyncio.Semaphore(LLM_CONCURRENCY)

    async def one(c):
        async with sem:
            return c, await generate_question(c.text)

    pairs = [{"passage": c.text, "question": q} for c, q in await asyncio.gather(*map(one, sample)) if q]
    pairs = pairs[:SANITY_N]
    DATA_DIR.mkdir(exist_ok=True)
    QUESTIONS_PATH.write_text("\n".join(json.dumps(p, ensure_ascii=False) for p in pairs))
    return pairs


async def main() -> int:
    configure_logging()
    pairs = await _pairs()
    passages = [p["passage"] for p in pairs]
    questions = [p["question"] for p in pairs]

    gemma = GemmaEmbedder()
    gemma_top1 = top1_accuracy(gemma.embed_queries(questions), gemma.embed_documents(passages))
    async with GeminiEmbedder() as gem:
        gd = await gem.embed_documents(passages)
        gq = np.stack([await gem.embed_query(q) for q in questions])
    gemini_top1 = top1_accuracy(gq, gd)

    tokens = [t for p in passages for t in gemma.tokenize(p)]
    words = sum(len(uyghur_words(p)) for p in passages)
    result = {
        "n": len(pairs),
        "gemma_top1": gemma_top1,
        "gemini_top1": gemini_top1,
        "tokens_per_word": len(tokens) / words,
        "byte_fallback_share": byte_fallback_share(tokens),
        "passed": gemma_top1 >= SANITY_MIN_TOP1 and gemma_top1 >= SANITY_MIN_RATIO * gemini_top1,
    }
    result["byte_fallback_warning"] = result["byte_fallback_share"] > BYTE_FALLBACK_WARN
    RESULT_PATH.write_text(json.dumps(result, indent=2))
    log_json(logger, logging.INFO, "Stage 0 result", **result)
    return 0 if result["passed"] else 3


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
```

- [ ] **Step 6: Run tests**

Run: `PT tests/test_sanity.py -q`
Expected: `3 passed`

- [ ] **Step 7: Run Stage 0**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.sanity; echo "exit=$?"`
Expected: a `Stage 0 result` log line and `exit=0` (pass) or `exit=3` (fail).

- [ ] **Step 8: GATE — report to the user and stop**

Show the user `data/sanity.json` and 5 sample question/passage pairs from `data/sanity_questions.jsonl`.
- `exit=3` → **stop the PoC.** Go to Task 14 Step 6 (write a NO-GO report from Stage 0 only) after the user agrees.
- `exit=0` → continue only after the user says to.

- [ ] **Step 9: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/db.py scripts/poc/embeddinggemma/egpoc/pool.py \
  scripts/poc/embeddinggemma/egpoc/sanity.py scripts/poc/embeddinggemma/tests/test_sanity.py
git commit -m "feat(poc): add book splitting and Stage 0 Uyghur sanity check"
```

---

### Task 8: Build the pool (`poc` schema)

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/schema.sql`
- Modify: `scripts/poc/embeddinggemma/egpoc/pool.py` (append distractor selection + CLI)
- Test: `scripts/poc/embeddinggemma/tests/test_pool.py`

**Interfaces:**
- Consumes: `book_chunks`, `connect`, `ensure_schema`.
- Produces: tables `poc.pool_books(book_id, role, category)` and `poc.chunks(...)` (columns below); `Candidate(book_id, category, est_chunks)`; `select_distractors(cands: list[Candidate], budget: int, seed: int) -> list[Candidate]`; `data/pool_stats.json` with `test_chunks`, `distractor_chunks`, `distractor_books`, `fallback`, `fallback_rate`, `whitespace_or_exact`.

- [ ] **Step 1: Write `egpoc/schema.sql`**

```sql
CREATE SCHEMA IF NOT EXISTS poc;

CREATE TABLE IF NOT EXISTS poc.pool_books (
    book_id varchar(64) PRIMARY KEY,
    role text NOT NULL CHECK (role IN ('test', 'distractor')),
    category text NOT NULL
);

CREATE TABLE IF NOT EXISTS poc.chunks (
    id serial PRIMARY KEY,
    strategy text NOT NULL,
    book_id varchar(64) NOT NULL REFERENCES poc.pool_books (book_id),
    page_number int NOT NULL,
    chunk_index int NOT NULL,
    text text NOT NULL,
    char_start int NOT NULL,
    char_end int NOT NULL,
    offset_exact boolean NOT NULL,
    emb_gemma vector(768),
    emb_gemini vector(3072),
    UNIQUE (strategy, book_id, page_number, chunk_index)
);
```

- [ ] **Step 2: Write failing tests `tests/test_pool.py`**

```python
from egpoc.pool import Candidate, select_distractors


def cands():
    return [Candidate(f"{cat}{i}", cat, 100) for cat in ("a", "b", "c") for i in range(5)]


def test_round_robin_covers_categories_before_repeating():
    chosen = select_distractors(cands(), budget=300, seed=7)
    assert sorted(c.category for c in chosen) == ["a", "b", "c"]


def test_stops_at_budget_and_is_deterministic():
    first = select_distractors(cands(), budget=650, seed=7)
    assert sum(c.est_chunks for c in first) == 700
    assert first == select_distractors(cands(), budget=650, seed=7)


def test_exhausts_candidates_without_looping():
    assert len(select_distractors(cands(), budget=10_000, seed=7)) == 15
```

- [ ] **Step 3: Run to verify failure**

Run: `PT tests/test_pool.py -q`
Expected: FAIL — `ImportError: cannot import name 'Candidate'`

- [ ] **Step 4: Append to `egpoc/pool.py`** (merge the new imports into the existing import block at the top of the file)

```python
import asyncio
import json
import logging
import random
import sys
from collections import defaultdict

from app.utils.observability import configure_logging, log_json
from egpoc.config import DATA_DIR, DISTRACTOR_CHUNK_BUDGET, MAX_FALLBACK_RATE, SEED, STRATEGY, TEST_BOOK_IDS, TEST_TITLES
from egpoc.db import connect, ensure_schema

logger = logging.getLogger("egpoc.pool")
STATS_PATH = DATA_DIR / "pool_stats.json"


@dataclass(frozen=True)
class Candidate:
    book_id: str
    category: str
    est_chunks: int


def select_distractors(cands: list[Candidate], budget: int, seed: int) -> list[Candidate]:
    """Round-robin across categories (random order, fixed seed) until the chunk budget is reached."""
    rng = random.Random(seed)
    by_cat: dict[str, list[Candidate]] = defaultdict(list)
    for c in sorted(cands, key=lambda c: c.book_id):
        by_cat[c.category].append(c)
    for books in by_cat.values():
        rng.shuffle(books)
    cats = sorted(by_cat)
    rng.shuffle(cats)
    chosen: list[Candidate] = []
    total = 0
    while total < budget and any(by_cat[c] for c in cats):
        for cat in cats:
            if by_cat[cat] and total < budget:
                pick = by_cat[cat].pop()
                chosen.append(pick)
                total += pick.est_chunks
    return chosen


async def _candidates(conn: asyncpg.Connection) -> list[Candidate]:
    rows = await conn.fetch(
        """
        SELECT b.id, COALESCE(b.categories[1], 'uncategorized') AS category, count(c.id) AS est_chunks
        FROM books b JOIN chunks c ON c.book_id = b.id
        WHERE b.status = 'ready' AND b.title <> ALL($1::text[]) AND b.id <> ALL($2::text[])
        GROUP BY b.id, category
        """,
        list(TEST_TITLES), list(TEST_BOOK_IDS),
    )
    return [Candidate(r["id"], r["category"], r["est_chunks"]) for r in rows]


async def _insert_book(conn: asyncpg.Connection, book_id: str, role: str, category: str) -> tuple[int, int]:
    chunks = await book_chunks(conn, book_id)
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO poc.pool_books (book_id, role, category) VALUES ($1, $2, $3)", book_id, role, category
        )
        await conn.executemany(
            """
            INSERT INTO poc.chunks (strategy, book_id, page_number, chunk_index, text, char_start, char_end, offset_exact)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            [(STRATEGY, c.book_id, c.page_number, c.chunk_index, c.text, c.span.start, c.span.end, c.span.exact)
             for c in chunks],
        )
    return len(chunks), sum(1 for c in chunks if not c.span.exact)


async def build(rebuild: bool) -> int:
    configure_logging()
    conn = await connect()
    try:
        await ensure_schema(conn)
        existing = await conn.fetchval("SELECT count(*) FROM poc.chunks WHERE strategy = $1", STRATEGY)
        if existing and not rebuild:
            log_json(logger, logging.ERROR, "Pool already built; pass --rebuild to recreate", chunks=existing)
            return 1
        if rebuild:
            await conn.execute("TRUNCATE poc.chunks, poc.pool_books RESTART IDENTITY")

        test_cats = dict(await conn.fetch(
            "SELECT id, COALESCE(categories[1], 'uncategorized') FROM books WHERE id = ANY($1::text[])",
            list(TEST_BOOK_IDS),
        ))
        stats = {"test_chunks": 0, "distractor_chunks": 0, "fallback": 0}
        for book_id in TEST_BOOK_IDS:
            n, fb = await _insert_book(conn, book_id, "test", test_cats[book_id])
            stats["test_chunks"] += n
            stats["fallback"] += fb
            log_json(logger, logging.INFO, "Test book pooled", book_id=book_id, chunks=n, fallback=fb)

        distractors = select_distractors(await _candidates(conn), DISTRACTOR_CHUNK_BUDGET, SEED)
        for cand in distractors:
            n, fb = await _insert_book(conn, cand.book_id, "distractor", cand.category)
            stats["distractor_chunks"] += n
            stats["fallback"] += fb
            log_json(logger, logging.INFO, "Distractor pooled", book_id=cand.book_id, chunks=n, fallback=fb)
    finally:
        await conn.close()

    total = stats["test_chunks"] + stats["distractor_chunks"]
    stats["distractor_books"] = [c.book_id for c in distractors]
    stats["fallback_rate"] = stats["fallback"] / total
    stats["whitespace_or_exact"] = total - stats["fallback"]
    DATA_DIR.mkdir(exist_ok=True)
    STATS_PATH.write_text(json.dumps(stats, indent=2))
    log_json(logger, logging.INFO, "Pool built", total=total, fallback_rate=round(stats["fallback_rate"], 4))
    if stats["fallback_rate"] > MAX_FALLBACK_RATE:
        log_json(logger, logging.ERROR, "Fallback rate above limit — inspect before continuing",
                 limit=MAX_FALLBACK_RATE)
        return 2
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] != "build":
        sys.exit("usage: python -m egpoc.pool build [--rebuild]")
    sys.exit(asyncio.run(build(rebuild="--rebuild" in sys.argv)))
```

- [ ] **Step 5: Run tests**

Run: `PT tests/test_pool.py -q`
Expected: `3 passed`

- [ ] **Step 6: Build the pool**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.pool build; echo "exit=$?"`
Expected: `exit=0`, `Pool built` with `total` roughly 45,000–55,000 and `fallback_rate` ≤ 0.05.
If `exit=2`: stop and show the user `data/pool_stats.json` plus 5 fallback chunks (`SELECT book_id, page_number, left(text, 200) FROM poc.chunks WHERE NOT offset_exact LIMIT 5`).

- [ ] **Step 7: Verify prod tables were untouched**

Run: `psql "$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -Atc "SELECT count(*) FROM public.chunks"`
Expected: `526168` (unchanged).

- [ ] **Step 8: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/schema.sql scripts/poc/embeddinggemma/egpoc/pool.py \
  scripts/poc/embeddinggemma/tests/test_pool.py
git commit -m "feat(poc): build poc.chunks pool from test and distractor books"
```

---

### Task 9: Embed the pool (overnight run)

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/embed_pool.py`

**Interfaces:**
- Consumes: `connect`, `GemmaEmbedder.embed_documents`, `GeminiEmbedder.embed_documents`.
- Produces: `poc.chunks.emb_gemma` and `emb_gemini` filled for every row.

- [ ] **Step 1: Implement `egpoc/embed_pool.py`**

```python
"""Fill poc.chunks embeddings. Resumable: only rows with a NULL column are processed."""

import asyncio
import logging
import sys
import time

from app.utils.observability import configure_logging, log_json
from egpoc.config import GEMINI_EMBED_BATCH
from egpoc.db import connect
from egpoc.gemini import GeminiEmbedder
from egpoc.gemma import GemmaEmbedder

logger = logging.getLogger("egpoc.embed_pool")
COLUMNS = {"gemma": "emb_gemma", "gemini": "emb_gemini"}  # fixed whitelist — safe to interpolate
FETCH = {"gemma": 256, "gemini": GEMINI_EMBED_BATCH}


async def run(model: str) -> None:
    configure_logging()
    col = COLUMNS[model]
    conn = await connect()
    gemma = GemmaEmbedder() if model == "gemma" else None
    gem = await GeminiEmbedder().__aenter__() if model == "gemini" else None
    started, done = time.perf_counter(), 0
    try:
        while True:
            rows = await conn.fetch(
                f"SELECT id, text FROM poc.chunks WHERE {col} IS NULL ORDER BY id LIMIT $1", FETCH[model]
            )
            if not rows:
                break
            texts = [r["text"] for r in rows]
            vecs = gemma.embed_documents(texts) if gemma else await gem.embed_documents(texts)
            await conn.executemany(
                f"UPDATE poc.chunks SET {col} = $2 WHERE id = $1",
                [(r["id"], v) for r, v in zip(rows, vecs)],
            )
            done += len(rows)
            if done % 2560 < len(rows):
                rate = done / (time.perf_counter() - started)
                log_json(logger, logging.INFO, "Embedding progress", model=model, done=done, per_sec=round(rate, 1))
    finally:
        if gem:
            await gem.__aexit__(None, None, None)
        await conn.close()
    log_json(logger, logging.INFO, "Embedding complete", model=model, done=done)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COLUMNS:
        sys.exit("usage: python -m egpoc.embed_pool gemma|gemini")
    asyncio.run(run(sys.argv[1]))
```

- [ ] **Step 2: Gemini run** (≈ 1,000 calls, ≈ $1.50)

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.embed_pool gemini`
Expected: `Embedding complete` with `done` equal to the pool size.

- [ ] **Step 3: Gemma run** (CPU, expected several hours — run in background or overnight; safe to interrupt and re-run)

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.embed_pool gemma`
Expected: `Embedding complete`.

- [ ] **Step 4: Verify completeness**

Run: `psql "$(grep '^DATABASE_URL=' .env | cut -d= -f2-)" -Atc "SELECT count(*) FILTER (WHERE emb_gemma IS NULL), count(*) FILTER (WHERE emb_gemini IS NULL), count(*) FROM poc.chunks"`
Expected: `0|0|<pool size>`

- [ ] **Step 5: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/embed_pool.py
git commit -m "feat(poc): add resumable pool embedding for Gemma and Gemini"
```

---

### Task 10: Synthetic question set + user review (GATE)

**Files:**
- Modify: `scripts/poc/embeddinggemma/egpoc/questions.py` (append CLI)

**Interfaces:**
- Consumes: `generate_question`, `connect`.
- Produces: `data/synthetic_questions.jsonl`, one JSON object per line: `{"id": "s<chunk_id>", "question", "chunk_id", "book_id", "page_number", "char_start", "char_end"}`; `data/review.csv`.

- [ ] **Step 1: Append the CLI to `egpoc/questions.py`** (merge imports into the top block)

```python
import asyncio
import csv
import json
import logging
import random
import sys

from app.utils.observability import configure_logging, log_json
from egpoc.config import (DATA_DIR, LLM_CONCURRENCY, MAX_REVIEW_FLAG_RATE, MIN_PASSAGE_CHARS, REVIEW_N, SEED,
                          STRATEGY, SYNTHETIC_OVERSAMPLE, SYNTHETIC_TARGET)
from egpoc.db import connect

logger = logging.getLogger("egpoc.questions")
SYNTHETIC_PATH = DATA_DIR / "synthetic_questions.jsonl"
REVIEW_PATH = DATA_DIR / "review.csv"


def load_jsonl(path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path, rows: list[dict]) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows))


async def build() -> int:
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT c.id, c.book_id, c.page_number, c.char_start, c.char_end, c.text
            FROM poc.chunks c JOIN poc.pool_books b ON b.book_id = c.book_id
            WHERE c.strategy = $1 AND b.role = 'test' AND c.offset_exact AND length(c.text) >= $2
            ORDER BY c.id
            """,
            STRATEGY, MIN_PASSAGE_CHARS,
        )
    finally:
        await conn.close()
    sample = random.Random(SEED).sample(list(rows), SYNTHETIC_OVERSAMPLE)
    sem = asyncio.Semaphore(LLM_CONCURRENCY)

    async def one(r):
        async with sem:
            return r, await generate_question(r["text"])

    out = []
    for r, q in await asyncio.gather(*map(one, sample)):
        if q:
            out.append({"id": f"s{r['id']}", "question": q, "chunk_id": r["id"], "book_id": r["book_id"],
                        "page_number": r["page_number"], "char_start": r["char_start"], "char_end": r["char_end"]})
    out = out[:SYNTHETIC_TARGET]
    write_jsonl(SYNTHETIC_PATH, out)
    log_json(logger, logging.INFO, "Synthetic questions written", kept=len(out), sampled=len(sample))
    return 0 if len(out) >= int(SYNTHETIC_TARGET * 0.9) else 1


async def export_review() -> int:
    questions = load_jsonl(SYNTHETIC_PATH)
    picks = random.Random(SEED).sample(questions, REVIEW_N)
    conn = await connect()
    try:
        texts = dict(await conn.fetch("SELECT id, text FROM poc.chunks WHERE id = ANY($1::int[])",
                                      [p["chunk_id"] for p in picks]))
    finally:
        await conn.close()
    with REVIEW_PATH.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "keep", "question", "passage"])
        for p in picks:
            w.writerow([p["id"], "", p["question"], texts[p["chunk_id"]]])
    log_json(logger, logging.INFO, "Review sheet written", path=str(REVIEW_PATH), rows=len(picks))
    return 0


async def apply_review() -> int:
    with REVIEW_PATH.open(newline="") as f:
        reviewed = list(csv.DictReader(f))
    dropped = {r["id"] for r in reviewed if r["keep"].strip().lower() == "n"}
    questions = [q for q in load_jsonl(SYNTHETIC_PATH) if q["id"] not in dropped]
    write_jsonl(SYNTHETIC_PATH, questions)
    rate = len(dropped) / len(reviewed)
    log_json(logger, logging.INFO, "Review applied", dropped=len(dropped), flag_rate=round(rate, 3),
             remaining=len(questions))
    if rate > MAX_REVIEW_FLAG_RATE:
        log_json(logger, logging.ERROR, "Too many flagged — revise QUESTION_PROMPT and rebuild")
        return 2
    return 0


COMMANDS = {"build": build, "export-review": export_review, "apply-review": apply_review}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        sys.exit(f"usage: python -m egpoc.questions {'|'.join(COMMANDS)}")
    configure_logging()
    sys.exit(asyncio.run(COMMANDS[sys.argv[1]]()))
```

- [ ] **Step 2: Re-run unit tests** (the generator must still pass)

Run: `PT tests/test_questions.py -q`
Expected: `3 passed`

- [ ] **Step 3: Generate and export**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.questions build && ./scripts/poc/embeddinggemma/run.sh python -m egpoc.questions export-review`
Expected: `Synthetic questions written` with `kept` ≥ 270; `Review sheet written`.

- [ ] **Step 4: GATE — user review**

Ask the user to open `scripts/poc/embeddinggemma/data/review.csv`, put `n` in `keep` for any question that is unnatural, wrong, or unanswerable from its passage, and save. Wait for the user to confirm.

- [ ] **Step 5: Apply review**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.questions apply-review; echo "exit=$?"`
Expected: `exit=0`. If `exit=2`, revise `QUESTION_PROMPT` with the user (via `/prompt-engineer`), delete `data/synthetic_questions.jsonl`, and repeat Steps 3–5.

- [ ] **Step 6: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/questions.py scripts/poc/embeddinggemma/egpoc/prompts.py
git commit -m "feat(poc): build and review synthetic Uyghur question set"
```

---

### Task 11: Pool index, query cache, real questions, blind judging

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/pool_index.py`, `egpoc/queries.py`, `egpoc/real_questions.py`, `egpoc/judge.py`
- Test: `scripts/poc/embeddinggemma/tests/test_pool_index.py`

**Interfaces:**
- Consumes: `top_k`, `l2_normalize`, `truncate_normalize`, `GemmaEmbedder.embed_queries`, `GeminiEmbedder.embed_query`, `generate_json`, `JUDGE_PROMPT`, `is_arabic_script`, `load_jsonl`, `write_jsonl`.
- Produces:
  - `PoolIndex(ids, book_ids, page_numbers, starts, ends, matrices: dict[str, np.ndarray])` with `.rank(variant: str, qvec: np.ndarray, k: int, book_id: str | None = None) -> np.ndarray` and `.relevant_mask(book_id, page_number, start, end) -> np.ndarray[bool]`
  - `async load_pool_index(conn) -> PoolIndex`
  - `async query_vectors(questions: list[dict], name: str) -> dict[str, np.ndarray]` — variant → (n_questions × dim) matrix, cached in `data/qemb_<name>.npz`
  - `data/real_questions.jsonl` (`{"id": "r<rag_evaluations.id>", "question"}`), `data/judgments.jsonl` (`{"qid", "chunk_id", "relevant"}`)

- [ ] **Step 1: Write failing tests `tests/test_pool_index.py`**

```python
import numpy as np

from egpoc.pool_index import PoolIndex


def index():
    m = np.array([[1.0, 0.0], [0.8, 0.6], [0.0, 1.0]], dtype=np.float32)
    return PoolIndex(
        ids=np.array([10, 11, 12]),
        book_ids=np.array(["A", "A", "B"], dtype=object),
        page_numbers=np.array([1, 1, 2]),
        starts=np.array([0, 100, 0]),
        ends=np.array([120, 220, 50]),
        matrices={"gemini": m},
    )


def test_rank_pool_and_book_scope():
    idx = index()
    q = np.array([0.0, 1.0], dtype=np.float32)
    assert idx.rank("gemini", q, 3).tolist() == [2, 1, 0]
    assert idx.rank("gemini", q, 3, book_id="A").tolist() == [1, 0]


def test_relevant_mask_uses_char_overlap():
    idx = index()
    assert idx.relevant_mask("A", 1, 110, 130).tolist() == [True, True, False]
    assert idx.relevant_mask("A", 1, 200, 210).tolist() == [False, True, False]
    assert idx.relevant_mask("B", 1, 0, 10).tolist() == [False, False, False]
```

- [ ] **Step 2: Run to verify failure**

Run: `PT tests/test_pool_index.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `egpoc/pool_index.py`**

```python
"""In-memory pool for exact retrieval and overlap-based relevance."""

from dataclasses import dataclass

import asyncpg
import numpy as np

from egpoc.config import GEMMA_DIMS, STRATEGY
from egpoc.vectors import l2_normalize, top_k, truncate_normalize


@dataclass
class PoolIndex:
    ids: np.ndarray
    book_ids: np.ndarray
    page_numbers: np.ndarray
    starts: np.ndarray
    ends: np.ndarray
    matrices: dict[str, np.ndarray]

    def rank(self, variant: str, qvec: np.ndarray, k: int, book_id: str | None = None) -> np.ndarray:
        mask = (self.book_ids == book_id) if book_id is not None else None
        return top_k(self.matrices[variant], qvec, k, mask)

    def relevant_mask(self, book_id: str, page_number: int, start: int, end: int) -> np.ndarray:
        return (
            (self.book_ids == book_id)
            & (self.page_numbers == page_number)
            & (self.starts < end)
            & (self.ends > start)
        )


async def load_pool_index(conn: asyncpg.Connection) -> PoolIndex:
    rows = await conn.fetch(
        """
        SELECT id, book_id, page_number, char_start, char_end, emb_gemma, emb_gemini
        FROM poc.chunks WHERE strategy = $1 ORDER BY id
        """,
        STRATEGY,
    )
    if any(r["emb_gemma"] is None or r["emb_gemini"] is None for r in rows):
        raise RuntimeError("poc.chunks has NULL embeddings — finish Task 9 first")
    gemma = np.stack([r["emb_gemma"] for r in rows]).astype(np.float32)
    gemini = np.stack([r["emb_gemini"] for r in rows]).astype(np.float32)
    matrices = {"gemini": l2_normalize(gemini)}
    del gemini
    for dim in GEMMA_DIMS:
        matrices[f"gemma{dim}"] = truncate_normalize(gemma, dim)
    return PoolIndex(
        ids=np.array([r["id"] for r in rows]),
        book_ids=np.array([r["book_id"] for r in rows], dtype=object),
        page_numbers=np.array([r["page_number"] for r in rows]),
        starts=np.array([r["char_start"] for r in rows]),
        ends=np.array([r["char_end"] for r in rows]),
        matrices=matrices,
    )
```

- [ ] **Step 4: Implement `egpoc/queries.py`**

```python
"""Query embeddings per variant, cached so judging, evaluation and benchmarking reuse them."""

import numpy as np

from egpoc.config import DATA_DIR, GEMMA_DIMS
from egpoc.gemini import GeminiEmbedder
from egpoc.gemma import GemmaEmbedder
from egpoc.vectors import truncate_normalize


async def query_vectors(questions: list[dict], name: str) -> dict[str, np.ndarray]:
    path = DATA_DIR / f"qemb_{name}.npz"
    ids = np.array([q["id"] for q in questions])
    if path.exists():
        cached = np.load(path)
        if np.array_equal(cached["ids"], ids):
            gemma, gemini = cached["gemma"], cached["gemini"]
            return _variants(gemma, gemini)
    texts = [q["question"] for q in questions]
    gemma = GemmaEmbedder().embed_queries(texts)
    async with GeminiEmbedder() as gem:
        gemini = np.stack([await gem.embed_query(t) for t in texts])
    np.savez(path, ids=ids, gemma=gemma, gemini=gemini)
    return _variants(gemma, gemini)


def _variants(gemma: np.ndarray, gemini: np.ndarray) -> dict[str, np.ndarray]:
    out = {"gemini": gemini}
    for dim in GEMMA_DIMS:
        out[f"gemma{dim}"] = truncate_normalize(gemma, dim)
    return out
```

- [ ] **Step 5: Implement `egpoc/real_questions.py`**

```python
"""Sample logged library-wide user questions from rag_evaluations."""

import asyncio
import logging
import random

from app.utils.observability import configure_logging, log_json
from egpoc.config import DATA_DIR, REAL_TARGET, SEED
from egpoc.db import connect
from egpoc.filters import is_arabic_script
from egpoc.questions import write_jsonl

logger = logging.getLogger("egpoc.real_questions")
REAL_PATH = DATA_DIR / "real_questions.jsonl"


async def main() -> None:
    configure_logging()
    conn = await connect()
    try:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (btrim(question)) id, btrim(question) AS question
            FROM rag_evaluations
            WHERE is_global AND length(btrim(question)) >= 10
            ORDER BY btrim(question), id
            """
        )
    finally:
        await conn.close()
    eligible = [r for r in rows if is_arabic_script(r["question"])]
    picks = random.Random(SEED).sample(eligible, min(REAL_TARGET, len(eligible)))
    write_jsonl(REAL_PATH, [{"id": f"r{r['id']}", "question": r["question"]} for r in picks])
    log_json(logger, logging.INFO, "Real questions written", eligible=len(eligible), kept=len(picks))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 6: Implement `egpoc/judge.py`**

```python
"""Pooled blind judging: every variant's top-25 per real question, judged once, model origin hidden."""

import asyncio
import json
import logging
import random

from app.utils.observability import configure_logging, log_json
from egpoc.config import DATA_DIR, LLM_CONCURRENCY, SEED, TOP_K, VARIANTS
from egpoc.db import connect
from egpoc.gemini import generate_json
from egpoc.pool_index import load_pool_index
from egpoc.prompts import JUDGE_PROMPT
from egpoc.queries import query_vectors
from egpoc.questions import load_jsonl
from egpoc.real_questions import REAL_PATH

logger = logging.getLogger("egpoc.judge")
JUDGMENTS_PATH = DATA_DIR / "judgments.jsonl"


def load_judgments() -> dict[tuple[str, int], bool]:
    if not JUDGMENTS_PATH.exists():
        return {}
    return {(j["qid"], j["chunk_id"]): j["relevant"] for j in load_jsonl(JUDGMENTS_PATH)}


async def main() -> None:
    configure_logging()
    questions = load_jsonl(REAL_PATH)
    qvecs = await query_vectors(questions, "real")
    conn = await connect()
    try:
        index = await load_pool_index(conn)
        todo: list[tuple[str, str, int]] = []
        done = load_judgments()
        for i, q in enumerate(questions):
            pooled = set()
            for variant in VARIANTS:
                pooled.update(int(index.ids[r]) for r in index.rank(variant, qvecs[variant][i], TOP_K))
            todo.extend((q["id"], q["question"], cid) for cid in pooled if (q["id"], cid) not in done)
        random.Random(SEED).shuffle(todo)
        texts = dict(await conn.fetch("SELECT id, text FROM poc.chunks WHERE id = ANY($1::int[])",
                                      list({cid for _, _, cid in todo})))
    finally:
        await conn.close()

    log_json(logger, logging.INFO, "Judging", pairs=len(todo))
    sem = asyncio.Semaphore(LLM_CONCURRENCY)
    with JUDGMENTS_PATH.open("a") as out:
        async def one(qid: str, question: str, cid: int) -> None:
            prompt = JUDGE_PROMPT.replace("{{QUESTION}}", question).replace("{{PASSAGE}}", texts[cid])
            async with sem:
                verdict = await generate_json(prompt, 0.0)
            out.write(json.dumps({"qid": qid, "chunk_id": cid, "relevant": bool(verdict.get("relevant"))}) + "\n")
            out.flush()

        await asyncio.gather(*(one(*t) for t in todo))
    log_json(logger, logging.INFO, "Judging complete", judged=len(todo))


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 7: Run tests**

Run: `PT tests/test_pool_index.py -q`
Expected: `2 passed`

- [ ] **Step 8: Sample real questions and judge** (≈ 200 × up to 100 pairs; flash-lite, a few dollars at most)

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.real_questions && ./scripts/poc/embeddinggemma/run.sh python -m egpoc.judge`
Expected: `Real questions written` with `kept` = 200; `Judging complete`. Re-running `judge` resumes and skips judged pairs.

- [ ] **Step 9: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/pool_index.py scripts/poc/embeddinggemma/egpoc/queries.py \
  scripts/poc/embeddinggemma/egpoc/real_questions.py scripts/poc/embeddinggemma/egpoc/judge.py \
  scripts/poc/embeddinggemma/tests/test_pool_index.py
git commit -m "feat(poc): add pool index, query cache, real questions and blind judging"
```

---

### Task 12: Evaluate

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/evaluate.py`

**Interfaces:**
- Consumes: `load_pool_index`, `query_vectors`, `load_judgments`, `aggregate`, `first_hit_rank`, `load_jsonl`.
- Produces: `data/results.json`:
  ```
  {"metrics": {"synthetic": {"pool": {variant: {...}}, "book": {variant: {...}}},
               "real": {"pool": {variant: {...}}}},
   "per_query": {"synthetic_pool": [{"qid", "question", "chunk_id", "ranks": {variant: int|null},
                                      "top5": {variant: [chunk_id, ...]}}]}}
  ```
  Each metrics dict has `success@5`, `success@10`, `success@25`, `mrr@10`, `ndcg@10`, `n`.

- [ ] **Step 1: Implement `egpoc/evaluate.py`**

```python
"""Score every variant on both question sets and scopes."""

import asyncio
import json
import logging

from app.utils.observability import configure_logging, log_json
from egpoc.config import DATA_DIR, TOP_K, VARIANTS
from egpoc.db import connect
from egpoc.judge import load_judgments
from egpoc.metrics import aggregate, first_hit_rank
from egpoc.pool_index import PoolIndex, load_pool_index
from egpoc.queries import query_vectors
from egpoc.questions import SYNTHETIC_PATH, load_jsonl
from egpoc.real_questions import REAL_PATH

logger = logging.getLogger("egpoc.evaluate")
RESULTS_PATH = DATA_DIR / "results.json"


def score_synthetic(index: PoolIndex, questions: list[dict], qvecs: dict, scope: str) -> tuple[dict, list]:
    metrics, per_query = {}, {q["id"]: {"qid": q["id"], "question": q["question"], "chunk_id": q["chunk_id"],
                                       "ranks": {}, "top5": {}} for q in questions}
    for variant in VARIANTS:
        rows = []
        for i, q in enumerate(questions):
            relevant = index.relevant_mask(q["book_id"], q["page_number"], q["char_start"], q["char_end"])
            ranked = index.rank(variant, qvecs[variant][i], TOP_K, book_id=q["book_id"] if scope == "book" else None)
            rels = relevant[ranked].tolist()
            rows.append((rels, int(relevant.sum())))
            per_query[q["id"]]["ranks"][variant] = first_hit_rank(rels)
            per_query[q["id"]]["top5"][variant] = [int(index.ids[r]) for r in ranked[:5]]
        metrics[variant] = aggregate(rows)
    return metrics, list(per_query.values())


def score_real(index: PoolIndex, questions: list[dict], qvecs: dict, judgments: dict) -> dict:
    n_relevant = {q["id"]: sum(1 for (qid, _), rel in judgments.items() if qid == q["id"] and rel)
                  for q in questions}
    kept = [(i, q) for i, q in enumerate(questions) if n_relevant[q["id"]] > 0]
    metrics = {}
    for variant in VARIANTS:
        rows = []
        for i, q in kept:
            ranked = index.rank(variant, qvecs[variant][i], TOP_K)
            rels = []
            for r in ranked:
                key = (q["id"], int(index.ids[r]))
                if key not in judgments:
                    raise RuntimeError(f"unjudged pair {key} — re-run egpoc.judge")
                rels.append(judgments[key])
            rows.append((rels, n_relevant[q["id"]]))
        metrics[variant] = aggregate(rows)
    log_json(logger, logging.INFO, "Real questions scored", kept=len(kept), dropped=len(questions) - len(kept))
    return metrics


async def main() -> None:
    configure_logging()
    synthetic = load_jsonl(SYNTHETIC_PATH)
    real = load_jsonl(REAL_PATH)
    s_vecs = await query_vectors(synthetic, "synthetic")
    r_vecs = await query_vectors(real, "real")
    conn = await connect()
    try:
        index = await load_pool_index(conn)
    finally:
        await conn.close()

    pool_metrics, per_query = score_synthetic(index, synthetic, s_vecs, "pool")
    book_metrics, _ = score_synthetic(index, synthetic, s_vecs, "book")
    results = {
        "metrics": {
            "synthetic": {"pool": pool_metrics, "book": book_metrics},
            "real": {"pool": score_real(index, real, r_vecs, load_judgments())},
        },
        "per_query": {"synthetic_pool": per_query},
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    for variant, m in pool_metrics.items():
        log_json(logger, logging.INFO, "synthetic/pool", variant=variant,
                 **{k: round(v, 3) for k, v in m.items()})


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the full test suite** (nothing should regress)

Run: `PT -q`
Expected: all tests pass.

- [ ] **Step 3: Run evaluation**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.evaluate`
Expected: four `synthetic/pool` log lines (one per variant); `Real questions scored` with `kept` ≥ 150; `data/results.json` written.

- [ ] **Step 4: Sanity-check results**

Gemini `synthetic/pool` `success@25` should be well above 0 (expect > 0.5). If every variant is near 0, the relevance mask or offsets are wrong — stop and debug with superpowers:systematic-debugging before continuing.

- [ ] **Step 5: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/evaluate.py
git commit -m "feat(poc): evaluate all variants on synthetic and real question sets"
```

---

### Task 13: CPU benchmark

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/bench.py`

**Interfaces:**
- Consumes: `GemmaEmbedder`, `connect`, `load_jsonl`, `SYNTHETIC_PATH`.
- Produces: `data/bench.json` with `cpus`, `memory`, `torch_threads`, `param_count`, `load_seconds`, `docs_per_sec`, `chunks_per_page`, `book_minutes`, `query_p50_ms`, `query_p95_ms`, `peak_rss_mb`, `arch`.

- [ ] **Step 1: Implement `egpoc/bench.py`**

```python
"""CPU throughput/latency for EmbeddingGemma 2 under the container's CPU/RAM limits."""

import asyncio
import json
import logging
import os
import platform
import random
import resource
import time

import numpy as np
import torch

from app.utils.observability import configure_logging, log_json
from egpoc.config import (BENCH_DOC_SAMPLE, BENCH_PAGES, BENCH_QUERY_SAMPLE, DATA_DIR, SEED, STRATEGY,
                          TEST_BOOK_IDS)
from egpoc.db import connect
from egpoc.gemma import GemmaEmbedder
from egpoc.questions import SYNTHETIC_PATH, load_jsonl

logger = logging.getLogger("egpoc.bench")
BENCH_PATH = DATA_DIR / "bench.json"


async def main() -> None:
    configure_logging()
    conn = await connect()
    try:
        texts = [r["text"] for r in await conn.fetch(
            "SELECT text FROM poc.chunks WHERE strategy = $1 ORDER BY id", STRATEGY)]
        chunks = await conn.fetchval(
            "SELECT count(*) FROM poc.chunks WHERE book_id = ANY($1::text[])", list(TEST_BOOK_IDS))
        pages = await conn.fetchval(
            "SELECT count(*) FROM pages WHERE book_id = ANY($1::text[])", list(TEST_BOOK_IDS))
    finally:
        await conn.close()
    docs = random.Random(SEED).sample(texts, BENCH_DOC_SAMPLE)
    questions = [q["question"] for q in load_jsonl(SYNTHETIC_PATH)][:BENCH_QUERY_SAMPLE]

    gemma = GemmaEmbedder()
    gemma.embed_documents(docs[:64])  # warm-up
    started = time.perf_counter()
    gemma.embed_documents(docs)
    docs_per_sec = len(docs) / (time.perf_counter() - started)

    for q in questions[:10]:
        gemma.embed_query(q)
    latencies = []
    for q in questions:
        t0 = time.perf_counter()
        gemma.embed_query(q)
        latencies.append((time.perf_counter() - t0) * 1000)

    chunks_per_page = chunks / pages
    result = {
        "arch": platform.machine(),
        "cpus": os.environ["POC_CPUS"],
        "memory": os.environ["POC_MEMORY"],
        "torch_threads": torch.get_num_threads(),
        "param_count": gemma.param_count,
        "load_seconds": gemma.load_seconds,
        "docs_per_sec": docs_per_sec,
        "chunks_per_page": chunks_per_page,
        "book_minutes": BENCH_PAGES * chunks_per_page / docs_per_sec / 60,
        "query_p50_ms": float(np.percentile(latencies, 50)),
        "query_p95_ms": float(np.percentile(latencies, 95)),
        "peak_rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
    }
    BENCH_PATH.write_text(json.dumps(result, indent=2))
    log_json(logger, logging.INFO, "Benchmark", **result)


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run the benchmark** (nothing else heavy running on the Mac)

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.bench`
Expected: `Benchmark` log with `arch` `aarch64`, `torch_threads` equal to `POC_CPUS`, numeric `book_minutes` and `query_p95_ms`.

- [ ] **Step 3: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/bench.py
git commit -m "feat(poc): add CPU throughput and latency benchmark"
```

---

### Task 14: Go/no-go decision and report

**Files:**
- Create: `scripts/poc/embeddinggemma/egpoc/report.py`
- Test: `scripts/poc/embeddinggemma/tests/test_report.py`
- Create (generated): `docs/poc/embeddinggemma/REPORT.md`

**Interfaces:**
- Consumes: `data/results.json`, `data/bench.json`, `data/sanity.json`, `data/pool_stats.json`.
- Produces: `decide(metrics: dict, bench: dict) -> dict` returning `{"variants": {variant: {"passed": bool, "checks": [{"name", "value", "threshold", "ok"}]}}, "recommended": str | None}`; `render(...) -> str`.

- [ ] **Step 1: Write failing tests `tests/test_report.py`**

```python
from egpoc.report import decide


def m(s25, ndcg):
    return {"success@25": s25, "ndcg@10": ndcg}


def metrics(g768, g512, g256):
    base = {"gemini": m(0.90, 0.60), "gemma768": g768, "gemma512": g512, "gemma256": g256}
    return {"synthetic": {"pool": base}, "real": {"pool": base}}


GOOD_BENCH = {"book_minutes": 12.0, "query_p95_ms": 40.0}


def test_recommends_smallest_passing_dimension():
    out = decide(metrics(m(0.89, 0.60), m(0.88, 0.59), m(0.86, 0.58)), GOOD_BENCH)
    assert out["recommended"] == "gemma256"


def test_ndcg_drop_over_three_points_fails():
    out = decide(metrics(m(0.89, 0.60), m(0.88, 0.59), m(0.88, 0.56)), GOOD_BENCH)
    assert not out["variants"]["gemma256"]["passed"]
    assert out["recommended"] == "gemma512"


def test_recall_ratio_below_95_percent_fails():
    out = decide(metrics(m(0.85, 0.60), m(0.85, 0.60), m(0.85, 0.60)), GOOD_BENCH)
    assert out["recommended"] is None


def test_slow_benchmark_fails_everything():
    out = decide(metrics(m(0.90, 0.60), m(0.90, 0.60), m(0.90, 0.60)), {"book_minutes": 45.0, "query_p95_ms": 40.0})
    assert out["recommended"] is None
```

- [ ] **Step 2: Run to verify failure**

Run: `PT tests/test_report.py -q`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement `egpoc/report.py`**

```python
"""Go/no-go decision and REPORT.md rendering."""

import asyncio
import json
import logging

from app.utils.observability import configure_logging, log_json
from egpoc.config import (BOOK_MINUTES_MAX, DATA_DIR, GEMMA_DIMS, NDCG_MAX_DROP, QUERY_P95_MS_MAX,
                          RECALL_RATIO_MIN, REPORT_PATH, TOP_K)
from egpoc.db import connect

logger = logging.getLogger("egpoc.report")
SETS = ("synthetic", "real")


def decide(metrics: dict, bench: dict) -> dict:
    variants = {}
    for dim in GEMMA_DIMS:
        v = f"gemma{dim}"
        checks = []
        for s in SETS:
            gem, cand = metrics[s]["pool"]["gemini"], metrics[s]["pool"][v]
            floor = RECALL_RATIO_MIN * gem["success@25"]
            checks.append({"name": f"{s} Recall@25", "value": cand["success@25"], "threshold": f">= {floor:.3f}",
                           "ok": cand["success@25"] >= floor})
            drop = gem["ndcg@10"] - cand["ndcg@10"]
            checks.append({"name": f"{s} nDCG@10 drop", "value": drop, "threshold": f"<= {NDCG_MAX_DROP}",
                           "ok": drop <= NDCG_MAX_DROP + 1e-9})
        checks.append({"name": "500-page book minutes", "value": bench["book_minutes"],
                       "threshold": f"<= {BOOK_MINUTES_MAX}", "ok": bench["book_minutes"] <= BOOK_MINUTES_MAX})
        checks.append({"name": "query p95 ms", "value": bench["query_p95_ms"],
                       "threshold": f"< {QUERY_P95_MS_MAX}", "ok": bench["query_p95_ms"] < QUERY_P95_MS_MAX})
        variants[v] = {"passed": all(c["ok"] for c in checks), "checks": checks}
    passing = [f"gemma{d}" for d in sorted(GEMMA_DIMS) if variants[f"gemma{d}"]["passed"]]
    return {"variants": variants, "recommended": passing[0] if passing else None}


def _metric_table(block: dict) -> list[str]:
    cols = ["success@5", "success@10", "success@25", "mrr@10", "ndcg@10", "n"]
    lines = ["| variant | " + " | ".join(cols) + " |", "|---" * (len(cols) + 1) + "|"]
    for variant, m in block.items():
        lines.append(f"| {variant} | " + " | ".join(
            str(int(m[c])) if c == "n" else f"{m[c]:.3f}" for c in cols) + " |")
    return lines


def _snippet(text: str) -> str:
    return text[:200].replace("\n", " ").replace("|", "¦")


def render(results: dict, bench: dict, sanity: dict, pool: dict, decision: dict, texts: dict[int, str]) -> str:
    rec = decision["recommended"]
    out = [
        "# EmbeddingGemma 2 PoC — Report",
        "",
        f"**Recommendation:** {'GO with `' + rec + '`' if rec else 'NO-GO'}",
        "",
        "Spec: `docs/superpowers/specs/2026-10-07-embeddinggemma-poc-design.md`",
        "",
        "## Stage 0 — Uyghur sanity",
        "",
        f"- Questions: {sanity['n']}; Gemma top-1 {sanity['gemma_top1']:.3f}; Gemini top-1 {sanity['gemini_top1']:.3f}",
        f"- Tokens per Uyghur word: {sanity['tokens_per_word']:.2f}; byte-fallback share: "
        f"{sanity['byte_fallback_share']:.3f}{' (WARNING)' if sanity['byte_fallback_warning'] else ''}",
        "",
        "## Pool",
        "",
        f"- Test chunks {pool['test_chunks']}, distractor chunks {pool['distractor_chunks']} "
        f"from {len(pool['distractor_books'])} books; offset fallback rate {pool['fallback_rate']:.3%}",
        "",
    ]
    for s, scopes in results["metrics"].items():
        for scope, block in scopes.items():
            out += [f"## Metrics — {s} questions, {scope} scope", "", *_metric_table(block), ""]
    out += ["## CPU benchmark (EmbeddingGemma 2)", "", "| field | value |", "|---|---|"]
    out += [f"| {k} | {v:.2f} |" if isinstance(v, float) else f"| {k} | {v} |" for k, v in bench.items()]
    out += ["", f"Prod images are amd64; this ran on {bench['arch']}. Re-run `egpoc.bench` on a matching "
            "GCP instance before production planning.", "", "## Go/no-go checks", ""]
    for v, d in decision["variants"].items():
        out += [f"### {v} — {'PASS' if d['passed'] else 'FAIL'}", "", "| check | value | threshold | ok |",
                "|---|---|---|---|"]
        out += [f"| {c['name']} | {c['value']:.3f} | {c['threshold']} | {'✅' if c['ok'] else '❌'} |"
                for c in d["checks"]]
        out.append("")

    best = rec or "gemma768"
    miss = TOP_K + 1
    rows = sorted(results["per_query"]["synthetic_pool"],
                  key=lambda q: -abs((q["ranks"]["gemini"] or miss) - (q["ranks"][best] or miss)))[:20]
    out += [f"## 20 largest disagreements (gemini vs {best}, synthetic, pool scope)", ""]
    for q in rows:
        out += [f"### {q['qid']} — gemini rank {q['ranks']['gemini']}, {best} rank {q['ranks'][best]}", "",
                f"**Question:** {q['question']}", "", f"**Gold:** {_snippet(texts[q['chunk_id']])}", "",
                f"| # | gemini | {best} |", "|---|---|---|"]
        for i in range(5):
            g = q["top5"]["gemini"][i] if i < len(q["top5"]["gemini"]) else None
            b = q["top5"][best][i] if i < len(q["top5"][best]) else None
            out.append(f"| {i + 1} | {_snippet(texts[g]) if g else ''} | {_snippet(texts[b]) if b else ''} |")
        out.append("")
    return "\n".join(out)


def _load(name: str) -> dict:
    return json.loads((DATA_DIR / name).read_text())


async def main() -> None:
    configure_logging()
    results, bench, sanity, pool = (_load(n) for n in ("results.json", "bench.json", "sanity.json", "pool_stats.json"))
    decision = decide(results["metrics"], bench)
    ids = {q["chunk_id"] for q in results["per_query"]["synthetic_pool"]}
    for q in results["per_query"]["synthetic_pool"]:
        for chunk_ids in q["top5"].values():
            ids.update(chunk_ids)
    conn = await connect()
    try:
        texts = dict(await conn.fetch("SELECT id, text FROM poc.chunks WHERE id = ANY($1::int[])", list(ids)))
    finally:
        await conn.close()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(results, bench, sanity, pool, decision, texts))
    log_json(logger, logging.INFO, "Report written", path=str(REPORT_PATH), recommended=decision["recommended"])


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests**

Run: `PT tests/test_report.py -q`
Expected: `4 passed`

- [ ] **Step 5: Generate the report**

Run: `./scripts/poc/embeddinggemma/run.sh python -m egpoc.report`
Expected: `Report written` with `recommended` set or `null`; `docs/poc/embeddinggemma/REPORT.md` exists.

- [ ] **Step 6: (Only if Stage 0 failed in Task 7)** Write `docs/poc/embeddinggemma/REPORT.md` by hand: recommendation NO-GO, the contents of `data/sanity.json`, and 5 sample question/passage pairs from `data/sanity_questions.jsonl`.

- [ ] **Step 7: Run the full test suite**

Run: `PT -q`
Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/poc/embeddinggemma/egpoc/report.py scripts/poc/embeddinggemma/tests/test_report.py \
  docs/poc/embeddinggemma/REPORT.md
git commit -m "feat(poc): add go/no-go decision and EmbeddingGemma PoC report"
```

- [ ] **Step 9: Hand off to the user**

Summarize the recommendation, the go/no-go table, and point the user at the disagreement section for review. If GO, the next step is a separate semantic-chunking spec that reuses `poc.pool_books`, the question sets and `egpoc.evaluate` with a new `strategy` value.
