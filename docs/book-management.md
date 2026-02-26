# Book Management Reference

## Book Status Values

| Status | Description |
|---|---|
| `uploading` | File is being uploaded to storage — not yet persisted as a book record |
| `pending` | Book record created, waiting for OCR to be triggered |
| `ocr_processing` | OCR (and/or embedding) job is actively running in the worker |
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
                    │ pending │  ◄─── Start OCR triggered here
                    └────┬────┘
                         │ Start OCR
                         ▼
               ┌──────────────────┐
               │  ocr_processing  │  ◄─── Retry OCR / Reindex / Reset Page land here too
               └────────┬─────────┘
                        │                    │
              pages done │              error │
                        ▼                    ▼
                  ┌──────────┐          ┌───────┐
                  │ ocr_done │          │ error │
                  └────┬─────┘          └───┬───┘
                       │ indexing starts     │ Retry OCR
                       ▼                    │
                  ┌──────────┐             (back to ocr_processing)
                  │ indexing │
                  └────┬─────┘
                       │ complete
                       ▼
                  ┌─────────┐
                  │  ready  │  ◄─── Reindex available from here
                  └─────────┘
```

---

## Page Status Values

Pages track individual PDF pages through their own pipeline.

| Status | Description |
|---|---|
| `pending` | Waiting to be OCR'd |
| `ocr_processing` | OCR running for this page |
| `ocr_done` | Raw text extracted, not yet chunked |
| `chunked` | Text split into chunks, not yet embedded |
| `indexing` | Embeddings being generated |
| `indexed` | Fully embedded and searchable |
| `error` | This page failed OCR or indexing |

---

## Admin Action Buttons

### Enable / Disable Rules

These are evaluated in [ActionMenu.tsx](../apps/frontend/src/components/admin/ActionMenu.tsx).

```
isStale             = (status is ocr_processing OR indexing)
                      AND processingLockExpiresAt is in the past

isActuallyProcessing = (status is ocr_processing OR indexing)
                       AND NOT isStale

hasFailedPages      = errorCount > 0 OR any page.status === 'error'

canRetry            = (hasFailedPages OR status === 'error' OR isStale)
                      AND NOT isActuallyProcessing

canStartOcr         = NOT isActuallyProcessing
                      AND NOT canRetry
                      AND status !== 'ready'
                      AND status !== 'uploading'

canReindex          = status === 'ready'
```

### Button State by Status

| Book Status | View | Start OCR | Retry OCR | Reindex | Delete |
|---|---|---|---|---|---|
| `uploading` | disabled | disabled | disabled | disabled | enabled |
| `pending` | disabled | **enabled** | disabled | disabled | enabled |
| `ocr_processing` (active) | enabled | disabled | disabled | disabled | enabled |
| `ocr_processing` (stale lock) | enabled | disabled | **enabled** | disabled | enabled |
| `ocr_done` | enabled | enabled | disabled | disabled | enabled |
| `indexing` (active) | enabled | disabled | disabled | disabled | enabled |
| `indexing` (stale lock) | enabled | disabled | **enabled** | disabled | enabled |
| `ready` | enabled | disabled | disabled | **enabled** | enabled |
| `error` | enabled | disabled | **enabled** | disabled | enabled |
| `error` + failed pages | enabled | disabled | **enabled** | disabled | enabled |

> **Stale detection**: A job is considered stale when the book is in `ocr_processing` or `indexing`
> and `processingLockExpiresAt` is in the past. This unlocks Retry OCR so admins can recover
> stuck books without backend intervention.

---

## API Endpoints

All write endpoints require **editor** role or above. Read endpoints are role-dependent as noted.

### Book Lifecycle

| Action | Method | Endpoint | Auth | Book status after |
|---|---|---|---|---|
| Upload PDF | `POST` | `/api/books/upload` | editor | `pending` |
| Start OCR | `POST` | `/api/books/{id}/start-ocr` | editor | `ocr_processing` |
| Retry failed pages | `POST` | `/api/books/{id}/retry-ocr` | editor | `ocr_processing` |
| Full reprocess (clears pages) | `POST` | `/api/books/{id}/reprocess` | editor | `ocr_processing` |
| Reindex embeddings | `POST` | `/api/books/{id}/reindex` | editor | `ocr_processing` → `ready` |
| Delete book | `DELETE` | `/api/books/{id}` | editor | — |

### Page-Level Operations

| Action | Method | Endpoint | Auth | Page status after |
|---|---|---|---|---|
| Reset single page | `POST` | `/api/books/{id}/pages/{n}/reset` | editor | `pending`, book → `ocr_processing` |
| Update page text manually | `POST` | `/api/books/{id}/pages/{n}/update` | editor | `ocr_done` |
| Reprocess single page | `POST` | `/api/books/{id}/pages/{n}/reprocess` | editor | `pending` → re-queued |
| Spell-check page | `POST` | `/api/books/{id}/pages/{n}/spell-check` | editor | unchanged |
| Apply spell corrections | `POST` | `/api/books/{id}/pages/{n}/apply-corrections` | editor | unchanged |

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

## Operation Details

### Start OCR (`POST /start-ocr`)
- Deletes all existing pages if book was previously processed (non-`pending` status)
- Sets book to `ocr_processing` + `processing_step = 'ocr'`
- Enqueues PDF processing job in the worker

### Retry OCR (`POST /retry-ocr`)
- If book is in `error` with no specific failed pages → resumes from scratch
- If there are pages with `status = 'error'` → resets only those pages to `pending` and re-queues
- Sets book to `ocr_processing`

### Reindex (`POST /reindex`)
- Only meaningful when book is `ready` (frontend enforces this)
- Resets `is_indexed = false` on all `ocr_done` pages
- Deletes all existing chunks
- Sets book to `ocr_processing` and re-queues (worker will re-chunk and re-embed)

### Reprocess (`POST /reprocess`)
- Full restart: deletes all pages, re-runs OCR + indexing from scratch
- Accepts `force_realtime=true` to bypass batch mode
- Not exposed in the admin UI action menu (internal / recovery use)

### Reset Page (`POST /pages/{n}/reset`)
- Resets a single page to `pending` and triggers re-OCR for that page only
- Sets book status to `ocr_processing` while that page is being redone
