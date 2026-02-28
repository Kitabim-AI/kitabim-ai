# Book Management Reference

## Overview

A book moves through a multi-stage pipeline from upload to fully searchable:

1. **Upload** → PDF stored in GCS, book record created (`pending`)
2. **OCR** → Worker reads each page as an image and extracts text via Gemini (`ocr_processing` → `ocr_done`)
3. **Chunking** → Background cron splits page text into overlapping chunks (`ocr_done` → `chunked`)
4. **Embedding** → Background cron generates 768-dim vectors for each chunk in realtime (`chunked` → `indexed`)
5. **Ready** → Book is fully searchable via RAG (`ready`)

All five stages are tracked at both the book level (`status`) and page level (`page.status`). OCR and embedding are protected by circuit breakers — if Gemini returns repeated errors, the breakers open and processing pauses until the service recovers.

---

## Book Status Values

| Status | Description |
|---|---|
| `pending` | Book record created, waiting for OCR to be triggered |
| `ocr_processing` | OCR (and/or re-embedding) job is actively running in the worker |
| `ocr_done` | All pages have been OCR'd; embeddings/indexing not yet done |
| `indexing` | Embedding and chunk indexing is in progress |
| `ready` | Fully processed and indexed; available to readers |
| `error` | Processing failed at some stage |

### The `processing_step` Field
Alongside `status`, the database tracks the specific sub-stage via `processing_step`. Two values are used: `ocr` (set when OCR begins via start-ocr or retry-ocr) and `rag` (set when reindexing begins). This gives the UI fine-grained progress indicators during the `ocr_processing` status phase.

### Status Transition Flow

```
                    ┌─────────┐
                    │ pending │  ◄─── Start OCR triggers from here only
                    └────┬────┘
                         │ Start OCR
                         ▼
               ┌──────────────────┐
               │  ocr_processing  │  ◄─── Retry OCR / Reindex / Reset Page land here
               └──────┬─────┬─────┘
                      │     │
            all done  │     │ failure
                      ▼     ▼
                  ┌──────────┐   ┌───────┐
                  │ ocr_done │   │ error │
                  └────┬─────┘   └───┬───┘
                       │              │
                       │              ├─ Retry OCR ──► ocr_processing
                       │              └─ Force Complete ──► ocr_done or ready
                       │                 (detected from surviving page states)
                       │ indexing starts
                       ▼
                  ┌──────────┐
                  │ indexing │
                  └────┬──┬──┘
                       │  │ unindexed ocr_done pages remain
                       │  └─ Force Complete ──► ocr_done
                       │ all indexed (or indexed + error == total_pages)
                       ▼
                  ┌─────────┐
                  │  ready  │  ◄─── Reindex available from here (and ocr_done)
                  └─────────┘
```

---

## Status Recovery Reference

| Status | Success — Next Step | Failure — Recovery Method |
|---|---|---|
| `pending` | Admin clicks **Start OCR** → `ocr_processing` | Watchdog auto-rescues after 30 min; or manually click **Start OCR** |
| `ocr_processing` (active) | All pages OCR'd → `ocr_done` | Wait; pages that keep failing auto-skip at `ocr_max_retry_count` |
| `ocr_processing` (stale lock) | — | **Retry OCR** resets stuck/error pages → `pending` and re-queues; or **Force Complete** promotes remaining pages → `ocr_done` |
| `ocr_done` | Cron (interval configurable via `batch_submission_interval_minutes`, default 15 min) chunks pages → embeds → `ready` | **Reindex** to re-chunk and re-embed all pages from scratch |
| `indexing` (active) | All chunks embedded → `ready` | Wait for finalization cron to promote book |
| `indexing` (stale lock) | — | **Force Complete** → `ready` (if no unindexed `ocr_done` pages remain) or → `ocr_done` (if unindexed pages still exist, cron picks up next cycle) |
| `error` | — | **Retry OCR** if pages are in `error`/`ocr_processing`; **Force Complete** to advance with what survived; last resort: **Reindex** after force-complete |
| `ready` | Terminal success — searchable | **Reindex** to refresh embeddings (e.g. after chunking strategy change) |

> **Key automatic recoveries (no admin action needed):**
> - Pages that fail OCR repeatedly auto-skip at `retry_count >= ocr_max_retry_count` (system config, default `10`)
> - Stale books in `pending`, `ocr_done`, `ocr_processing`, or `indexing` are auto-rescued by the watchdog every 30 min
> - `finalize_indexed_pages` promotes books to `ready` automatically on every polling cron tick

