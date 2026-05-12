# Worker Design — Event-Driven Pipeline

## Overview

The Kitabim.AI processing pipeline uses a **decoupled, event-driven architecture** based on the **Transactional Outbox Pattern**. This design ensures high reliability, observability, and responsiveness by separating the concern of "what work needs doing" from the "execution of that work."

Key characteristics:
- **`milestone` columns** — each stage (`ocr`, `chunking`, `embedding`, `spell_check`) has its own milestone in the `pages` table.
- **States** — `idle | in_progress | succeeded | failed`.
- **Mandatory pipeline** — `ocr → chunking → embedding` is sequential; a book becomes `ready` when embedding is terminal.
- **Spell check is independent** — it only requires OCR to be done, runs in parallel with chunking/embedding, and does **not** block book readiness.
- **Transactional Outbox** — the `pipeline_events` table captures successful milestones within the same database transaction as the result application.
- **Event Dispatcher** — a low-latency scanner that polls the outbox and immediately enqueues the next required job, bypasses traditional 1-minute cron delays.

---

## Goals

- Clear, unambiguous page and book state at all times
- Per-page retry with exhausted retry detection
- Uniform stale detection across all steps (one rule)
- Each component has a single responsibility
- Adding a new pipeline step requires only a new scanner + job, nothing else changes

## Non-Goals

- Gemini Batch API mode (realtime only)
- **Circuit breaker** — Implemented for AI services and Redis.
- Backwards compatibility with v1 status columns


---

## Schema
Current implementation uses granular milestone columns on the `pages` table and a `pipeline_step` column on the `books` table.

### `pages` table

| Column | Type | Description |
|---|---|---|
| `ocr_milestone` | `varchar` | State of OCR: `idle \| in_progress \| succeeded \| failed` |
| `chunking_milestone` | `varchar` | State of Chunking: `idle \| in_progress \| succeeded \| failed` |
| `embedding_milestone` | `varchar` | State of Embedding: `idle \| in_progress \| succeeded \| failed` |
| `spell_check_milestone` | `varchar` | State of Spell Check: `idle \| in_progress \| done \| failed` |
| `retry_count` | `integer` | Number of failed attempts for the current step. |

### `books` table

| Column | Type | Description |
|---|---|---|
| `pipeline_step` | `varchar` | Primary step for progress tracking: `ocr \| chunking \| embedding \| spell_check \| ready` |

---

## Architecture

