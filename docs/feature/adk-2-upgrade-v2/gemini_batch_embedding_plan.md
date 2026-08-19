# Gemini Batch API Embedding Architecture & Implementation Plan

## Executive Summary

This document outlines the architecture and implementation plan to integrate the **Gemini Batch API** for vector embeddings generation in **Kitabim.AI**.

Using Gemini Batch API for bulk embedding tasks provides a **50% cost reduction** compared to standard online/real-time inference and avoids hitting standard API rate limits during large book ingestions. To ensure zero disruption to current operations, the system will support a **dual-mode architecture**:
- **Online Mode (Default / Fallback)**: Real-time embedding pipeline using `GeminiEmbeddings.aembed_documents()` (`batchEmbedContents`).
- **Batch Mode**: Asynchronous batch processing using `client.batches.create()` with GCS input/output JSONL datasets and Gemini Files API.

The feature will be controlled dynamically via a system configuration flag (`embed_batch_enabled`) stored in the `system_configs` table — matching the naming convention of the existing `ocr_batch_enabled` flag. Administrators can toggle between modes at runtime without restarting services.

A single batch job is allowed to span **multiple books**, mirroring the existing online `embedding_scanner`, which claims idle pages across all books in one flat sweep (chunk embedding has no per-book dependency, unlike OCR which needs a per-book PDF document). Grouping strictly by `book_id` would fragment a `scanner_page_limit`-sized claim spanning many small books into many tiny batch submissions, each paying its own GCS/Files-API upload and poll overhead — eroding the cost benefit the Batch API is meant to provide.

---

## Technical Architecture

```mermaid
flowchart TD
    subgraph Trigger & Ingestion
        A[Embedding Scanner: claim idle pages\nacross ALL books, like today] --> B{system_config:\nembed_batch_enabled}
    end

    subgraph Mode 1: Online Embedding (Existing)
        B -- false --> C[Standard embedding_job]
        C --> D[Fetch unembedded chunks for page]
        D --> E[Gemini API: aembed_documents / batchEmbedContents]
        E --> F[Update Chunk.embedding & Page embedding_milestone]
    end

    subgraph Mode 2: Batch Embedding (New)
        B -- true --> G[Submit Batch Embedding Job\nsingle job may span multiple books]
        G --> H[Extract Chunks & Build JSONL Dataset]
        H --> I[Upload JSONL to GCS & Gemini Files API]
        I --> J[Call client.batches.create]
        J --> K[Record batch_embedding_jobs entry in DB]
        
        L[Batch Embedding Poller Scanner] --> M[Poll client.batches.get]
        M --> N{Job Status}
        N -- RUNNING/PENDING --> O[Wait for next poll cycle]
        N -- SUCCEEDED --> P[Download Output JSONL from Gemini/GCS]
        P --> Q[Parse Embeddings & Update Chunk.embedding in DB]
        Q --> Q2{Per-line error\nfor a chunk?}
        Q2 -- yes --> Q3[Mark owning Page failed,\nretry_count++, leave chunk NULL]
        Q2 -- no --> R[Mark Pages & Book embedding_milestone succeeded]
        N -- FAILED --> S[Mark Pages/Chunks Failed / Trigger Retries]
    end
```

---

## Detailed Design Components

### 1. Database Schema & System Configuration