---

## Real-time vs. Batch Processing

All OCR and indexing processing runs synchronously (realtime) — there is no Gemini Batch API in use.

1. **OCR (realtime)**
   - When a book is enqueued for OCR, the ARQ worker picks up the job and `pdf_service` processes each page synchronously via Gemini, one at a time.
   - Each page transitions `pending` → `ocr_processing` → `ocr_done` (or `error` on failure).

2. **Chunking (background cron)**
   - `gemini_batch_submission_cron` runs every minute but early-exits based on `batch_submission_interval_minutes` (default 15 min) to avoid redundant runs.
   - When it fires, `chunk_ocr_done_pages()` sweeps all `ocr_done` pages, splits their text into overlapping chunks, and saves those chunks with NULL embeddings. Pages move to `chunked`.

3. **Embedding (realtime, same cron run)**
   - Immediately after chunking, the same cron run calls `embed_pending_chunks_realtime()`, which fetches all chunks with NULL embeddings and generates 768-dim vectors synchronously in batches of 20.

4. **Finalization (every minute)**
   - `gemini_batch_polling_cron` runs every minute and calls `finalize_indexed_pages()`.
   - `chunked` pages whose chunks are all embedded are promoted to `indexed`.
   - A book is promoted to `ready` when `indexed_count + error_count == total_pages` — books with some error pages can still reach `ready`.

### Cron Schedule

| Job | Schedule | Description |
|---|---|---|
| `rescue_stale_jobs` | At startup + every 30 min | Finds stale `ocr_processing`/`pending`/`ocr_done`/`indexing` books and re-enqueues them |
| `scheduled_gcs_sync` | Every 30 min | Scans GCS bucket for new PDFs not yet in the DB |
| `gemini_batch_submission_cron` | Every minute (early-exits by `batch_submission_interval_minutes`) | Chunks `ocr_done` pages; embeds pending chunks in realtime |
| `gemini_batch_polling_cron` | Every minute | Finalizes page/book statuses; promotes books to `ready` |

---

## Circuit Breakers

Two circuit breakers protect all Gemini API calls: `llm_generate` (text/OCR) and `llm_embed` (embeddings). Both share the same configuration:

| Parameter | Env var | Default | Description |
|---|---|---|---|
| `failure_threshold` | `LLM_CB_FAILURE_THRESHOLD` | `10` | Consecutive failures before breaker opens |
| `recovery_timeout` | `LLM_CB_RECOVERY_SECONDS` | `60` | Seconds to wait before allowing a trial call (half-open) |
| `half_open_max_calls` | `LLM_CB_HALF_OPEN_MAX_CALLS` | `1` | Trial calls allowed in half-open state |
| `cooling_period` | `LLM_CB_COOLING_PERIOD` | `60` | Grace period after process restart before failures are counted |

**When a breaker is open:**
- All Gemini calls immediately raise `CircuitBreakerOpen` (no wait, no retry)
- The batch submission cron skips entirely
- RAG/chat responses fall back to no-context mode
- The breaker auto-recovers after `recovery_timeout` seconds (half-open → single trial call → closed if successful)

**Admin endpoints** (`/api/system-configs/circuit-breaker/`):

| Action | Method | Endpoint | Auth |
|---|---|---|---|
| Check status | `GET` | `/api/system-configs/circuit-breaker/status` | editor |
| Reset (force close) | `POST` | `/api/system-configs/circuit-breaker/reset` | admin |
| Force open | `POST` | `/api/system-configs/circuit-breaker/open` | admin |

---

## Page Status Values

| Status | Description |
|---|---|
| `pending` | Waiting to be OCR'd |
| `ocr_processing` | OCR running for this page |
| `ocr_done` | Raw text extracted, not yet chunked |
| `chunked` | Text split into chunks, not yet embedded |
| `indexing` | Embeddings being generated |
| `indexed` | Fully embedded and searchable |
| `error` | This page failed OCR or indexing |

### Page Retry Count

Each page tracks a `retry_count` field. When OCR fails (exception or empty text), `retry_count` is incremented. Once it reaches `ocr_max_retry_count` (system config, default `10`), the page is automatically skipped instead of re-queued as `error`:

- **OCR exception path** (`pdf_service`): on max retry → page set to `ocr_done` with empty text
- **Empty text path** (`batch_service`): on max retry → page set to `indexed` with `is_indexed=true` (no chunk created)

This prevents a permanently-failing page from blocking the entire book indefinitely. The `ocr_max_retry_count` value is configurable via the System Configs admin API.

### Page Status Recovery Reference

| Status | Success — Next Step | Failure — Recovery Method |
|---|---|---|
| `pending` | Worker picks up → `ocr_processing` | Auto-retried by worker; manually **Reset Page** |
| `ocr_processing` | OCR completes → `ocr_done` | `retry_count` incremented; auto-skip at max retry; **Reset Page** to re-queue |
| `ocr_done` | Batch cron chunks text → `chunked` | **Edit Text** to manually correct; **Reindex** book to re-run chunking |
| `chunked` | Batch cron embeds → `indexed` | **Reindex** book to re-chunk and re-embed from scratch |
| `indexing` | Embedding completes → `indexed` | **Force Complete** on book; or **Reindex** book |
| `indexed` | Terminal — embedded and searchable | **Edit Text** to correct and re-embed; **Reset Page** to re-OCR |
| `error` | — | **Reset Page** (re-queues OCR); **Edit Text** if partial text exists |

### Page Action Button State

All page actions require **editor** role. The frontend shows the three buttons on hover for any page status — the backend does not restrict calls by page status. The table below indicates when each action is *meaningful*.

| Page Status | Reset Page | Edit Text | Spell Check | Apply Corrections |
|---|---|---|---|---|
| `pending` | enabled | not useful (empty text) | not useful | not useful |
| `ocr_processing` | enabled | not useful (empty text) | not useful | not useful |
| `ocr_done` | enabled | **primary use** | **primary use** | after spell check |
| `chunked` | enabled | **primary use** | **primary use** | after spell check |
| `indexing` | enabled | **primary use** | **primary use** | after spell check |
| `indexed` | enabled | **primary use** | **primary use** | after spell check |
| `error` | **primary use** | enabled if partial text | enabled if partial text | after spell check |

> **Reset Page** maps to `POST /api/books/{id}/pages/{n}/reset` — clears text, sets page to `pending`, and immediately re-queues it for real-time OCR (`force_realtime=true`). This is the Reprocess (↺) button in the reader UI.

---

## Admin Action Buttons

### Enable / Disable Rules

Evaluated in [ActionMenu.tsx](../apps/frontend/src/components/admin/ActionMenu.tsx).

```
isStale              = (status is ocr_processing OR indexing)
                       AND processingLockExpiresAt is in the past

isActuallyProcessing = (status is ocr_processing OR indexing)
                       AND NOT isStale

hasFailedPages       = errorCount > 0 OR any page.status === 'error'

canView              = status !== 'pending'

canStartOcr          = status === 'pending'

canRetry             = (hasFailedPages OR status === 'error' OR isStale)
                       AND NOT isActuallyProcessing

canReindex           = status === 'ready' OR status === 'ocr_done'

canForceComplete     = isEditorOrAdmin
                       AND (isStale OR status === 'ocr_processing'
                            OR status === 'indexing' OR status === 'error')
```

### Button State by Status

| Book Status | View | Start OCR | Retry OCR | Reindex | Force Complete | Delete |
|---|---|---|---|---|---|---|
| `pending` | disabled | **enabled** | disabled | disabled | disabled | enabled |
| `ocr_processing` (active) | enabled | disabled | disabled | disabled | **enabled** (editor+) | enabled |
| `ocr_processing` (stale lock) | enabled | disabled | **enabled** | disabled | **enabled** (editor+) | enabled |
| `ocr_done` | enabled | disabled | disabled | **enabled** | disabled | enabled |
| `indexing` (active) | enabled | disabled | disabled | disabled | **enabled** (editor+) | enabled |
| `indexing` (stale lock) | enabled | disabled | **enabled** | disabled | **enabled** (editor+) | enabled |
| `ready` | enabled | disabled | disabled | **enabled** | disabled | enabled |
| `error` | enabled | disabled | **enabled** | disabled | **enabled** (editor+) | enabled |
| `error` + failed pages | enabled | disabled | **enabled** | disabled | **enabled** (editor+) | enabled |

