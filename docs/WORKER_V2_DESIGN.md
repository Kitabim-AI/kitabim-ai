# Worker v2 — Design Document

## Overview

Worker v2 is a ground-up redesign of the book processing pipeline. The core problem with v1 is that **pipeline step** and **execution state** are collapsed into a single `status` field (e.g. `ocr_processing`, `ocr_done`, `indexing`). This makes it hard to answer basic questions like "which step failed?" or "is this page being worked on right now?", and makes stale detection and retry logic step-specific and scattered.

Worker v2 separates these two concerns explicitly:

- **`pipeline_step`** — where the page is in the pipeline (`ocr | chunking | embedding`)
- **`milestone`** — the execution state of that step (`idle | in_progress | succeeded | failed`)

This makes state unambiguous, stale detection uniform, and adding new pipeline steps trivial.

Worker v1 stays untouched. Worker v2 runs alongside it using new database columns.

---

## Goals

- Clear, unambiguous page and book state at all times
- Per-page retry with exhausted retry detection
- Uniform stale detection across all steps (one rule)
- Each component has a single responsibility
- Adding a new pipeline step requires only a new scanner + job, nothing else changes

## Non-Goals (v2)

- Gemini Batch API mode (realtime only)
- Circuit breaker (deferred to a later iteration)
- Backwards compatibility with v1 status columns

---

## Schema Changes

New columns added to existing tables. V1 columns are untouched.

### `pages` table

| Column | Type | Description |
|---|---|---|
| `v2_pipeline_step` | `varchar` | Current pipeline step: `ocr \| chunking \| embedding` |
| `v2_milestone` | `varchar` | Execution state of that step: `idle \| in_progress \| succeeded \| failed` |
| `v2_retry_count` | `integer` | Number of failed attempts for the current step. Default `0`. |

### `books` table

| Column | Type | Description |
|---|---|---|
| `v2_pipeline_step` | `varchar` | Active step for the book: `ocr \| chunking \| embedding \| ready`. `NULL` = not yet in v2 pipeline. |

---

## Architecture

```
worker_v2/
  scanners/
    gcs_discovery_scanner.py ← lists GCS uploads/, registers new books in DB
    pipeline_driver.py       ← state machine: initializes pages, advances steps, marks book ready
    ocr_scanner.py           ← claims idle ocr pages, dispatches OcrJob per book
    chunking_scanner.py      ← claims idle chunking pages, dispatches ChunkingJob
    embedding_scanner.py     ← claims idle embedding pages, dispatches EmbeddingJob
    stale_watchdog.py        ← resets stale in_progress pages to idle
  jobs/
    ocr_job.py            ← downloads PDF, OCRs pages via Gemini Vision
    chunking_job.py       ← chunks page text into DB records
    embedding_job.py      ← generates and stores embeddings
  worker.py               ← ARQ WorkerSettings for v2
```

---

## Component Responsibilities

### GcsDiscoveryScanner

Polls the GCS bucket and registers books that aren't yet in the database. Runs every 5 minutes.

**Responsibilities:**

1. List all `uploads/*.pdf` files in the GCS data bucket
2. Skip files already known to the DB (by filename or book ID)
3. Download unknown files to compute SHA-256 hash and extract PDF metadata
4. Skip content-hash duplicates (same file under a different name)
5. Standardize the GCS path to `uploads/{book_id}.pdf` (rename if needed)
6. Insert a `Book` record with `status='pending'` and `v2_pipeline_step=NULL`

PipelineDriver picks up the new book on its next run and initializes its pages into `ocr / idle`. No explicit OCR triggering is needed.

The manual admin API (`POST /api/books/storage/sync`) continues to use the existing `DiscoveryService` directly.

---

### PipelineDriver

The single entry point into the v2 pipeline and the only component that advances pipeline steps. Runs every minute as a cron job.

**Responsibilities:**

1. **Initialize** — finds pages with `v2_pipeline_step IS NULL`, sets them to `ocr / idle`
2. **Promote** — advances pages whose current step has succeeded to the next step
3. **Book ready** — marks a book as `ready` when all its pages are terminal

**Promotion rules:**

```
ocr / succeeded       →  chunking / idle
chunking / succeeded  →  embedding / idle
```

Embedding is the end of the page pipeline. There is no further step — `embedding / succeeded` is the terminal success state for a page.

**Book ready condition (option b — pragmatic):**

