# Worker Design — Event-Driven Pipeline

See also: [BOOK_PROCESSING_DIAGRAM.md](BOOK_PROCESSING_DIAGRAM.md) for the visual pipeline diagram, admin recovery actions, and page-milestone transition diagrams.

## Overview

The Kitabim.AI processing pipeline is a **decoupled, event-driven architecture** built on the **Transactional Outbox Pattern**. Work is expressed as small, single-purpose ARQ jobs; scanners run on a cron schedule to find eligible work and dispatch jobs; an event dispatcher reacts to completed work and dispatches the next step immediately, without waiting for the next cron tick.

Key characteristics:

- **Milestone columns** — each pipeline step (`ocr`, `chunking`, `embedding`, `spell_check`) has its own state column on the `pages` table, denormalized onto `books` for fast listing/filtering.
- **States** — `idle | in_progress | succeeded | failed`, one per step, per page.
- **Mandatory pipeline** — `ocr → chunking → embedding` is sequential; embedding is the terminal mandatory step.
- **Spell check** — an independent quality layer. It only depends on OCR being done, runs in parallel with chunking/embedding, and does not block book readiness.
- **Knowledge graph extraction, spell check, history dictionary extraction, and Gemini Batch API mode for OCR/embedding/history extraction are all feature-flagged** — see [Feature Flags](#feature-flags).
- **History dictionary extraction is a fully separate, admin-triggered sub-system.** It does not use the milestone columns/state machine described below at all — see [HistoryExtractionJob](#historyextractionjob--batchhistorypollerscanner).
- **Transactional Outbox** — the `pipeline_events` table records a row for every milestone transition, written in the same DB transaction as the result. The Event Dispatcher polls this table and immediately enqueues the next job, so most pages move `ocr → chunking → embedding` inside seconds rather than waiting for the next 1-minute scanner tick.
- **Per-page distributed locking** — `ocr_job`, `chunking_job`, `embedding_job`, and `spell_check_job` each wrap their claimed page IDs in a `MultiPageLock` (Redis `SET NX` per page, 1‑hour expiry, keyed as `lock:{prefix}:{page_id}` with each stage passing its own `prefix` — e.g. `ocr`, `chunking` — so the same page can be locked independently per pipeline stage) before processing, so the same page can never be worked on by two job instances concurrently even if a scanner double-claims it.
- **Optional Gemini Batch API mode** — OCR, embedding, and history dictionary extraction can each independently run through the Gemini Batch API instead of the interactive API (`ocr_batch_enabled` / `embed_batch_enabled` / `history_batch_enabled`, all `false` by default), trading latency (async submit + poll) for lower cost on high-volume ingestion. See [OCR_DESIGN.md](OCR_DESIGN.md#data-flow) and [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md#data-flow) for the full OCR/embedding batch-mode algorithm.

## Goals

- Clear, unambiguous page and book state at all times
- Per-page retry with exhausted-retry detection
- Uniform stale-page detection across all steps (one rule, worker-heartbeat aware)
- Each component has a single responsibility: scanners claim and dispatch, jobs execute
- Adding a new pipeline step only requires a new scanner + job

## Feature Flags

Several pipeline stages are gated by boolean flags in `system_configs` (checked at the top of the relevant scanner/job, default is what ships in `packages/backend-core/app/db/seeds.py`):

| Flag | Default | Gates |
|---|---|---|
| `spell_check_enabled` | `true` | `spell_check_scanner` — returns immediately if not `"true"` |
| `auto_correct_enabled` | `true` | `auto_correct_scanner` — returns immediately if not `"true"` |
| `kg_enabled` | `false` | `graph_scanner`, `graph_resolution_scanner`, and `knowledge_graph_job` — all no-op if not `"true"` (`knowledge_graph_job` additionally resets `graph_milestone` back to `idle`); also gates `POST /{book_id}/reprocess/graph`, which returns `400` if the flag isn't `"true"` |
| `ocr_batch_enabled` | `false` | `ocr_job` — submits a `batch_ocr_jobs` row via the Gemini Batch API instead of OCR'ing inline when `"true"` |
| `embed_batch_enabled` | `false` | `embedding_scanner` — submits a `batch_embedding_jobs` row via the Gemini Batch API instead of dispatching `embedding_job` when `"true"` |
| `history_extraction_enabled` | `true` | `history_extraction_job` — returns `{"status": "skipped", ...}` without processing if not `"true"`; also gates `POST /api/admin/books/{book_id}/extract-history`, which returns `400` if the flag isn't `"true"` |
| `history_batch_enabled` | `false` | `history_extraction_job` — submits a `batch_history_extraction_jobs` row via the Gemini Batch API instead of extracting inline when `"true"` |

> **Knowledge graph extraction is off by default in a fresh environment.** It must be explicitly enabled via `system_configs` before `graph_scanner` or the "Reprocess Graph" admin action will do anything.

## Schema

### `pages` table

| Column | Type | Description |
|---|---|---|
| `ocr_milestone` | `varchar` | `idle \| in_progress \| succeeded \| failed` |
| `chunking_milestone` | `varchar` | `idle \| in_progress \| succeeded \| failed` |
| `embedding_milestone` | `varchar` | `idle \| in_progress \| succeeded \| failed` |
| `spell_check_milestone` | `varchar` | `idle \| in_progress \| succeeded \| failed` |
| `retry_count` | `integer` | Shared failure counter for the page — incremented by whichever step's job fails (OCR, chunking, embedding, or spell check all write to the same counter). |
| `worker_id` / `claimed_at` | `varchar` / `timestamptz` | Set by the scanner that claimed the page; used by `StaleWatchdog` to detect dead workers. |
| `pipeline_step` | `varchar` | Legacy/display field showing the step a page is currently associated with (`ocr`, `chunking`, `embedding`, `spell_check`). Not read by scanners to gate work — milestones are the source of truth. |

### `books` table

| Column | Type | Description |
|---|---|---|
| `pipeline_step` | `varchar` | Coarse progress indicator for the UI: `ocr \| chunking \| embedding \| spell_check \| ready \| failed` |
| `status` | `varchar` | `pending \| ready \| error` — the field that actually gates search visibility and further scanner eligibility |
| `ocr_milestone` / `chunking_milestone` / `embedding_milestone` / `spell_check_milestone` | `varchar` | Book-level rollups of the page milestones (`idle \| in_progress \| complete \| partial_failure \| failed`), maintained by `BookMilestoneService` for fast listing without joining `pages`. |
| `graph_milestone` | `varchar` | `idle \| in_progress \| complete \| partial \| failed`. `has_graph` in the API is derived as `graph_milestone == 'complete'` — there is no separate Neo4j lookup. |

Note: history dictionary extraction (`history_extraction_job`) does **not** use any of the columns above. It is tracked entirely through its own tables — `batch_history_extraction_jobs` (job/status, mirrors `batch_ocr_jobs`/`batch_embedding_jobs`), `history_dictionary_staging` (candidate terms awaiting admin review), and `history_dictionary` (published terms) — keyed by `book_id` with no page- or book-level milestone column.

## Architecture

```
worker/
  scanners/
    gcs_discovery_scanner.py   ← lists GCS uploads/, registers new books in DB
    pipeline_driver.py         ← state machine: initializes pages, resets retryable failures, marks book ready/error, enqueues summary_job
    ocr_scanner.py             ← claims idle ocr pages (grouped by book), dispatches OcrJob per book
    batch_ocr_poller_scanner.py ← polls in-flight batch_ocr_jobs, ingests results (feature-flagged path)
    chunking_scanner.py        ← claims idle chunking pages across all books, dispatches one ChunkingJob
    embedding_scanner.py       ← claims idle embedding pages across all books, dispatches one EmbeddingJob
                                  (or submits a batch_embedding_job inline if embed_batch_enabled)
    batch_embedding_poller_scanner.py ← polls in-flight batch_embedding_jobs, writes vectors back (feature-flagged path)
    spell_check_scanner.py     ← claims idle spell_check pages, dispatches SpellCheckJob (feature-flagged)
    event_dispatcher.py        ← polls the outbox, immediately dispatches the next job
    auto_correct_scanner.py    ← finds pages with auto-correctable spell issues, dispatches AutoCorrectJob in batches (feature-flagged)
    stale_watchdog_scanner.py  ← resets pages/books stuck in_progress using worker-heartbeat detection
    summary_scanner.py         ← backfills/retries missing book_summaries for ready books
    graph_scanner.py           ← backfills/retries missing knowledge graphs for ready books (feature-flagged; see note below)
    graph_resolution_scanner.py ← claims graph_resolution_queue rows every 5 min, dispatches GraphResolutionJob per scope (feature-flagged)
    batch_history_poller_scanner.py ← polls in-flight batch_history_extraction_jobs, ingests results into history_dictionary_staging (feature-flagged path)
    maintenance_scanner.py     ← deletes old processed pipeline_events rows
  jobs/
    ocr_job.py                 ← downloads PDF, OCRs pages via Gemini Vision (google-genai)
    chunking_job.py            ← splits page text into chunks, upserts into the chunks table
    embedding_job.py           ← generates and stores chunk embeddings (google-genai)
    spell_check_job.py         ← identifies unknown words and suggests corrections
    auto_correct_job.py        ← applies auto-correction rules to open spell issues
    summary_job.py             ← generates a semantic book summary + embedding for RAG routing
    knowledge_graph_job.py     ← extracts entities/relationships and indexes them in Neo4j
    graph_resolution_job.py    ← resolves/merges duplicate graph entities against Neo4j fuzzy-match candidates
    history_extraction_job.py  ← extracts/stages Uyghur history-dictionary candidate terms from a book's pages (admin-triggered only, see below)
    rag_eval_job.py            ← post-turn async judge scoring for rag_evaluations (not a pipeline/cron job)
  worker.py                    ← ARQ WorkerSettings: registers the 10 jobs and 15 of the 16 scanners as cron jobs
```

**Job and scanner count:** 10 job functions are registered in `WorkerSettings.functions` (`ocr_job`, `chunking_job`, `embedding_job`, `spell_check_job`, `summary_job`, `auto_correct_job`, `knowledge_graph_job`, `graph_resolution_job`, `rag_eval_job`, `extract_book_history_terms_task`). 16 scanner modules exist under `services/worker/scanners/` (including the three batch-API poller scanners and `graph_resolution_scanner.py`), but only **15** are wired into `WorkerSettings.cron_jobs` in `worker.py` — `graph_scanner.py` is fully implemented and tested but is **not currently scheduled** (see [Cron Schedule](#cron-schedule)).

Batch OCR/embedding/history-extraction submission itself is **not** a separate ARQ job — it happens inline inside `ocr_job.py`, `embedding_scanner.py`, and `history_extraction_job.py` respectively, gated by the feature flags above (see [OCR_DESIGN.md](OCR_DESIGN.md#data-flow) and [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md#data-flow)).

## Component Responsibilities

### GcsDiscoveryScanner

See [DOCUMENT_DISCOVERY_DESIGN.md](DOCUMENT_DISCOVERY_DESIGN.md) for the full document discovery algorithm.

`PipelineDriver` picks up the new pages on its next run and initializes them into `ocr / idle`.

### PipelineDriver

The core state-machine bookkeeper. On every run:

1. **Initialize** — for pages with `ocr_milestone = 'idle'` on non-terminal books, ensures `pipeline_step` starts at `'ocr'`.
2. **Reset** — for any page where a step milestone is `failed`/`error` and `retry_count < ocr_max_retry_count`, resets that milestone back to `idle` so the owning scanner retries it. `retry_count` is **not** reset here — it keeps accumulating across steps until the page either succeeds or hits the max.
3. **Book ready / error** — for every book where **all** of its pages are terminal (each page's `embedding_milestone = 'succeeded'`, OR one of its mandatory steps failed with `retry_count >= ocr_max_retry_count`):
   - If **zero** pages on the book have an exhausted mandatory-step failure → book is marked `status='ready'`, `pipeline_step='ready'`.
   - If **any** page on the book has an exhausted mandatory-step failure → the whole book is marked `status='error'`, `pipeline_step='failed'`.

   In practice this rarely blocks a book: `ocr_job` treats an exhausted per-page OCR failure as a **soft skip** — it marks that page `ocr_milestone='succeeded'` with empty text rather than `'failed'` (see [OCR_DESIGN.md](OCR_DESIGN.md) for `OcrJob`'s full algorithm), so it flows through chunking/embedding as an empty, harmless page instead of ever counting as an exhausted mandatory failure. A book only lands in `status='error'` if `chunking_job` or `embedding_job` itself exhausts retries on a page, or if the OCR job can't even download the book's PDF.

4. `book.status='error'` removes the book from `chunking_scanner`/`embedding_scanner` eligibility (both explicitly exclude `Book.status == 'error'`) until an admin action resets it: either a pipeline recovery action (`/retry-failed`, a step reprocess, etc.) back to `pending`, or — unconditionally, without reprocessing anything — an editor setting the book's `visibility` to `public` via `PUT /books/{book_id}` (`update_book_details` in `books_router.py`), which clears it straight to `status='ready'`, `pipeline_step='ready'` on the assumption that publishing an errored book is an explicit signal it's actually usable. `scripts/retrofit_public_book_status.py` applies this same override retroactively to books that were already public before this behavior existed.
5. For books newly transitioning to `ready` (and that don't already have a `book_summaries` row, to avoid re-enqueuing during unrelated spell-check updates), enqueues `summary_job`. It does **not** enqueue `knowledge_graph_job` — graph generation is picked up separately by `graph_scanner` (currently unscheduled — see below) or triggered manually via the admin "Reprocess Graph" action.

### OcrScanner / ChunkingScanner / EmbeddingScanner / SpellCheckScanner

Each claims idle pages atomically (`SELECT ... FOR UPDATE SKIP LOCKED`, or an atomic `UPDATE` for OCR), flips the milestone to `in_progress`, and dispatches a job.

- See [OCR_DESIGN.md](OCR_DESIGN.md) for the full OCR algorithm (`OcrScanner`).
- See [CHUNKING_DESIGN.md](CHUNKING_DESIGN.md) for the full chunking algorithm (`ChunkingScanner`).
- See [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md) for the full embedding algorithm (`EmbeddingScanner`).
- See [SPELLCHECK_DESIGN.md](SPELLCHECK_DESIGN.md) for the full spell-check algorithm (`SpellCheckScanner`).

### Jobs

- See [OCR_DESIGN.md](OCR_DESIGN.md) for the full OCR algorithm (`OcrJob`).
- See [CHUNKING_DESIGN.md](CHUNKING_DESIGN.md) for the full chunking algorithm (`ChunkingJob`).
- See [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md) for the full embedding algorithm (`EmbeddingJob`).
- See [SPELLCHECK_DESIGN.md](SPELLCHECK_DESIGN.md) for the full spellcheck/auto-correct algorithm (`SpellCheckJob`, `AutoCorrectJob`).
- See [SUMMARY_DESIGN.md](SUMMARY_DESIGN.md) for the full summary algorithm (`SummaryJob`).
- See [KNOWLEDGE_GRAPH_DESIGN.md](KNOWLEDGE_GRAPH_DESIGN.md) for the full knowledge-graph extraction algorithm (`KnowledgeGraphJob`) and the entity-resolution sub-pipeline (`graph_resolution_scanner` / `GraphResolutionJob`).
- `history_extraction_job` (function `extract_book_history_terms_task`) — see [HistoryExtractionJob](#historyextractionjob--batchhistorypollerscanner) below; no dedicated design doc yet.
- See [CHAT_RAG_DESIGN.md](CHAT_RAG_DESIGN.md) for `rag_eval_job` — post-turn async judge scoring, not a pipeline/cron job.

### StaleWatchdog

Recovers pages (and books) stuck `in_progress` after a worker crash or restart. Unlike a flat timeout, it cross-references active worker heartbeats in Redis (`worker:heartbeat:*`) to reset stuck work faster when the owning worker is confirmed dead:

```
For every page with any milestone == 'in_progress':
  - No worker_id recorded, or worker_id == 'unknown':
      stale if claimed_at is older than 30 minutes (or missing)
  - worker_id has no active heartbeat key in Redis (worker is dead):
      stale if claimed_at is older than 2 minutes
  - worker_id has an active heartbeat (worker is alive, just slow):
      stale if claimed_at is older than 30 minutes

For each stale page: reset the in_progress milestone(s) back to idle
(including the legacy singular `milestone` column, kept in sync for
backward compatibility), clear worker_id/claimed_at, and recompute the
book's rolled-up milestones.

Separately: any book with graph_milestone='in_progress' for more than
1 hour is reset to graph_milestone='idle' so graph_scanner (or a manual
retry) can pick it up again.
```

### EventDispatcher

Polls up to 100 unprocessed rows from `pipeline_events` (`FOR UPDATE SKIP LOCKED`) per run and reacts immediately, rather than waiting for the next per-step scanner tick:

| Event | Action |
|---|---|
| `ocr_succeeded` | If `spell_check_enabled` is `"false"`: atomically claim the page (idle → in_progress) and enqueue `chunking_job` for it |
| `spell_check_succeeded` / `spell_check_failed` | If `spell_check_enabled` is `"true"`: atomically claim the page and enqueue `chunking_job` for it (mirrors `chunking_scanner`'s gating — chunking must wait for spell check to finish either way) |
| `chunking_succeeded` | Atomically claim the page and enqueue `embedding_job` for it |
| `embedding_succeeded`, `ocr_failed`, `chunking_failed`, `embedding_failed`, `auto_correct_succeeded`, `auto_correct_failed`, and the trigger type not selected by the `spell_check_enabled` branch above | No-op — just marked `processed=true`. Book-ready detection is handled separately by `PipelineDriver` on its own schedule |

The "claim" step re-checks that the target milestone is still `idle` (`SKIP LOCKED`) before dispatching, mirroring the `*_scanner` claim pattern — this prevents the reactive dispatch and the next per-step scanner poll from both enqueuing a job for the same page. Processed events are marked `processed=true`; `MaintenanceScanner` deletes them later.

### MaintenanceScanner

Deletes `pipeline_events` rows where `processed=true` and `created_at` is older than `sys_maintenance_retention_days` (system_configs, default 7).

### AutoCorrectScanner

See [SPELLCHECK_DESIGN.md](SPELLCHECK_DESIGN.md) for the full auto-correct algorithm.

### HistoryExtractionJob / BatchHistoryPollerScanner

Unlike every other job described above, `history_extraction_job` has **no scanner that claims idle work for it** — it is admin-triggered only. `POST /api/admin/books/{book_id}/extract-history` (admin-only, `admin_history_dictionary_router.py`) enqueues the job directly with a `min_significance` threshold; it 400s if `history_extraction_enabled` isn't `"true"`.

The job either:
- runs Gemini extraction inline over the book's pages in sliding windows of `history_batch_size` pages (default 15, `history_gemini_model` default `gemini-2.5-flash`) and stages candidate terms + facts into `history_dictionary_staging`, or
- when `history_batch_enabled` is `"true"`, submits a row to `batch_history_extraction_jobs` via the Gemini Batch API instead (mirrors the OCR/embedding batch-mode pattern).

`batch_history_poller_scanner` (every 1 min) polls in-flight `batch_history_extraction_jobs` and ingests completed results the same way `batch_ocr_poller_scanner`/`batch_embedding_poller_scanner` do for their stages — but note there is currently no timeout config analogous to `ocr_batch_timeout_hours`/`embed_batch_timeout_hours` for stuck batch history jobs. Staged candidates are reviewed and approved/rejected by an admin via the `/history-dictionary/staging` endpoints before publishing to the live `history_dictionary` table.

## Cron Schedule

Authoritative source: `WorkerSettings.cron_jobs` in `services/worker/worker.py`.

| Scanner | Interval | Notes |
|---|---|---|
| `gcs_discovery_scanner` | Every 5 min | List GCS bucket, register new books |
| `pipeline_driver` | Every 1 min (+ at startup) | Initialize, reset retryable failures, mark ready/error, enqueue summary jobs |
| `ocr_scanner` | Every 1 min | Groups claimed pages by book |
| `batch_ocr_poller_scanner` | Every 1 min | Polls in-flight `batch_ocr_jobs` (no-op unless `ocr_batch_enabled` has been used) |
| `chunking_scanner` | Every 1 min | Cross-book |
| `embedding_scanner` | Every 1 min | Cross-book |
| `batch_embedding_poller_scanner` | Every 1 min | Polls in-flight `batch_embedding_jobs` (no-op unless `embed_batch_enabled` has been used) |
| `spell_check_scanner` | Every 1 min | Cross-book; no-op unless `spell_check_enabled` |
| `batch_history_poller_scanner` | Every 1 min | Polls in-flight `batch_history_extraction_jobs` (no-op unless `history_batch_enabled` has been used) |
| `event_dispatcher` | Every 1 min (+ at startup) | Reactive low-latency progression via the outbox |
| `stale_watchdog` | Minute 0 and 30 (i.e. every 30 min) | Worker-heartbeat-aware reset |
| `summary_scanner` | Every 5 min | Backfill/retry missing book summaries |
| `graph_resolution_scanner` | Every 5 min | Claims `graph_resolution_queue` rows, dispatches one `graph_resolution_job` per scope; no-op unless `kg_enabled` |
| `auto_correct_scanner` | Daily at 3:00 AM | Loops through all eligible pages in batches |
| `maintenance_scanner` | Daily at 3:00 AM | Deletes old processed outbox events |

**`graph_scanner` is not in this list.** The module (`services/worker/scanners/graph_scanner.py`) and its unit tests exist, and `worker.py`'s own module docstring claims it runs every 5 minutes, but it is never imported or added to `cron_jobs`. With `kg_enabled` also defaulting to `false`, knowledge-graph generation today only runs via the manual admin "Reprocess Graph" action (`POST /api/books/{book_id}/reprocess/graph`), which enqueues `knowledge_graph_job` directly.

## State Machine

```mermaid
flowchart TD
    OCR_IDLE["ocr / idle"]
    OCR_IP["ocr / in_progress"]
    OCR_OK["ocr / succeeded<br/>(incl. soft-skipped empty pages)"]
    OCR_FAIL["ocr / failed<br/>(PDF download failure, or a per-page<br/>Gemini OCR error before retries exhausted)"]
    CHUNK_IDLE["chunking / idle"]
    CHUNK_IP["chunking / in_progress"]
    CHUNK_OK["chunking / succeeded"]
    CHUNK_FAIL["chunking / failed"]
    EMB_IDLE["embedding / idle"]
    EMB_IP["embedding / in_progress"]
    EMB_OK["embedding / succeeded"]
    EMB_FAIL["embedding / failed"]
    SPELL_IDLE["spell_check / idle<br/>(independent quality layer)"]
    SPELL_IP["spell_check / in_progress"]
    SPELL_OK["spell_check / succeeded"]
    SPELL_FAIL["spell_check / failed"]
    EXHAUSTED["ocr/chunking/embedding failed<br/>retry_count >= max<br/>(book-wide status=error;<br/>OCR only lands here via repeated<br/>PDF download failures — a per-page<br/>Gemini OCR error always soft-skips<br/>to OCR_OK at exhaustion instead)"]
    HISTORY_NOTE["history_extraction_job<br/>(admin-triggered only — POST /api/admin/books/{id}/extract-history)<br/>Uses batch_history_extraction_jobs /<br/>history_dictionary_staging / history_dictionary.<br/>NOT part of this milestone state machine —<br/>no page/book milestone column involved.<br/>See HistoryExtractionJob section above."]

    OCR_IDLE -->|OcrScanner: claim| OCR_IP
    OCR_IP -->|"Gemini call succeeds, or retries exhausted (soft-skip)"| OCR_OK
    OCR_IP -->|PDF download failed| OCR_FAIL
    OCR_FAIL -->|retry_count < max: PipelineDriver reset| OCR_IDLE
    OCR_FAIL -->|retry_count >= max| EXHAUSTED
    OCR_OK -->|ChunkingScanner: dep satisfied| CHUNK_IDLE
    OCR_OK -.->|SpellCheckScanner: dep satisfied| SPELL_IDLE

    CHUNK_IDLE -->|ChunkingScanner: claim| CHUNK_IP
    CHUNK_IP -->|ChunkingJob: success| CHUNK_OK
    CHUNK_IP -->|ChunkingJob: failure| CHUNK_FAIL
    CHUNK_FAIL -->|retry_count < max: PipelineDriver reset| CHUNK_IDLE
    CHUNK_FAIL -->|retry_count >= max| EXHAUSTED
    CHUNK_OK -->|EmbeddingScanner: dep satisfied| EMB_IDLE

    EMB_IDLE -->|EmbeddingScanner: claim| EMB_IP
    EMB_IP -->|EmbeddingJob: success| EMB_OK
    EMB_IP -->|EmbeddingJob: failure| EMB_FAIL
    EMB_FAIL -->|retry_count < max: PipelineDriver reset| EMB_IDLE
    EMB_FAIL -->|retry_count >= max| EXHAUSTED
    EMB_OK -->|"PipelineDriver: ALL pages on book terminal, zero exhausted"| BookReady(["book.status = ready"])
    EXHAUSTED -->|"PipelineDriver: ANY page on book exhausted"| BookError(["book.status = error"])

    BookReady -->|Enqueue| SummaryJob["summary_job<br/>(auto, once per book)"]
    BookReady -.->|"graph_milestone reset to idle;<br/>manual trigger or (if scheduled) graph_scanner"| KGJob["knowledge_graph_job<br/>(feature-flagged, off by default)"]

    SPELL_IDLE -->|SpellCheckScanner: claim| SPELL_IP
    SPELL_IP -->|SpellCheckJob: success| SPELL_OK
    SPELL_IP -->|SpellCheckJob: failure| SPELL_FAIL
    SPELL_FAIL -->|retry_count < max: PipelineDriver reset| SPELL_IDLE
    SPELL_FAIL -->|retry_count >= max| SPELL_TERMINAL["spell_check permanently failed<br/>(does not affect book status)"]

    classDef idle fill:#e9edc9,stroke:#606c38
    classDef active fill:#fff3cd,stroke:#856404
    classDef done fill:#d4f1f4,stroke:#189ab4
    classDef fail fill:#ffcccb,stroke:#d32f2f
    classDef terminal fill:#f1f1f1,stroke:#888,stroke-dasharray:4 4
    classDef book fill:#d4f1f4,stroke:#189ab4,stroke-width:2px
    classDef bookErr fill:#ffcccb,stroke:#d32f2f,stroke-width:2px
    classDef note fill:#f5f5f5,stroke:#999,stroke-dasharray:2 2

    class OCR_IDLE,CHUNK_IDLE,EMB_IDLE,SPELL_IDLE idle
    class OCR_IP,CHUNK_IP,EMB_IP,SPELL_IP active
    class OCR_OK,CHUNK_OK,EMB_OK,SPELL_OK done
    class OCR_FAIL,CHUNK_FAIL,EMB_FAIL,SPELL_FAIL fail
    class EXHAUSTED,SPELL_TERMINAL terminal
    class BookReady book
    class BookError bookErr
    class HISTORY_NOTE note
```

## Retry Logic

`retry_count` is a single counter per page, shared across all four steps.

| Scenario | Behavior |
|---|---|
| A step's job sets `milestone = failed` | `retry_count++` |
| `PipelineDriver` finds `milestone = failed AND retry_count < max` | Resets that milestone to `idle` — the owning scanner retries it |
| `PipelineDriver` finds `milestone = failed AND retry_count >= max` | Leaves it `failed`; if the exhausted step is a mandatory one (OCR/chunking/embedding), the whole book is marked `status='error'` |
| `StaleWatchdog` fires | Resets `in_progress → idle` without incrementing `retry_count` (a timeout is not a failure) |

`ocr_max_retry_count` (system_configs, default `10`) is the pipeline-level retry budget used by all four steps. It is distinct from `OCR_MAX_RETRIES` (env var, default `4`), which only bounds the inner transient-error retry loop of a single Gemini Vision call inside `ocr_service`, before that call is even counted as one pipeline-level failure.

## Configuration Reference

All batch sizes, concurrency limits, and model names below are `system_configs` values (hot-reloadable without a deploy) unless marked "env" (`packages/backend-core/app/core/config.py`, requires a restart to change).

| Key | Default | Used by |
|---|---|---|
| `ocr_max_retry_count` | `10` | All scanners/`PipelineDriver` — pipeline-level retry budget |
| `ocr_max_parallel_pages` | `1` | `ocr_job` — pages OCR'd concurrently within one job |
| `ocr_scanner_batch_size` | `10` | `ocr_scanner` — pages claimed per book per run |
| `scanner_book_limit` | `10` | `ocr_scanner` — books dispatched per run |
| `scanner_page_limit` | `100` | `chunking_scanner` / `embedding_scanner` / `spell_check_scanner` — pages claimed per run |
| `ocr_gemini_timeout` | `300` (sec) | `ocr_job` — per-page Gemini Vision call timeout |
| `auto_correct_batch_size` | `500` | `auto_correct_scanner` — pages per dispatched batch |
| `summary_scanner_batch_size` | `5` | `summary_scanner` — books backfilled per run |
| `kg_scanner_batch_size` | `5` | `graph_scanner` — books backfilled per run (scanner currently unscheduled) |
| `resolution_batch_size` | `20` | `graph_resolution_scanner` — `graph_resolution_queue` rows claimed per run |
| `kg_chunk_batch_size` | `5` | `knowledge_graph_job` — chunks combined per LLM call |
| `kg_max_parallel_chunks` | `5` | `knowledge_graph_job` — concurrent batch LLM calls |
| `sys_maintenance_retention_days` | `7` | `maintenance_scanner` — processed-event retention |
| `ocr_batch_enabled` | `false` | `ocr_job` — routes OCR through the Gemini Batch API instead of inline |
| `ocr_batch_size_per_job` | `50` | `ocr_job` — pages per submitted batch-OCR sub-job |
| `embed_batch_enabled` | `false` | `embedding_scanner` — routes embedding through the Gemini Batch API instead of `embedding_job` |
| `embed_batch_max_chunks_per_job` | `100` | `batch_embedding_service` — chunks per submitted batch-embedding sub-job |
| `ocr_batch_timeout_hours` / `embed_batch_timeout_hours` | `24` | Poller scanners — wall-clock timeout before marking a stuck batch job's pages failed |
| `embed_batch_max_retry_count` | `3` | `batch_embedding_service` (poller scanner) — per-chunk retry budget before giving up. Batch OCR has no equivalent dedicated key — `batch_ocr_service` reuses `ocr_max_retry_count` (default `10`) as its per-page retry budget instead |
| `history_extraction_enabled` | `true` | `history_extraction_job` — pipeline-level feature flag; also gates `POST /api/admin/books/{book_id}/extract-history` |
| `history_gemini_model` | `gemini-2.5-flash` | `history_extraction_job` / `batch_history_extraction_service` — Gemini model used for term extraction and factual synthesis |
| `history_batch_size` | `15` | `history_extraction_service` / `batch_history_extraction_service` — pages per sliding-window/batch extraction request |
| `history_batch_enabled` | `false` | `history_extraction_job` — routes extraction through the Gemini Batch API instead of inline; unlike batch OCR/embedding, there is no dedicated `*_timeout_hours` or `*_max_retry_count` key for stuck batch history jobs |
| `MAX_PARALLEL_SPELL_CHECK` (env) | `6` | `spell_check_job` — pages spell-checked concurrently |
| `MAX_CONCURRENT_SPELL_CHECK_BOOKS` (env) | `3` | `spell_check_scanner` — books actively spell-checked at once |
| `MAX_PARALLEL_AUTO_CORRECT` (env) | `10` | `auto_correct_job` — pages corrected concurrently |
| `EMBED_BATCH_SIZE` (env) | `50` | `embedding_job` — chunks per embedding API call |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` (env) | `1500` / `300` | `chunking_service` — recursive character splitter |
| `OCR_PAGE_ZOOM_FACTOR` (env) | `1.5` | `ocr_job` — PDF page render resolution |
| `OCR_MAX_RETRIES` (env) | `4` | `ocr_service` — inner transient-error retry loop per Gemini call |

Note: `.env.template` also defines `MAX_PARALLEL_PAGES=6`, but no setting in `config.py` reads that variable — OCR page concurrency is actually controlled by the `ocr_max_parallel_pages` system_config above (default `1`). Treat `MAX_PARALLEL_PAGES` in the env template as unused.