> **Stale detection**: A job is considered stale when the book is in `ocr_processing` or `indexing`
> and `processingLockExpiresAt` is in the past. This unlocks Retry OCR and Force Complete so
> admins can recover stuck books without backend intervention.

---

## Action Metrics

Each action's trigger conditions, what it changes, and what state the book/pages end up in.

### Start OCR — `POST /api/books/{id}/start-ocr`

| | Detail |
|---|---|
| **Enabled when** | `status === 'pending'` |
| **Book status → after** | `ocr_processing` |
| **processing_step → after** | `ocr` |
| **Lock cleared** | Yes (`processing_lock = null`, `processing_lock_expires_at = null`) |
| **Pages changed** | Worker deletes existing pages on first run and creates fresh `pending` pages |
| **Worker enqueued** | Yes (`start_ocr`) |

---

### Retry OCR — `POST /api/books/{id}/retry-ocr`

| | Detail |
|---|---|
| **Enabled when** | `hasFailedPages OR status === 'error' OR isStale` AND not actively processing |
| **Book status → after** | `ocr_processing` |
| **processing_step → after** | `ocr` |
| **Lock cleared** | Yes (`processing_lock = null`, `processing_lock_expires_at = null`) |
| **Pages changed** | Pages with `status IN ('error', 'ocr_processing')` → reset to `pending` (text cleared, is_indexed=false) |
| **Special case** | If `status === 'error'` and no stuck/failed pages → re-enqueues as-is (`resumed`) |
| **Worker enqueued** | Yes (`retry_failed` or `resume_error`) |

> **Note on permanently-failing pages**: If a page consistently fails OCR, its `retry_count`
> is incremented each attempt. Once `retry_count >= ocr_max_retry_count`, the page is
> automatically skipped (set to `ocr_done` with empty text) rather than looping as `error`.
> This means Retry OCR will eventually self-resolve without admin intervention.

---

### Reindex — `POST /api/books/{id}/reindex`

| | Detail |
|---|---|
| **Enabled when** | `status === 'ready' OR status === 'ocr_done'` |
| **Book status → after** | `ocr_processing` |
| **processing_step → after** | `rag` |
| **Lock cleared** | Yes (`processing_lock = null`, `processing_lock_expires_at = null`) |
| **Pages changed** | All `ocr_done`, `chunked`, `indexed` pages → `ocr_done`, `is_indexed=false` |
| **Chunks** | All existing chunks deleted |
| **Worker enqueued** | Yes (`reindex`) — worker re-chunks and re-embeds all `ocr_done` pages |

---

### Force Complete — `POST /api/books/{id}/force-complete`

| | Detail |
|---|---|
| **Enabled when** | Editor/admin AND (`isStale OR status IN ('ocr_processing', 'indexing', 'error')`) |
| **Logic** | Backend detects the active stage from surviving page states and advances accordingly |
| **Lock cleared** | Always (`processing_lock = null`, `processing_lock_expires_at = null`) |

#### Force Complete — Outcome by Current Status

| Book Status | Page condition | Pages changed | Book status → after |
|---|---|---|---|
| `ocr_processing` | — | `ocr_processing` pages → `ocr_done` | `ocr_done` |
| `indexing` | — | `chunked` pages → `ocr_done` (embedding retries on next cycle) | `ocr_done` |
| `error` | has `ocr_processing` pages | `ocr_processing` pages → `ocr_done` | `ocr_done` |
| `error` | has `chunked` pages | `chunked` pages → `ocr_done` (embedding retries on next cycle) | `ocr_done` |
| `error` | has `ocr_done` pages only | none | `ocr_done` |
| `error` | has `indexed` pages only | none | `ready` |
| `error` | no surviving page states | none | `ocr_done` |

> When force-complete resolves to `ocr_done`, the normal indexing pipeline will pick up
> remaining `ocr_done` pages automatically on the next worker cycle.

> **Note on partial completion**: A book can reach `ready` even if some pages are in `error` status.
> `finalize_indexed_pages` promotes a book to `ready` when `indexed_count + error_count == total_pages`,
> meaning pages that permanently failed do not prevent the rest of the book from becoming searchable.

---

## API Endpoints

All write endpoints require **editor** role or above. Read endpoints are role-dependent as noted.

### Book Lifecycle

*Common Errors: API endpoints communicating directly with Gemini APIs may return `503 Service Unavailable` on high demand (triggering Circuit Breakers).*