```
worker/
  scanners/
    gcs_discovery_scanner.py ← lists GCS uploads/, registers new books in DB
    pipeline_driver.py       ← state machine: initializes pages, advances steps, marks book ready
    ocr_scanner.py           ← claims idle ocr pages, dispatches OcrJob per book
    chunking_scanner.py      ← claims idle chunking pages, dispatches ChunkingJob
    embedding_scanner.py     ← claims idle embedding pages, dispatches EmbeddingJob
    spell_check_scanner.py   ← claims idle spell_check pages, dispatches SpellCheckJob
    event_dispatcher.py      ← monitors outbox, triggers next-step jobs immediately
    auto_correct_scanner.py  ← claims all auto-correctable pages (daily)
    stale_watchdog.py        ← resets stale in_progress pages to idle
    maintenance_scanner.py   ← cleans up processed outbox events (daily)
  jobs/
    ocr_job.py            ← downloads PDF, OCRs pages via Gemini Vision
    chunking_job.py       ← chunks page text into DB records
    embedding_job.py      ← generates and stores embeddings
    spell_check_job.py    ← identifies unknown words and suggests corrections
    auto_correct_job.py   ← applies auto-correction rules to spell issues
    summary_job.py        ← generates semantic book summaries for RAG routing
  worker.py               ← ARQ WorkerSettings

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
6. Insert a `Book` record with `status='pending'` and `pipeline_step=NULL`

PipelineDriver picks up the new book on its next run and initializes its pages into `ocr / idle`. No explicit OCR triggering is needed.

The manual admin API (`POST /api/books/storage/sync`) continues to use the existing `DiscoveryService` directly.

---

### PipelineDriver

Handles pipeline bookkeeping. Runs every minute as a cron job.

**Responsibilities:**

1. **Initialize** — finds pages with `ocr_milestone = 'idle'` on non-ready books, ensures they are registered for processing
2. **Reset** — resets `failed` milestones back to `idle` when retries remain
3. **Book ready** — marks a book as `ready` when all **mandatory** pages are terminal

> **Note:** Sequential promotion (`ocr → chunking → embedding`) is **not** done by PipelineDriver. Each scanner enforces its own dependency by checking the upstream milestone directly (e.g. `ChunkingScanner` only claims pages where `ocr_milestone = 'succeeded'`).

**Mandatory pipeline (what gates book readiness):**

```
ocr / succeeded  →  (ChunkingScanner claims)  chunking / idle
chunking / succeeded  →  (EmbeddingScanner claims)  embedding / idle
```

Embedding is the terminal mandatory step. A book is marked `pipeline_step = ready` when every page has `embedding_milestone = 'succeeded'` OR any mandatory step has failed with exhausted retries.

**Spell check is NOT mandatory** — it is a quality layer that runs independently (see SpellCheckScanner below) and does not block book readiness.

This means a book with a few permanently failed pages is still marked ready and searchable.

---

### Scanners (OcrScanner / ChunkingScanner / EmbeddingScanner)

Each scanner is responsible for one step only: **claim idle pages atomically and dispatch a job**.

**Generic scanner flow (every 1 min):**

```sql
-- Step 1: Atomic claim (prevents double-dispatch)
UPDATE pages
SET <step>_milestone = 'in_progress'
WHERE <step>_milestone = 'idle'
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
ChunkingScanner (every 1 min):
  Dependency: ocr_milestone = 'succeeded'
  1. Claim up to N idle chunking pages across all books → in_progress
  2. Dispatch one job with all claimed page IDs

EmbeddingScanner (every 1 min):
  Dependency: chunking_milestone = 'succeeded'
  1. Claim up to N idle embedding pages across all books → in_progress
  2. Dispatch one job with all claimed page IDs
```

**SpellCheckScanner:**

Spell check runs as an **independent quality layer** — it does not block book readiness and does not need to wait for embedding.

```
SpellCheckScanner (every 1 min):
  Dependency: ocr_milestone = 'succeeded'  (NOT embedding)
  1. Identify books currently in spell_check step + new candidates (up to max_concurrent limit)
  2. Claim idle spell-check pages for those books → in_progress
  3. Dispatch SpellCheckJob with claimed page IDs
```

A book can be fully `ready` (searchable, in the library) while its spell check is still running in the background.

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
     e. Set <step>_milestone = 'succeeded'
   On failure:
     e.retry_count++
     f. Set <step>_milestone = 'failed'
3. Update book.pipeline_step = 'ocr' (marks book as actively in OCR step)
```

**ChunkingJob(page_ids):**

```
1. For each page:
     a. Load text from DB
     b. Apply recursive character text splitter
     c. Delete chunks with index >= new chunk count (handles shrinking pages)
     d. Upsert remaining chunks — on conflict update text and reset embedding/embedding_v1 to NULL
     e. Set chunking_milestone = 'succeeded'
   On failure:
     f. retry_count++
     g. Set chunking_milestone = 'failed'
```

**EmbeddingJob(page_ids):**

```
1. For each page:
     a. Load chunks from DB
     b. Generate 768-dim embeddings via Gemini Embeddings API
     c. Store vectors on chunk records
     d. Set embedding_milestone = 'succeeded'
   On failure:
     e. retry_count++
     f. Set embedding_milestone = 'failed'
```

---

### StaleWatchdog

Resets pages that are stuck in `in_progress` (e.g. job crashed, pod restarted). One rule applies to all steps.

