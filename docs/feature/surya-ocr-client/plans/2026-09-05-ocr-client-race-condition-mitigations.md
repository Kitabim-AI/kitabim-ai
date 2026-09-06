# OCR Client Race Condition Mitigations Implementation Plan

**Branch:** `feature/surya-ocr-client`  
**Date:** September 5, 2026  
**Component:** `clients/kitabim-ocr` (Desktop OCR Client)  

---

## Problem Summary & Background

In the Kitabim OCR desktop client (`clients/kitabim-ocr`), users can run OCR on a book while reviewing and modifying page content concurrently. Several race conditions can cause silent loss of human edits, premature push of empty pages, and JSON corruption:

1. **Split-Brain Instances:** `open_session()` and `resume_session()` in `preview/app_server.py` load a detached `OcrWorkDir` instance from disk even when `BookQueueManager` is actively processing that same book, creating divergent in-memory page sets and unshared locks.
2. **Unconditional In-Flight Overwrites:** When `ocr_page()` finishes (after a multi-second inference gap), it unconditionally overwrites page text and resets `is_toc = False`, clobbering any human edits made while the OCR was in flight.
3. **Queue Loop Discarding In-Memory Edits:** At the completion of an OCR run, `queue.py` reloads `workdir = OcrWorkDir.load(session_dir)` without locks, overwriting recent in-memory page edits.
4. **Pushing During Active OCR:** `push()` does not check if OCR or Redo is running, potentially pushing empty pages and prematurely marking the book as uploaded.
5. **Non-Atomic File I/O:** `OcrWorkDir.save()` uses non-atomic `write_text` without internal lock enforcement, risking reading truncated/corrupted JSON during concurrent requests.
6. **Destructive DOM Re-renders:** Frontend Redo completion handlers run `container.innerHTML = ''`, destroying textareas and active keystrokes on other pages.

---

## Proposed Changes

### Component 1: Engine WorkDir (`clients/kitabim-ocr/engine/workdir.py`)
- Change `self.save_lock` from `threading.Lock()` to `threading.RLock()` so nested callers (or internal methods) can safely lock without deadlock.
- Enforce `with self.save_lock:` inside `OcrWorkDir.save()`.
- Implement **atomic write** for `book.json` and `pages.json` using temporary files (`.tmp`) and `os.replace` to prevent concurrent readers from seeing empty/truncated JSON.
- Guard `all_pages()` and `get_page()` under `self.save_lock` to avoid `RuntimeError: dictionary changed size during iteration`.

---

### Component 2: Engine Queue (`clients/kitabim-ocr/engine/queue.py`)
- In `_process_loop()`:
  - Do not discard `self._active_workdir` and reload from disk after `await self.runner(workdir)`.
  - Mutate the live `workdir` under `workdir.save_lock` to set `queue_status = "completed"` and call `workdir.save()`.
  - Similarly handle failed status under `workdir.save_lock`.

---

### Component 3: Preview Server & App Server (`clients/kitabim-ocr/preview/`)
- In `open_session(session_id)`:
  - If `state.queue_manager and state.queue_manager.active_session_id == session_id and state.queue_manager.active_workdir is not None`, reuse `state.queue_manager.active_workdir` instead of loading a new instance from disk.
- In `resume_session(session_id)`:
  - If `session_id` is already the active session in `state.queue_manager`, reuse `state.queue_manager.active_workdir`.
- In `_run_ocr_background(workdir, state)`:
  - In `process_one(page_number)`: After OCR model inference finishes, before writing the OCR result, inspect `current_page = workdir.get_page(page_number)` under `workdir.save_lock`.
  - If `current_page.status == "reviewed"`, **preserve** the user's manual text and `is_toc` flag.
  - If the page was previously marked `is_toc`, preserve `is_toc`.
- In `push()` (`/api/push`):
  - Check if the book currently has active OCR tasks running (or status `processing` / `pending`). If so, reject with HTTP 409 Conflict.
- In `toggle_session_uploaded(session_id)`:
  - If the session matches `state.workdir` or `state.queue_manager.active_workdir`, mutate that live instance under `save_lock` instead of loading a disconnected copy.
- In `redo_pages_response()`:
  - Preserve `is_toc` if the page was marked as TOC by the user.
  - If `status == "reviewed"` was set while redo was in flight, do not blindly overwrite.

---

### Component 4: Frontend UI Reconciliation
- In JavaScript review mode:
  - After Redo finishes, do not destroy all textareas with `container.innerHTML = ''`.
  - Implement targeted updates: find the specific page cards by `#page-card-${pageNum}`, update their status badge and image version, and only update the textarea if the user is NOT currently focusing/editing that specific textarea.

---

## Verification Plan

### Automated Tests
- Run existing test suite:
  ```bash
  clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests
  ```
- Add comprehensive concurrency and protection tests in:
  - `clients/kitabim-ocr/tests/engine/test_workdir.py`
  - `clients/kitabim-ocr/tests/engine/test_queue.py`
  - `clients/kitabim-ocr/tests/preview/test_app_server.py`
  - `clients/kitabim-ocr/tests/preview/test_server.py`
