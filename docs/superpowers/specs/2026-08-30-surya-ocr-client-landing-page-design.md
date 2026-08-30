# Surya OCR Client — Book-Picker Landing Page — Design

**Date:** 2026-08-30
**Branch:** `feature/surya-ocr-client`
**Status:** Approved — ready for implementation planning
**Builds on:** `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` (the original client design — auth, engine, preview UI, backend endpoint)

## Motivation

The client currently requires the user to already know what they want to process before touching the UI: `cli.py ocr <path> --out <dir>` for a brand-new PDF, or `cli.py correct <book_id> --out <dir> --base-url <url>` for an existing Kitabim book — book id and local paths typed on the command line, OCR running synchronously in the terminal before the browser preview ever opens. There is no way to browse what's already in Kitabim and pick a book to fix, and no way to kick off a new PDF's OCR from the browser.

This design adds a landing screen to the existing local preview app: search/pick an existing Kitabim book, or upload a new local PDF, and watch OCR progress live in the browser — no CLI arguments beyond a single `cli.py app` invocation.

## Scope

- New: a landing screen in the existing `clients/surya-ocr/preview/` FastAPI app — book search (backed by Kitabim's existing `GET /books/`) and local-PDF upload, each with a "start" action.
- New: background (non-blocking) execution of the render+OCR loop, with live progress visible on the landing screen via the existing page-list endpoint.
- New: `cli.py app` command (no arguments; reads `KITABIM_BASE_URL` and `KITABIM_WORK_DIR` from the environment).
- New: `KitabimClient.list_books()` in `kitabim_client/api.py`.
- Removed: the `ocr` and `correct` argparse subcommands (their logic moves into the app's internal start-handlers, reused by `app`).
- Unchanged: `preview` and `push` subcommands (still operate on an existing workdir path, useful for scripting); the review screen's existing page list/redo/push behavior; all backend code; the local OCR engine itself.
- Out of scope: multi-user or remote access to the local server (still `127.0.0.1`-only); any change to how OCR itself runs per page.

## Architecture

The single FastAPI app in `preview/server.py` (today: preview-only) grows a `stage` state machine held in module-level state on the running process — this is a single-user, single-tab local tool, so process-global state (not per-session) is the right amount of complexity:

```
stage: "landing" | "processing" | "review" | "error"
```

`cli.py app` starts the server and opens the browser to `/` immediately (unlike today's `ocr`/`correct`, which block on the full OCR loop before ever starting the server). The page's own JS polls a small state endpoint and swaps between the landing markup, a progress view, and the existing review markup client-side — one long-lived page, no server-side redirects.

```
clients/surya-ocr/
├── preview/
│   └── server.py       # + stage state machine, landing/progress views,
│                         #   /api/books, /api/start/existing, /api/start/upload,
│                         #   /api/state, /api/reset
├── kitabim_client/
│   └── api.py           # + list_books()
└── cli.py                # `app` replaces `ocr`/`correct` as subcommands;
                            #   `preview`/`push` unchanged
```

## Landing Screen

Rendered when `stage == "landing"` (the initial state, and the state after "back to library").

**Existing Kitabim book panel:**
- A search input debounced client-side, hitting `GET /api/books?q=<text>&page=<n>`.
- `preview/server.py` proxies this to `KitabimClient.list_books(q, page, page_size=20)`, which calls the backend's existing `GET /books/?q=...&page=...&pageSize=...&sortBy=title`.
- Each result row shows title, author, total pages, and `ocrMilestone` (so a book already fully OCR'd is visually distinguishable from one still needing work) with a "Correct this book" button.

**New local PDF panel:**
- A standard `<input type="file" accept="application/pdf">` inside a form that posts to `POST /api/start/upload` as `multipart/form-data`. A browser cannot hand a local server a filesystem path, so the bytes are uploaded, not referenced.

## Starting Processing

Both entry points resolve a workdir under `KITABIM_WORK_DIR` and hand off to a background `asyncio.create_task`, then immediately flip `stage` to `"processing"` and return — the HTTP request that triggered them does not block on OCR.

**`POST /api/start/existing`** — body `{"bookId": "..."}`:
1. Workdir path is `${KITABIM_WORK_DIR}/${book_id}`. If `book.json` already exists there, `OcrWorkDir.load()` resumes it (no re-download) — covers the case where a previous correction session was interrupted.
2. Otherwise: download the PDF (`GET /{book_id}/download`, existing `KitabimClient.download_book_pdf`), fetch existing pages (`get_book_pages`), create the workdir, and pre-populate every page's `PageState` immediately — `status="from_kitabim"` for pages the API already returned text for. This is the same logic `cmd_correct` has today, just no longer followed by a blocking call to `serve()` since `serve()` is already running.
3. Background task re-OCRs pages the user later selects via the existing `/api/pages/redo` route — starting a correction session does **not** itself trigger OCR; it just loads the book for review. (OCR-on-start only applies to the new-PDF flow below, where there is no existing text at all.)

Because step 3 means "existing book" correction has no OCR to show progress for, `stage` goes straight to `"review"` after step 2 completes — the progress screen is only shown for the upload flow.

**`POST /api/start/upload`** — multipart PDF file:
1. Workdir path is `${KITABIM_WORK_DIR}/upload-<timestamp>`.
2. The uploaded PDF is saved into it; page count is read via PyMuPDF; every page's `PageState` is written immediately as `status="pending"` (new status value, not currently used) before OCR starts, so `GET /api/pages` reflects the full set of pages from the first poll.
3. The background task is the existing `cmd_ocr` per-page loop (render, call Surya, `workdir.set_page(...)`, `workdir.save()`), unchanged except that it no longer calls `serve()` at the end — it runs inside the already-serving app and flips `stage` to `"review"` on completion.

## Progress Display

While `stage == "processing"`, the landing page's JS polls the existing `GET /api/pages` every ~1s and renders `"{count(status != pending)} / {total}"` with a simple bar — no new progress endpoint. Once the polled response shows zero `pending` pages, the client-side JS transitions to the review markup itself (already has all the data `/api/pages` returns) rather than waiting for another round-trip.

A lightweight `GET /api/state` (`{"stage": ..., "error": ...}`) backs the initial page load so a browser refresh mid-processing lands back in the right view instead of always starting at `landing`.

## Review Screen Changes

The existing list/redo/push UI is unchanged, plus:
- A "back to library" link/button that calls `POST /api/reset`, which drops the in-memory `workdir`/`client` references and sets `stage = "landing"` — it does **not** delete anything on disk. The next `app` run (or the next "start" on the same run) for the same `book_id` will find and resume the existing workdir.

## CLI Changes

- `cli.py app`: no positional/flag arguments. Reads `KITABIM_BASE_URL` (Kitabim API base URL) and `KITABIM_WORK_DIR` (root directory for all workdirs) from the environment; exits with a clear error naming the missing variable if either is unset. Builds a `KitabimClient` and calls the server's new `serve_app(client, work_root)`, which opens the browser to `http://127.0.0.1:PORT/`.
- `ocr` and `correct` subcommands are removed from `build_parser()`. `cmd_ocr`/`cmd_correct` as standalone blocking functions go away; their logic is inlined into the two `/api/start/*` handlers described above (same engine/workdir calls, different caller and no trailing `serve()`).
- `preview` and `push` subcommands are unchanged — both already operate on a workdir path the caller provides, independent of this design.

## Error Handling

| Scenario | Behavior |
|---|---|
| `KITABIM_BASE_URL` or `KITABIM_WORK_DIR` unset when running `app` | CLI exits immediately with a message naming the missing variable; server never starts. |
| Background OCR/download task raises (network loss, corrupt PDF, etc.) | `stage` → `"error"`, message captured and shown on the landing page; user can retry from there (state resets to `"landing"` on retry, no partial workdir left in an ambiguous state — the failed workdir stays on disk for inspection). |
| A single page fails Surya's confidence/degenerate-output check during the upload flow's background OCR | Unchanged from today: flagged `status="failed"`, loop continues — visible in progress as "no longer pending" and later in review, never silently pushed. |
| User uploads a non-PDF or unreadable file | `/api/start/upload` returns 400 before creating a workdir or starting the background task; landing page shows the error inline, stays on `"landing"`. |
| User navigates to `/api/start/*` while `stage` is already `"processing"` or `"review"` | Rejected with 409 — only one job runs at a time per server process; the user must "back to library" first. |

## Testing

- `kitabim_client/api.py`: `list_books()` — request params, response parsing, mocked HTTP.
- `preview/server.py`: `stage` transitions for both start routes (existing-book resume vs. fresh download; upload pending-page pre-population), the 409 double-start guard, `/api/reset`, and `/api/state` — following the existing pattern of mocking `KitabimClient`/`fitz`/the recognizer already used in `tests/test_cli.py` and (per the original design) the preview server's own tests.
- `cli.py`: replace the two removed subcommand parser tests with one for `app` (env-var requirement, missing-var error message); existing `cmd_ocr`/`cmd_correct` behavioral assertions move to whatever module now hosts the inlined start-handler logic, unchanged in substance.

## Related Docs

- `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` — the client this design extends (engine, auth, original preview UI, backend endpoint).
