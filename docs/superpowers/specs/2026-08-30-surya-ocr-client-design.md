# Local Surya OCR Client — Design

**Date:** 2026-08-30
**Branch:** `feature/surya-ocr-client` (fresh off `main` — no Surya code in the Kitabim app itself)
**Status:** Approved — ready for implementation planning

## Motivation

`poc/easy-ocr-v2` wired a local OCR engine (Surya, née EasyOCR) directly into the production worker (`ocr_job.py` / `packages/backend-core/app/services/surya_service.py`), selected via the `ocr_engine` system_config. Running Surya's recognition model in prod requires deploying its runtime (`llama-server` CPU backend, extra memory headroom, capped parallel slots) alongside the existing worker infra — real ongoing infra cost for something that only needs to run occasionally, on one person's machine.

This design keeps `poc/easy-ocr-v2` exactly as-is (untouched, not merged, not deleted) and takes a different approach on a fresh branch: **a standalone local client** that runs Surya OCR entirely on the user's own desktop hardware (full GPU/CPU access, no containerization), lets the user preview and redo OCR results before committing to anything, and pushes only the finished text to Kitabim over its existing public API. Kitabim itself gains two small API endpoints and otherwise doesn't change — prod keeps Gemini as its only OCR engine, exactly as it is on `main` today.

## Current State (for context — unchanged by this design except where noted)

- **OCR pipeline today (main):** `OcrScanner` claims idle `Page` rows per book, enqueues `ocr_job(book_id, page_ids)`. The job downloads the book's PDF once, renders each page via PyMuPDF, and calls Gemini Vision per page (or the Gemini Batch API in batch mode). See `docs/main/OCR_DESIGN.md`.
- **Prior art for "OCR already done, skip the pipeline's OCR step" already exists**: DOCX uploads (`POST /books/upload`) extract page text immediately, create `Page` rows with `text` pre-filled and `ocr_milestone='succeeded'`, and enter the pipeline directly at chunking (`docs/main/DOCUMENT_DISCOVERY_DESIGN.md`). This design's new-book endpoint reuses that exact shape for a pre-OCR'd PDF instead of inventing a new mechanism.
- **Reprocessing an existing book's downstream stages is also existing behavior**: `POST /{book_id}/reprocess/chunking` resets `chunking_milestone`/`embedding_milestone`/`spell_check_milestone` to `idle` (plus `retry_count=0`, `is_indexed=False`) and lets the scanners recreate chunks. `chunking_job.py` deletes and recreates a page's chunks atomically (`delete(Chunk).where(...)` followed by an upsert) — resetting the milestone is sufficient, no separate cleanup step is needed. This design's page-correction endpoint reuses this exact mechanism, scoped to specific pages.
- **Auth is OAuth-JWT only** — no API-key/service-account path exists into the backend today. The OAuth callback already supports a "mobile redirect flow": `GET /auth/{provider}/login?redirect_uri=<url>` redirects back to `{redirect_uri}#access_token=...` after login, which is what the local client's login will use. The refresh-token cookie set alongside it is scoped to the backend's own domain and isn't retrievable by a non-browser client, so the client cannot silently refresh — access tokens (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`, default 60) are short-lived and re-login is a real, accepted constraint (see Client Design).
- **`GET /{book_id}/download`** already serves a book's original PDF — reused by the client's existing-book correction flow to re-render pages locally.

## Scope

- New: a local, non-containerized client app (`clients/surya-ocr/`) that renders PDF pages, runs Surya OCR locally, offers a local preview UI to review/redo pages, and pushes finished results to Kitabim.
- New: two Kitabim backend endpoints supporting ingestion of pre-OCR'd content.
- Out of scope: any change to `services/worker`, `ocr_job.py`, or Gemini's OCR path. Prod's OCR engine remains Gemini-only. `poc/easy-ocr-v2` is not touched, merged, or referenced by this branch.

## Architecture

```
clients/surya-ocr/                 # new, standalone Python app, own deps/venv
├── engine/                        # local Surya OCR
│   ├── recognize.py               # RecognitionPredictor call, confidence/retry
│   │                               # loop, blank-page detection — vendored from
│   │                               # surya_service.py (poc/easy-ocr-v2), adapted
│   │                               # to run without llama-server/Docker
│   └── text_cleanup.py            # clean_uyghur_text, is_degenerate_ocr_output,
│                                   # is_toc_page — vendored copies from
│                                   # packages/backend-core/app/utils/text.py
├── preview/                       # local FastAPI app + simple web page
│   └── server.py                  # localhost:PORT — page-by-page image/text
│                                   # view, multi-select redo, push action
├── kitabim_client/                # thin HTTP client for the Kitabim API
│   ├── auth.py                    # lazy browser-based OAuth login
│   └── api.py                     # push_new_book, push_corrections,
│                                   # download_book_pdf
└── cli.py                         # `ocr <pdf>`, `push`, `correct <book_id>`

services/backend/api/endpoints/books_router.py   # + 2 new endpoints (below)
```

No shared package between the client and `packages/backend-core`: the vendored text-cleanup functions are copied, not imported, so the client stays free of FastAPI/SQLAlchemy/Neo4j and every other backend-core dependency it doesn't need. This trades a small amount of duplication (a handful of stable, rarely-changed text functions) for a genuinely lightweight desktop tool — a shared package was considered and rejected as overkill for one consumer.

## Backend Changes

### `POST /books/upload-ocrd`

New endpoint in `books_router.py`, same auth as `POST /books/upload` (editor/admin).