| Action | Method | Endpoint | Auth | Book status after |
|---|---|---|---|---|
| Upload PDF | `POST` | `/api/books/upload` | editor | `pending` |
| Start OCR | `POST` | `/api/books/{id}/start-ocr` | editor | `ocr_processing` |
| Retry failed/stuck pages | `POST` | `/api/books/{id}/retry-ocr` | editor | `ocr_processing` |
| Force complete current stage | `POST` | `/api/books/{id}/force-complete` | editor+ | `ocr_done` or `ready` |
| Reindex embeddings | `POST` | `/api/books/{id}/reindex` | editor | `ocr_processing` → `ready` |
| Full reprocess (clears pages) | `POST` | `/api/books/{id}/reprocess` | editor | `ocr_processing` |
| Delete book | `DELETE` | `/api/books/{id}` | admin | — |

### Page-Level Operations

| Action | Method | Endpoint | Auth | Page status after |
|---|---|---|---|---|
| Reset single page | `POST` | `/api/books/{id}/pages/{n}/reset` | editor | `pending`, book → `ocr_processing` |
| Update page text manually | `POST` | `/api/books/{id}/pages/{n}/update` | editor | `ocr_done` → `indexed` (synchronous embed) |
| Spell-check page | `POST` | `/api/books/{id}/pages/{n}/spell-check` | editor | unchanged |
| Apply spell corrections | `POST` | `/api/books/{id}/pages/{n}/apply-corrections` | editor | unchanged |

### System Configuration

| Action | Method | Endpoint | Auth |
|---|---|---|---|
| List all system configs | `GET` | `/api/system-configs/` | admin |
| Get config value | `GET` | `/api/system-configs/{key}` | admin |
| Create config | `POST` | `/api/system-configs/` | admin |
| Update config | `PUT` | `/api/system-configs/{key}` | admin |

**Relevant config keys:**

| Key | Default | Description |
|---|---|---|
| `ocr_max_retry_count` | `10` | Max OCR attempts per page before auto-skip |
| `batch_chunking_limit` | `1000` | Max pages chunked per batch submission cron tick |
| `batch_embedding_limit` | `2000` | Max chunks embedded per batch submission cron tick |
| `batch_submission_interval_minutes` | `15` | Minutes between chunking + embedding runs. Lower = faster processing. |
| `batch_submission_last_run_at` | `0` | Unix timestamp of last submission cron run. Managed automatically. |

### Metadata

| Action | Method | Endpoint | Auth |
|---|---|---|---|
| Update title, author, volume, categories | `PUT` | `/api/books/{id}` | editor |
| Upload cover image | `POST` | `/api/books/upload-cover` | editor |
| Sync from GCS storage | `POST` | `/api/books/storage/sync` | admin |

### Read

| Action | Method | Endpoint | Auth |
|---|---|---|---|
| List books (paginated) | `GET` | `/api/books/` | optional (guests: public+ready only) |
| Get single book | `GET` | `/api/books/{id}` | optional |
| Get book by content hash | `GET` | `/api/books/hash/{hash}` | optional |
| Get all pages | `GET` | `/api/books/{id}/pages` | reader |
| Get single page | `GET` | `/api/books/{id}/pages/{n}` | reader |
| Get full text content | `GET` | `/api/books/{id}/content` | reader |
| Search suggestions | `GET` | `/api/books/suggest?q=` | optional |
| Top categories | `GET` | `/api/books/top-categories` | optional |
| Admin stats | `GET` | `/api/books/stats` | admin |

---

## Content Deduplication

During upload (`POST /api/books/upload`), the backend computes a SHA-256 hash of the incoming PDF file. Before creating a new book record, it checks for an existing book with the same hash:

- **Duplicate found** → returns `{"bookId": "<existing_id>", "status": "existing"}` immediately. No new record is created.
- **No duplicate** → proceeds with normal book creation.

The `content_hash` field is exposed on every book response and can be used to look up a book directly via `GET /api/books/hash/{hash}`.

---

## Book Read Count

The `read_count` field on every book tracks how many times `GET /api/books/{id}` has been called. It is:

- Incremented atomically via a background task on every single-book fetch (non-blocking, does not slow down the response)
- Returned in all book list and single book responses
- Indexed in the database for fast sorting by popularity

There is no API to manually set or reset `read_count`. It is read-only from the API perspective.