```sql
UPDATE pages
SET <step>_milestone = 'idle'
WHERE <step>_milestone = 'in_progress'
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
| `spell_check_scanner`| Every 1 min | Cross-book |
| `event_dispatcher` | Startup + 1 min (high frequency pool) | Triggers reactive progression |
| `stale_watchdog` | Every 30 min | Uniform reset for all steps |
| `maintenance_scanner`| Daily at 3 AM | Database house keeping |
| `summary_scanner`     | Every 5 min | Regenerates missing book summaries |
| `auto_correct_scanner` | Daily at 3 AM | Bulk applies spell corrections |


---

## State Machine

```mermaid
flowchart TD
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
    EMB_OK["embedding / succeeded"]
    EMB_FAIL["embedding / failed"]
    SPELL_IDLE["spell_check / idle\n(independent quality layer)"]
    SPELL_IP["spell_check / in_progress"]
    SPELL_OK["spell_check / done"]
    SPELL_FAIL["spell_check / failed"]
    TERMINAL["ocr|chunking|embedding failed\nretry_count >= max\n(mandatory step — skipped)"]

    OCR_IDLE -->|OcrScanner: claim| OCR_IP
    OCR_IP -->|OcrJob: success| OCR_OK
    OCR_IP -->|OcrJob: failure| OCR_FAIL
    OCR_FAIL -->|StaleWatchdog or Scanner retry| OCR_IDLE
    OCR_FAIL -->|retry_count >= max| TERMINAL
    OCR_OK -->|ChunkingScanner: dep satisfied| CHUNK_IDLE
    OCR_OK -.->|SpellCheckScanner: dep satisfied| SPELL_IDLE

    CHUNK_IDLE -->|ChunkingScanner: claim| CHUNK_IP
    CHUNK_IP -->|ChunkingJob: success| CHUNK_OK
    CHUNK_IP -->|ChunkingJob: failure| CHUNK_FAIL
    CHUNK_FAIL -->|Scanner retry| CHUNK_IDLE
    CHUNK_FAIL -->|retry_count >= max| TERMINAL
    CHUNK_OK -->|EmbeddingScanner: dep satisfied| EMB_IDLE

    EMB_IDLE -->|EmbeddingScanner: claim| EMB_IP
    EMB_IP -->|EmbeddingJob: success| EMB_OK
    EMB_IP -->|EmbeddingJob: failure| EMB_FAIL
    EMB_FAIL -->|Scanner retry| EMB_IDLE
    EMB_FAIL -->|retry_count >= max| TERMINAL
    EMB_OK -->|PipelineDriver: mandatory terminal| BookReady([book.pipeline_step = ready])
    TERMINAL -->|PipelineDriver: mandatory terminal| BookReady

    SPELL_IDLE -->|SpellCheckScanner: claim| SPELL_IP
    SPELL_IP -->|SpellCheckJob: success| SPELL_OK
    SPELL_IP -->|SpellCheckJob: failure| SPELL_FAIL
    SPELL_FAIL -->|Scanner retry| SPELL_IDLE
    SPELL_FAIL -->|retry_count >= max| SPELL_TERMINAL[spell_check / exhausted]

    classDef idle fill:#e9edc9,stroke:#606c38
    classDef active fill:#fff3cd,stroke:#856404
    classDef done fill:#d4f1f4,stroke:#189ab4
    classDef fail fill:#ffcccb,stroke:#d32f2f
    classDef terminal fill:#f1f1f1,stroke:#888,stroke-dasharray:4 4
    classDef book fill:#d4f1f4,stroke:#189ab4,stroke-width:2px

    class OCR_IDLE,CHUNK_IDLE,EMB_IDLE,SPELL_IDLE idle
    class OCR_IP,CHUNK_IP,EMB_IP,SPELL_IP active
    class OCR_OK,CHUNK_OK,EMB_OK,SPELL_OK done
    class OCR_FAIL,CHUNK_FAIL,EMB_FAIL,SPELL_FAIL fail
    class TERMINAL terminal
    class BookReady book
```

---

## Retry Logic

Retry state is tracked on the page row via `retry_count`.

| Scenario | Behaviour |
|---|---|
| Job sets `milestone = failed` | `retry_count++` |
| Scanner finds `milestone = failed AND retry_count < max` | Resets to `idle` — page will be retried |
| Scanner finds `milestone = failed AND retry_count >= max` | Skips — page is terminal |
| Stale watchdog fires | Resets `in_progress → idle`, does **not** increment `retry_count` (timeout ≠ failure) |

Max retries is configurable via `system_configs` (e.g. `ocr_max_retry_count`, default `10`).

---