- Request: multipart PDF + a JSON array of `{page_number, text, is_toc}` covering every page of the PDF.
- Validation:
  - Page count in the array must exactly match the PDF's actual page count (PyMuPDF `page_count`, same check the existing upload path already does); reject with 400 on any mismatch or gap in `1..total_pages` — never create a partially-filled book.
  - Same content-hash duplicate detection as `POST /books/upload` (SHA-256 of the uploaded bytes against `books.content_hash`); a duplicate returns the existing book id, no new row.
- Effect: creates the `Book` row and `Page` rows in the same shape the DOCX-upload path already produces — `text`/`is_toc` pre-filled, `ocr_milestone='succeeded'` (book-level `'complete'`), `pipeline_step='chunking'`. The book enters the pipeline at chunking; `OcrScanner` never sees it.
- Provenance: sets `books.source="surya_local"` (reusing the existing `source` column, which today only distinguishes `"upload"` vs `"gcs_sync"`) so books ingested this way are identifiable later (e.g. in the admin UI) without a schema change.

### `POST /{book_id}/pages/ocr-override`

New endpoint in `books_router.py`, `require_editor` (same role as the existing single-page `/pages/{page_num}/reset`).

- Request: JSON array of `{page_number, text, is_toc}` for one or more pages of an existing book.
- Effect, per targeted page:
  - Overwrite `text`/`is_toc`, set `ocr_milestone='succeeded'`.
  - Reset `chunking_milestone`/`embedding_milestone`/`spell_check_milestone` to `idle`, `retry_count=0`, `is_indexed=False` — identical mechanics to `/reprocess/chunking`, scoped to just these pages instead of the whole book.
  - Same cache invalidation as `/reprocess/chunking` (`book:{book_id}`, `rag:search:{book_id}:*`, `rag:summary_search:*`).
- Downstream scanners pick the pages back up exactly as they would after any other milestone reset; no separate chunk-cleanup step is needed (see Current State).

## Client Design

### Local OCR + preview loop

1. `ocr <pdf>` renders every page locally (PyMuPDF) and runs the vendored Surya recognizer on each, using the same confidence-threshold/retry-with-bumped-zoom and degenerate-output guards `poc/easy-ocr-v2` already validated (adapted to call the recognition model directly, without the llama-server backend process).
2. The preview server shows each page's rendered image next to its OCR'd text (rendered through the same markdown/table convention chunking expects downstream).
3. From the preview UI the user can:
   - Redo OCR on **any subset of selected pages** (multi-select, not just one at a time).
   - Redo OCR on the **whole book**.
   - Mark the book (or, in correction mode, the selected pages) ready to push.
4. All of the above is fully local — no network calls, no auth, until the user explicitly pushes.

### Pushing to Kitabim

- **New book:** lazy login (see below), then one call to `POST /books/upload-ocrd` with the PDF and every page's final text.
- **Correcting an existing book:** `correct <book_id>` downloads the PDF via `GET /{book_id}/download`, runs the same local OCR/preview loop scoped to the pages the user picks, then pushes via `POST /{book_id}/pages/ocr-override` with just the changed pages.
- **Auth:** login happens lazily, immediately before a push call — not at startup, and not held open for the duration of OCR/review. `auth.py` opens the system browser to `GET /auth/{provider}/login?redirect_uri=http://localhost:PORT/oauth-callback`, and a one-shot local HTTP handler captures the `access_token` off the redirect fragment (a tiny static callback page reads `location.hash` and posts it to the local server, since fragments never reach a server directly). This sidesteps the 60-minute access-token expiry: OCR and review can take as long as needed, since the token is only needed for the push itself. On a 401 during push (token expired mid-operation), the client re-triggers login and retries the call once.

## Error Handling

| Scenario | Behavior |
|---|---|
| `upload-ocrd`: page count/array mismatch vs. actual PDF page count | Reject with 400; no book created. |
| `upload-ocrd`: content hash already exists | Return the existing book id (same as `/books/upload` today); no new row. |
| Local Surya recognition fails confidence/degenerate-output checks on a page | Flagged in the preview UI as needing a redo; never silently pushed. |
| Access token expires mid-push | Client catches 401, re-runs the lazy-login flow, retries the failed call once. |
| `ocr-override` targets a page number that doesn't exist on the book | Reject with 400 (no partial application to the pages that do exist). |

## Testing

- **Client (`clients/surya-ocr/`):** its own local pytest suite for the vendored engine/text-cleanup functions and the preview server's redo/multi-select logic. No dependency on `backend-core`'s test fixtures.
- **Backend:** standard repository/service/endpoint coverage per `api-unit-tester` conventions —
  - `upload-ocrd`: page-count validation, content-hash dedup, correct `Page`/`Book` field values on success, auth gating.
  - `ocr-override`: milestone-reset correctness on targeted pages only (untargeted pages unaffected), cache invalidation, auth gating, rejection of out-of-range page numbers.
- **Worker:** no new tests — `services/worker` is untouched by this design.

## Related Docs

- `docs/main/OCR_DESIGN.md` — current (Gemini-only, prod) OCR stage this design does not change.
- `docs/main/DOCUMENT_DISCOVERY_DESIGN.md` — the DOCX-upload pattern `upload-ocrd` reuses.
- `docs/superpowers/specs/2026-08-29-easy-ocr-integration-design.md` — the in-worker Surya integration on `poc/easy-ocr-v2`, kept as-is and unrelated to this branch.