#### Database Migration (`packages/backend-core/migrations/071_add_batch_embedding_jobs.sql`)
A new table `batch_embedding_jobs` will track the lifecycle of Gemini Batch API embedding requests. Unlike `batch_ocr_jobs`, a single job is **not** scoped to one book — `book_ids` is an array so a job can span whatever cross-book page set the scanner claimed (see [Executive Summary](#executive-summary)). The `CHECK` constraint and `IF NOT EXISTS` guards mirror the landed `070_add_batch_ocr_jobs.sql` convention.

```sql
CREATE TABLE IF NOT EXISTS batch_embedding_jobs (
    id VARCHAR(64) PRIMARY KEY, -- UUID
    gemini_batch_id VARCHAR(255) UNIQUE, -- Gemini API batch job name (e.g. 'batches/98765432')
    book_ids VARCHAR(64)[] NOT NULL, -- Distinct Book IDs whose pages are included in this batch
    page_ids INT[] NOT NULL, -- Array of Page IDs included in batch
    chunk_ids INT[] NOT NULL, -- Array of Chunk IDs included in batch
    status VARCHAR(20) NOT NULL DEFAULT 'submitting',
    gcs_input_uri TEXT,
    gcs_output_uri TEXT,
    total_chunks INT NOT NULL DEFAULT 0,
    processed_chunks INT NOT NULL DEFAULT 0,
    error TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT check_batch_embedding_jobs_status CHECK (
        status IN ('submitting', 'submitted', 'running', 'succeeded', 'failed', 'cancelled')
    )
);

CREATE INDEX IF NOT EXISTS idx_batch_embedding_jobs_book_ids ON batch_embedding_jobs USING GIN (book_ids);
CREATE INDEX IF NOT EXISTS idx_batch_embedding_jobs_status ON batch_embedding_jobs(status);
```

Rollback migration (`packages/backend-core/migrations/071_rollback_add_batch_embedding_jobs.sql`):
```sql
DROP TABLE IF EXISTS batch_embedding_jobs CASCADE;
```

#### System Config Defaults (`packages/backend-core/app/db/seeds.py`)
Add the following system configuration keys:

| Config Key | Default Value | Description |
| :--- | :--- | :--- |
| `embed_batch_enabled` | `false` | Dynamically enables/disables Batch API embedding processing (`true`/`false`). Naming matches the existing `ocr_batch_enabled` flag. |
| `embed_batch_timeout_hours` | `24` | Timeout threshold after which a pending/running batch job is marked stale and retried. |
| `embed_batch_max_chunks_per_job` | `5000` | Caps how many chunks are placed in a single JSONL/batch submission. Unlike the dead `ocr_batch_size_per_job` config (seeded but never read — see code review), this key must actually be read by `submit_batch_embedding_job` to split an oversized claim into multiple submissions. |
| `embed_batch_max_retry_count` | `3` | Per-chunk retry ceiling before a permanently-failing chunk is skipped (embedding left `NULL`) so it doesn't block the page forever — mirrors `ocr_max_retry_count`. |

---

### 2. Service Layer (`packages/backend-core/app/services/batch_embedding_service.py`)

Provides core utilities for:
1. **JSONL Format Assembly**: Converts unembedded chunks into JSONL request lines adhering to Google GenAI Batch API format for embedding requests. **`outputDimensionality` must be computed from the configured model**, exactly like the online path does in `GeminiEmbeddings.aembed_documents()` (`3072` for `gemini-embedding-2`, `768` otherwise) — a hardcoded `768` would fail to insert into the `Chunk.embedding` column, which is `Vector(3072)` to match the currently-seeded `gemini-embedding-2` model:
   ```json
   {
     "custom_id": "chunk_1024",
     "request": {
       "content": {
         "parts": [
           {"text": "Sample text content of the chunk..."}
         ]
       },
       "outputDimensionality": 3072
     }
   }
   ```
2. **Submission (`submit_batch_embedding_job`)**:
   - Queries idle pages/chunks for a claimed set of `page_ids` (which, unlike batch OCR, may span multiple books — see [Executive Summary](#executive-summary)).
   - Splits into multiple submissions if the claim exceeds `embed_batch_max_chunks_per_job`.
   - Builds JSONL dataset with dynamic `outputDimensionality` (see above).
   - Uploads audit JSONL payload to GCS storage (`batch_embedding/inputs/<job_id>.jsonl`).
   - Uploads payload to Gemini Files API (`client.files.upload()`).
   - Submits batch job via `client.batches.create(model=embedding_model, src=uploaded_file.name)`.
   - Records `BatchEmbeddingJob` entry (with `book_ids` set to the distinct book IDs in this claim) in DB and updates page status to `in_progress`.
   - On submission failure: marks pages `embedding_milestone="failed"`, increments `retry_count`, **and calls `BookMilestoneService.update_book_milestone_for_step()` for every affected book** — the batch OCR service originally missed this and left `Book.ocr_milestone` stuck at `in_progress` indefinitely on submission failure; this must not be repeated here.
3. **Polling & Ingestion (`poll_and_process_batch_embedding_jobs`)**:
   - Queries `BatchEmbeddingJob` records with `status.in_(["submitting", "submitted", "running"])`.
   - Queries status from Gemini API (`client.batches.get(name=job.gemini_batch_id)`).
   - Upon `JOB_STATE_SUCCEEDED`:
     - Downloads result JSONL output (`client.files.download()` or GCS).
     - Parses vector float array per `custom_id` (`chunk_<id>`).
     - **Per-line failure handling (a job can be `SUCCEEDED` overall while individual lines carry an `error`, mirroring `_record_page_ocr_failure` in the OCR service)**: if a chunk's line has an `error` or an empty/missing embedding, leave `Chunk.embedding` as `NULL`, mark the *owning* `Page.embedding_milestone="failed"` with `retry_count` incremented and a `PipelineEvent("embedding_failed")` — do **not** mark that page `succeeded`. Once a page's `retry_count` exceeds `embed_batch_max_retry_count`, mark it `succeeded` anyway (chunk embedding stays permanently `NULL`) so one bad chunk can't block the page/book forever, matching the OCR precedent of skipping after exhausting retries.
     - For chunks that parsed successfully, batch updates `Chunk.embedding` in database.
     - Sets each fully-succeeded page's `embedding_milestone="succeeded"`, `is_indexed=True`, and emits pipeline events.
     - Updates milestone for every book in `job.book_ids` using `BookMilestoneService.update_book_milestone_for_step()`.
   - Upon failure or timeout (> `embed_batch_timeout_hours`):
     - Marks job status as `failed`, resets page/chunk retries, and updates milestone for every book in `job.book_ids`.

---

### 3. Worker Scanners & Scheduling

1. **`services/worker/scanners/embedding_scanner.py`**:
   - Reads `embed_batch_enabled` setting from `SystemConfigsRepository`.
   - If `True`: passes the claimed `page_ids` — still claimed across all books in one sweep, exactly as today — straight to `submit_batch_embedding_job()` without grouping by `book_id`. The service itself splits into multiple submissions only if the claim exceeds `embed_batch_max_chunks_per_job`.
   - If `False`: Enqueues standard real-time `embedding_job` (unchanged).
2. **`services/worker/scanners/batch_embedding_poller_scanner.py`**:
   - Runs periodically (every 1 minute) in the worker process to invoke `poll_and_process_batch_embedding_jobs()`.
   - **Registration in `services/worker/worker.py`**: add a new `from scanners.batch_embedding_poller_scanner import run_batch_embedding_poller_scanner` import line and a new `cron(run_batch_embedding_poller_scanner)` entry — as *additions* alongside the existing imports/cron entries, not as a replacement. A prior diff for the OCR poller once replaced an unrelated import line instead of adding a new one, which raised `NameError` at worker startup and crashed the entire worker process (not just the OCR path); the same mistake here would take down embedding, OCR, chunking, and every other scanner.
3. **`services/worker/scanners/stale_watchdog_scanner.py`**:
   - **Must exempt in-flight batch embedding pages from the existing 30-minute `STALE_THRESHOLD_MINUTES` reset**, the same way it already exempts `BatchOCRJob` pages today via its `active_batch_page_ids` query. Add an equivalent query against `BatchEmbeddingJob` (`status.in_(["submitting", "submitted", "running"])`) and union its `page_ids` into the exemption set. Without this, pages sit at `embedding_milestone="in_progress"` for longer than 30 minutes (batch jobs run for up to `embed_batch_timeout_hours`, default 24h), get reset to `idle` by the watchdog, get re-claimed and re-dispatched as a duplicate online `embedding_job`, and race with the original batch job's writes to `Chunk.embedding` when it later completes. This exact bug was already caught and fixed for `BatchOCRJob` — see `code-review-worker-2026-07-22.md`.
   - Separately, also monitor stuck `BatchEmbeddingJob` instances (jobs in `submitted`/`running` for > 2 hours with no progress) and trigger recovery — this is in addition to, not instead of, the 30-minute exemption above.

---

### 4. Verification & Testing

1. **Unit & Integration Tests** (`packages/backend-core/tests/app/services/batch_embedding_service_test.py`) — the batch OCR test suite shipped with happy-path-only coverage per code review; this feature must not repeat that gap:
   - JSONL payload generation, including `outputDimensionality` matching the configured model (assert `768` vs `3072` for both model families, not just the default).
   - Batch submission across pages spanning **multiple books**, asserting a single `BatchEmbeddingJob.book_ids` array with all distinct book IDs.
   - Submission split when the claim exceeds `embed_batch_max_chunks_per_job`.
   - Submission failure path (`client.batches.create` raises) — assert `Page.embedding_milestone="failed"`, `retry_count` incremented, **and** `Book.embedding_milestone` updated for every affected book (not just the page-level write).
   - Result JSONL parsing: full-success case, a per-line `error` on one chunk while the job status is `SUCCEEDED` (assert that chunk's `Chunk.embedding` stays `NULL` and its page is marked `failed`, not `succeeded`), and the retry-exhaustion skip path.
   - Timeout path (`created_at` older than `embed_batch_timeout_hours`).
   - `FAILED` / `CANCELLED` Gemini batch state handling.
   - No-active-jobs early return (no Gemini API calls made).
   - `stale_watchdog_scanner_test.py`: assert pages tied to an active `BatchEmbeddingJob` are exempted from the 30-minute reset, and pages tied to a completed/failed job are not.
2. **Local End-to-End Test**:
   - Enable `embed_batch_enabled = "true"` via DB seed / admin config.
   - Run document ingestion pipeline and verify batch job submission, poller execution, vector persistence, and book milestone completion across a multi-book batch.

---
