# Book Management Reference

## Book Status Values

| Status | Description |
|---|---|
| `uploading` | File is being uploaded to storage — not yet persisted as a book record |
| `pending` | Book record created, waiting for OCR to be triggered |
| `ocr_processing` | OCR (and/or re-embedding) job is actively running in the worker |
| `ocr_done` | All pages have been OCR'd; embeddings/indexing not yet done |
| `indexing` | Embedding and chunk indexing is in progress |
| `ready` | Fully processed and indexed; available to readers |
| `error` | Processing failed at some stage |

### Status Transition Flow

```
                    ┌─────────┐
                    │uploading│  (transient, during file upload)
                    └────┬────┘
                         │ upload complete
                         ▼
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
                       │ all indexed
                       ▼
                  ┌─────────┐
                  │  ready  │  ◄─── Reindex available from here (and ocr_done)
                  └─────────┘
```

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

Each page tracks a `retry_count` field. When OCR fails (exception or empty text), `retry_count` is incremented. Once it reaches `ocr_max_retry_count` (system config, default `3`), the page is automatically skipped instead of re-queued as `error`:

- **OCR exception path** (`pdf_service`): on max retry → page set to `ocr_done` with empty text
- **Empty text path** (`batch_service`): on max retry → page set to `indexed` with `is_indexed=true` (no chunk created)

This prevents a permanently-failing page from blocking the entire book indefinitely. The `ocr_max_retry_count` value is configurable via the System Configs admin API.

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
| `uploading` | disabled | disabled | disabled | disabled | disabled | enabled |
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
| **Pages changed** | All existing pages deleted (if non-pending); worker creates fresh `pending` pages |
| **Worker enqueued** | Yes (`start_ocr`) |

---

### Retry OCR — `POST /api/books/{id}/retry-ocr`

| | Detail |
|---|---|
| **Enabled when** | `hasFailedPages OR status === 'error' OR isStale` AND not actively processing |
| **Book status → after** | `ocr_processing` |
| **processing_step → after** | `ocr` |
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
| `indexing` | no remaining `ocr_done` pages | `indexing` pages → `indexed` (is_indexed=true) | `ready` |
| `indexing` | `ocr_done` pages still unindexed | `indexing` pages → `indexed` (is_indexed=true) | `ocr_done` |
| `error` | has `ocr_processing` pages | `ocr_processing` pages → `ocr_done` | `ocr_done` |
| `error` | has `indexing` pages, no `ocr_done` | `indexing` pages → `indexed` (is_indexed=true) | `ready` |
| `error` | has `indexing` pages + `ocr_done` pages | `indexing` pages → `indexed` (is_indexed=true) | `ocr_done` |
| `error` | has `ocr_done` pages only | none | `ocr_done` |
| `error` | has `indexed` pages only | none | `ready` |
| `error` | no surviving page states | none | `ocr_done` |

> When force-complete resolves to `ocr_done`, the normal indexing pipeline will pick up
> remaining `ocr_done` pages automatically on the next worker cycle.

---

## API Endpoints

All write endpoints require **editor** role or above. Read endpoints are role-dependent as noted.

### Book Lifecycle

| Action | Method | Endpoint | Auth | Book status after |
|---|---|---|---|---|
| Upload PDF | `POST` | `/api/books/upload` | editor | `pending` |
| Start OCR | `POST` | `/api/books/{id}/start-ocr` | editor | `ocr_processing` |
| Retry failed/stuck pages | `POST` | `/api/books/{id}/retry-ocr` | editor | `ocr_processing` |
| Force complete current stage | `POST` | `/api/books/{id}/force-complete` | editor | `ocr_done` or `ready` |
| Reindex embeddings | `POST` | `/api/books/{id}/reindex` | editor | `ocr_processing` → `ready` |
| Full reprocess (clears pages) | `POST` | `/api/books/{id}/reprocess` | editor | `ocr_processing` |
| Delete book | `DELETE` | `/api/books/{id}` | editor | — |

### Page-Level Operations

| Action | Method | Endpoint | Auth | Page status after |
|---|---|---|---|---|
| Reset single page | `POST` | `/api/books/{id}/pages/{n}/reset` | editor | `pending`, book → `ocr_processing` |
| Update page text manually | `POST` | `/api/books/{id}/pages/{n}/update` | editor | `ocr_done` → `indexed` (synchronous embed) |
| Reprocess single page | `POST` | `/api/books/{id}/pages/{n}/reprocess` | editor | `pending` → re-queued |
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
| `ocr_max_retry_count` | `3` | Max OCR attempts per page before auto-skip |

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

## Reprocess (internal)

`POST /api/books/{id}/reprocess` — not exposed in the admin UI action menu.

- Full restart: deletes all pages, re-runs OCR + indexing from scratch
- Accepts `force_realtime=true` to bypass batch mode
- Use for severe data corruption or full pipeline re-runs

## Reset Page

`POST /api/books/{id}/pages/{n}/reset`

- Resets a single page to `pending` and triggers re-OCR for that page only
- Sets book status to `ocr_processing` while that page is being redone