A book is marked `v2_pipeline_step = ready` when every page is in a terminal state:
- `pipeline_step = embedding AND milestone = succeeded`  (processed successfully)
- `milestone = failed AND v2_retry_count >= max_retries`  (exhausted, skipped)

This means a book with a few permanently failed pages is still marked ready and searchable.

---

### Scanners (OcrScanner / ChunkingScanner / EmbeddingScanner)

Each scanner is responsible for one step only: **claim idle pages atomically and dispatch a job**.

**Generic scanner flow (every 1 min):**

```sql
-- Step 1: Atomic claim (prevents double-dispatch)
UPDATE pages
SET v2_milestone = 'in_progress'
WHERE v2_pipeline_step = '<step>'
  AND v2_milestone = 'idle'
LIMIT <scanner_page_limit>
RETURNING id
```

```python
# Step 2: Dispatch job with claimed page IDs
await redis.enqueue_job("<step>_job", page_ids=[...])
```

**OcrScanner — groups by book:**

OCR requires a PDF file. Processing pages from the same book in one job means one PDF download. The OcrScanner therefore groups idle OCR pages by book and dispatches one `OcrJob` per book.

```
OcrScanner (every 1 min):
  1. Find distinct book_ids where pages have (ocr / idle)
  2. For each book (up to N books per run):
       a. Claim all idle ocr pages for that book → in_progress
       b. Dispatch OcrJob(book_id, page_ids)
```

**ChunkingScanner / EmbeddingScanner:**

Chunking and embedding only need text from the database, so pages from any book can be processed together.

```
ChunkingScanner / EmbeddingScanner (every 1 min):
  1. Claim up to N idle pages across all books → in_progress
  2. Dispatch one job with all claimed page IDs
```

---

### Jobs

Jobs are pure executors — they process pages and report success or failure. They have no knowledge of what step comes next.

**OcrJob(book_id, page_ids):**

```
1. Download PDF once from storage
2. For each page (async, semaphore-limited concurrency):
     a. Render page as image (PyMuPDF, 1.5x zoom)
     b. Call Gemini Vision API
     c. Normalize text (Uyghur character normalization, markdown cleanup)
     d. Save extracted text to page record
     e. Set v2_milestone = 'succeeded'
   On failure:
     f. v2_retry_count++
     g. Set v2_milestone = 'failed'
3. Update book.v2_pipeline_step = 'ocr' (marks book as actively in OCR step)
```

**ChunkingJob(page_ids):**

```
1. For each page:
     a. Load text from DB
     b. Apply recursive character text splitter
     c. Save Chunk records (embedding = NULL)
     d. Set v2_milestone = 'succeeded'
   On failure:
     e. v2_retry_count++
     f. Set v2_milestone = 'failed'
```

**EmbeddingJob(page_ids):**

```
1. For each page:
     a. Load chunks from DB
     b. Generate 768-dim embeddings via Gemini Embeddings API
     c. Store vectors on chunk records
     d. Set v2_milestone = 'succeeded'
   On failure:
     e. v2_retry_count++
     f. Set v2_milestone = 'failed'
```

---

### StaleWatchdog

Resets pages that are stuck in `in_progress` (e.g. job crashed, pod restarted). One rule applies to all steps.

```sql
UPDATE pages
SET v2_milestone = 'idle'
WHERE v2_milestone = 'in_progress'
  AND updated_at < NOW() - INTERVAL '30 minutes'
```

Runs every 30 minutes.

---

## Cron Schedule

| Scanner | Interval | Notes |
|---|---|---|
| `gcs_discovery_scanner` | Every 5 min | List GCS bucket, register new books |
| `pipeline_driver` | Every 1 min | Initialize + promote + book ready |
| `ocr_scanner` | Every 1 min | Groups by book |
| `chunking_scanner` | Every 1 min | Cross-book |
| `embedding_scanner` | Every 1 min | Cross-book |
| `stale_watchdog` | Every 30 min | Uniform reset for all steps |

---

## State Machine

