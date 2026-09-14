# Local OCR Queue & Upload Status Design

## Overview
This document specifies the design for adding sequential queue processing and upload tracking to the local Kitabim OCR client (`clients/kitabim-ocr`).

Currently, the client only allows one active book at a time, throws `409 Conflict` if a new book is uploaded or selected while OCR is running, and does not record or display whether a local session has been pushed/uploaded to the Kitabim Cloud server.

This feature enables users to continuously add books (via local PDF upload or Kitabim Library selection) while OCR is running. The client queues subsequent books, processes them one-by-one automatically in FIFO order, and displays an "Uploaded" status column in the local sessions book list view.

---

## Key Requirements
1. **Multi-Book Queueing**: Users can upload new PDFs or select books from Kitabim Library even when OCR is currently in progress.
2. **Automatic Sequential Execution**: Exactly one book undergoes OCR processing at a time (preventing memory/GPU exhaustion). When the active book completes (or fails), the next queued book starts OCR automatically.
3. **Queue Visibility**: The local sessions book list displays queue position (`Queued #1`, `Queued #2`, etc.) and processing progress (`Processing (X/Y pages, Z%)`).
4. **Uploaded Status Column**: A dedicated column in the book list shows whether a book has been uploaded to Kitabim:
   - **Local PDF uploads**: starts as `Not Uploaded` (`يۈكلەنمىگەن`), switches to `Uploaded` (`يۈكلەنگەن`) once successfully pushed to Kitabim.
   - **Kitabim Library books**: starts as `Uploaded` (`يۈكلەنگەن`) since it originates from Kitabim.
5. **Periodic Auto-Refresh**: When any book is queued or processing, the sessions table auto-refreshes every 10 seconds to display real-time progress.
6. **Zero Backend API Changes**: All changes remain strictly inside `clients/kitabim-ocr`. The central backend (`services/backend`) requires no modifications.

---

## Architecture & Data Model

### 1. Data Model (`engine/workdir.py` & `book.json`)
The session metadata stored on disk in `<session_dir>/book.json` is extended:

```json
{
  "source_pdf": "/path/to/book.pdf",
  "book_id": null,
  "total_pages": 120,
  "original_filename": "history.pdf",
  "queue_status": "queued",
  "queued_at": 1756885200.123,
  "uploaded": false,
  "uploaded_at": null
}
```

#### Fields:
- `queue_status`: `"idle" | "queued" | "processing" | "completed" | "failed"` (defaults to `"idle"`).
- `queued_at`: `float | None` (epoch timestamp when added to queue).
- `uploaded`: `bool` (defaults to `False` for local PDF uploads, `True` for Kitabim library downloads).
- `uploaded_at`: `float | None` (epoch timestamp when pushed to Kitabim).

#### Backward Compatibility:
When loading existing directories lacking these fields:
- `uploaded`: inferred as `True` if `book_id` is present, otherwise `False`.
- `queue_status`: inferred as `"completed"` if all pages are done, otherwise `"idle"`.

---

### 2. Queue Manager (`engine/queue.py`)
A dedicated `BookQueueManager` handles sequential execution:
- **State**:
  - `active_session_id: str | None`: the ID of the currently running session.
  - `active_task: asyncio.Task | None`: running background OCR task.
  - `queue: list[str]`: ordered list of session IDs waiting to be processed.
- **Methods**:
  - `enqueue(session_id: str) -> int`: marks session as `"queued"`, adds to list, returns queue position. If idle, triggers `_start_next()`.
  - `cancel(session_id: str) -> bool`: removes from queue if not active.
  - `_start_next()`: pops head of queue, marks as `"processing"`, starts OCR runner coroutine.
  - `on_session_finished(session_id: str, success: bool)`: marks session as `"completed"` or `"failed"`, clears `active_session_id`, and immediately calls `_start_next()`.
  - `recover_queue(work_root: Path)`: scans `work_root` on startup for unfinished/queued sessions, rebuilds queue in order of `queued_at`, and starts processing.

---

### 3. App Server Changes (`preview/app_server.py`)

1. **Upload & Existing Book Endpoints**:
   - `POST /api/start/upload`:
     - Creates workdir with `uploaded=False`, `queue_status="queued"`.
     - Calls `queue_manager.enqueue(session_id)`.
     - Returns `{ "status": "queued", "sessionId": session_id, "queuePosition": pos, "isProcessing": is_active }`.
   - `POST /api/start/existing`:
     - Creates workdir with `uploaded=True`, `queue_status="queued"`.
     - Calls `queue_manager.enqueue(session_id)`.
     - Returns `{ "status": "queued", "sessionId": session_id, "queuePosition": pos, "isProcessing": is_active }`.

2. **Session Listing (`GET /api/sessions`)**:
   - Each session in the returned list includes:
     - `uploaded: bool`
     - `uploadedAt: float | None`
     - `queueStatus: str`
     - `queuePosition: int | None`

3. **Push Endpoint (`POST /api/push`)**:
   - Upon successful push via `KitabimClient`, sets `workdir.uploaded = True`, `workdir.uploaded_at = time.time()`, and saves `book.json`.

4. **Delete Endpoint (`DELETE /api/sessions/{session_id}`)**:
   - If session is queued, removes it from queue before directory deletion.

---

### 4. UI & Localization

1. **Local Sessions Table Columns**:
   1. **Book / Document** (`كىتاب / ھۆججەت`)
   2. **Pages & Progress** (`بەت سانى ۋە تەرەققىياتى`)
   3. **Status** (`ھالىتى`):
      - `⚡ Processing (X/Y pages, Z%)` (with progress bar)
      - `🕒 Queued (#N in line)` / `كۈتۈلمەكتە (#N)`
      - `✓ Completed` / `پۈتتى`
      - `❌ Failed` / `مەغلۇپ بولدى`
   4. **Uploaded** (`يۈكلەنگەن ھالىتى`):
      - `✓ Uploaded` (`يۈكلەنگەن`) with emerald badge
      - `⏳ Not Uploaded` (`يۈكلەنمىگەن`) with amber badge
   5. **Last Modified** (`ئۆزگەرتىلگەن ۋاقتى`)
   6. **Action** (`مەشغۇلات`): View Results, Resume, or Delete

2. **Auto-Refresh**:
   - `setInterval(loadLocalSessions, 10000)` runs whenever any session has `queueStatus === 'processing'` or `queueStatus === 'queued'`.

3. **User Feedback**:
   - When a book is added while another is processing, a non-blocking toast informs the user:
     - Uyghur: `كىتاب نۆۋەتكە مۇۋەپپەقىيەتلىك قوشۇلدى (نۆۋەت نومۇرى: #N)`
     - English: `Book added to queue successfully (Position: #N)`
   - The user stays on the Local Sessions tab to see all queued items.

---

## Verification Plan
1. **Unit / Integration Tests (`tests/test_queue.py`)**:
   - Test enqueueing multiple books and sequential execution.
   - Test queue recovery from disk on startup.
   - Test upload status tracking in `book.json` before and after `/api/push`.
2. **End-to-End Client Testing**:
   - Start client with test workdir.
   - Queue multiple PDFs sequentially.
   - Verify that the second PDF starts automatically when the first completes.
   - Verify that the "Uploaded" column shows "Not Uploaded" initially, and switches to "Uploaded" after pushing.