```mermaid
flowchart TD
    NULL["v2_pipeline_step = NULL\n(new page, not yet in v2)"]
    OCR_IDLE["ocr / idle"]
    OCR_IP["ocr / in_progress"]
    OCR_OK["ocr / succeeded"]
    OCR_FAIL["ocr / failed"]
    CHUNK_IDLE["chunking / idle"]
    CHUNK_IP["chunking / in_progress"]
    CHUNK_OK["chunking / succeeded"]
    CHUNK_FAIL["chunking / failed"]
    EMB_IDLE["embedding / idle"]
    EMB_IP["embedding / in_progress"]
    EMB_OK["embedding / succeeded\n(terminal — page done)"]
    EMB_FAIL["embedding / failed"]
    TERMINAL["milestone = failed\nretry_count >= max\n(terminal — skipped)"]

    NULL -->|PipelineDriver: initialize| OCR_IDLE
    OCR_IDLE -->|OcrScanner: claim| OCR_IP
    OCR_IP -->|OcrJob: success| OCR_OK
    OCR_IP -->|OcrJob: failure| OCR_FAIL
    OCR_FAIL -->|StaleWatchdog or Scanner retry| OCR_IDLE
    OCR_FAIL -->|retry_count >= max| TERMINAL
    OCR_OK -->|PipelineDriver: promote| CHUNK_IDLE

    CHUNK_IDLE -->|ChunkingScanner: claim| CHUNK_IP
    CHUNK_IP -->|ChunkingJob: success| CHUNK_OK
    CHUNK_IP -->|ChunkingJob: failure| CHUNK_FAIL
    CHUNK_FAIL -->|Scanner retry| CHUNK_IDLE
    CHUNK_FAIL -->|retry_count >= max| TERMINAL
    CHUNK_OK -->|PipelineDriver: promote| EMB_IDLE

    EMB_IDLE -->|EmbeddingScanner: claim| EMB_IP
    EMB_IP -->|EmbeddingJob: success| EMB_OK
    EMB_IP -->|EmbeddingJob: failure| EMB_FAIL
    EMB_FAIL -->|Scanner retry| EMB_IDLE
    EMB_FAIL -->|retry_count >= max| TERMINAL

    EMB_OK -->|PipelineDriver: all pages terminal| BookReady([book.v2_pipeline_step = ready])
    TERMINAL -->|PipelineDriver: all pages terminal| BookReady

    classDef idle fill:#e9edc9,stroke:#606c38
    classDef active fill:#fff3cd,stroke:#856404
    classDef done fill:#d4f1f4,stroke:#189ab4
    classDef fail fill:#ffcccb,stroke:#d32f2f
    classDef terminal fill:#f1f1f1,stroke:#888,stroke-dasharray:4 4
    classDef book fill:#d4f1f4,stroke:#189ab4,stroke-width:2px

    class OCR_IDLE,CHUNK_IDLE,EMB_IDLE idle
    class OCR_IP,CHUNK_IP,EMB_IP active
    class OCR_OK,CHUNK_OK,EMB_OK done
    class OCR_FAIL,CHUNK_FAIL,EMB_FAIL fail
    class TERMINAL terminal
    class BookReady book
```

---

## Retry Logic

Retry state is tracked on the page row via `v2_retry_count`.

| Scenario | Behaviour |
|---|---|
| Job sets `milestone = failed` | `v2_retry_count++` |
| Scanner finds `milestone = failed AND retry_count < max` | Resets to `idle` — page will be retried |
| Scanner finds `milestone = failed AND retry_count >= max` | Skips — page is terminal |
| Stale watchdog fires | Resets `in_progress → idle`, does **not** increment `retry_count` (timeout ≠ failure) |

Max retries is configurable via `system_configs` (e.g. `v2_ocr_max_retry_count`, default `10`).

---

## Why This Is Better Than v1

| Concern | v1 | v2 |
|---|---|---|
| Which step failed? | `status = error` — ambiguous | `pipeline_step = ocr, milestone = failed` — explicit |
| Stale detection | Step-specific hardcoded timeouts in `maintenance.py` | One rule: `in_progress + timeout → idle` |
| Adding a new pipeline step | Touch `pdf_service`, `maintenance`, `queue`, `worker` | Add one scanner + one job, nothing else changes |
| Per-page retry | Partial — mixed into OCR job logic | First-class: `v2_retry_count` on the row, checked by scanner |
| Processing lock | TTL-based `processing_lock` column per book | `in_progress` milestone is the lock — no separate column |
| Monolithic job | `pdf_service.py` does OCR + chunking + embedding | Three focused jobs, each does one thing |
| Batch vs realtime code paths | Two parallel code paths | One path — realtime only |

---

## Migration Notes

- V1 columns (`status`, `processing_lock`, etc.) are left untouched
- V2 columns (`v2_pipeline_step`, `v2_milestone`, `v2_retry_count`) default to `NULL`
- PipelineDriver initializes pages into the v2 pipeline on its first run
- Both workers can run simultaneously during transition — they operate on different columns
- Feature flag: `USE_WORKER_V2` in `system_configs` controls which worker deployment is active
