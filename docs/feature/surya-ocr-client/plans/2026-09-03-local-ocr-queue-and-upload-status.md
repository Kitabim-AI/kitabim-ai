# Local OCR Queue & Upload Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement sequential multi-book queueing and an "Uploaded" status column in the local Kitabim OCR client.

**Architecture:** Extend `OcrWorkDir` to persist `queue_status`, `queued_at`, `uploaded`, and `uploaded_at` in `book.json`. Introduce a sequential `BookQueueManager` in `engine/queue.py` that processes books one at a time and auto-advances. Update `preview/app_server.py` and `locales/{ug,en}.json` to show the Uploaded status column, queue positions, and auto-refresh every 10 seconds.

**Tech Stack:** Python 3.13, FastAPI, Pydantic, pytest, Vanilla HTML/JS, i18n JSON locales.

## Global Constraints
- Zero modifications to central backend (`services/backend`). All changes are restricted to `clients/kitabim-ocr/`.
- LLM system prompts rule (if any): English only.
- Sequential OCR execution: strictly 1 active book at a time to prevent GPU/CPU/memory thrashing.
- Auto-refresh rate: 10 seconds.
- Test runner: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/`.

---

### Task 1: Extend `OcrWorkDir` Metadata for Queue and Upload Status

**Files:**
- Modify: `clients/kitabim-ocr/engine/workdir.py:20-100`
- Test: `clients/kitabim-ocr/tests/engine/test_workdir.py`

**Interfaces:**
- Consumes: `book.json` schema
- Produces: `OcrWorkDir` attributes:
  - `workdir.queue_status: str` (`"idle" | "queued" | "processing" | "completed" | "failed"`)
  - `workdir.queued_at: float | None`
  - `workdir.uploaded: bool`
  - `workdir.uploaded_at: float | None`

- [ ] **Step 1: Write the failing test**

Add unit tests to `clients/kitabim-ocr/tests/engine/test_workdir.py`:
```python
def test_workdir_queue_and_upload_defaults(tmp_path: Path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    workdir = OcrWorkDir.create(tmp_path / "session_1", source_pdf=pdf, total_pages=5)
    assert workdir.queue_status == "idle"
    assert workdir.queued_at is None
    assert workdir.uploaded is False
    assert workdir.uploaded_at is None


def test_workdir_preserves_queue_and_upload_status(tmp_path: Path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    session_dir = tmp_path / "session_2"
    workdir = OcrWorkDir.create(
        session_dir,
        source_pdf=pdf,
        total_pages=5,
        queue_status="queued",
        queued_at=123456.78,
        uploaded=True,
        uploaded_at=234567.89,
    )
    loaded = OcrWorkDir.load(session_dir)
    assert loaded.queue_status == "queued"
    assert loaded.queued_at == 123456.78
    assert loaded.uploaded is True
    assert loaded.uploaded_at == 234567.89


def test_workdir_backward_compatibility(tmp_path: Path):
    pdf = tmp_path / "source.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")
    session_dir = tmp_path / "session_old"
    session_dir.mkdir()
    (session_dir / "book.json").write_text(
        json.dumps({
            "source_pdf": str(pdf),
            "book_id": "book_123",
            "total_pages": 3,
            "original_filename": "old.pdf",
        })
    )
    loaded = OcrWorkDir.load(session_dir)
    assert loaded.uploaded is True  # Inferred from book_id
    assert loaded.queue_status == "idle"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/engine/test_workdir.py -v`
Expected: FAIL (unexpected keyword arguments or missing attributes).

- [ ] **Step 3: Write minimal implementation**

Update `clients/kitabim-ocr/engine/workdir.py`:
- In `__init__`: add `queue_status: str = "idle"`, `queued_at: Optional[float] = None`, `uploaded: bool = False`, `uploaded_at: Optional[float] = None`.
- In `create`: accept these optional parameters and pass to `cls(...)`.
- In `load`: parse `queue_status` (fallback: `"completed"` if all pages done, else `"idle"`), `queued_at`, `uploaded` (fallback: `True` if `book_meta.get("book_id")` else `False`), `uploaded_at`.
- In `save`: serialize `queue_status`, `queued_at`, `uploaded`, `uploaded_at` into `book.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/engine/test_workdir.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/workdir.py clients/kitabim-ocr/tests/engine/test_workdir.py
git commit -m "feat: persist queue_status and uploaded flags in OcrWorkDir"
```

---

### Task 2: Implement Sequential `BookQueueManager` in `engine/queue.py`

**Files:**
- Create: `clients/kitabim-ocr/engine/queue.py`
- Test: `clients/kitabim-ocr/tests/engine/test_queue.py`

**Interfaces:**
- Consumes: `OcrWorkDir`, `work_root: Path`, runner callback
- Produces: `BookQueueManager` class with:
  - `enqueue(session_id: str) -> tuple[int, bool]` (returns `(queue_position, is_active)`)
  - `active_session_id: str | None`
  - `get_queue_position(session_id: str) -> int | None`
  - `cancel(session_id: str) -> bool`
  - `recover_queue() -> None`

- [ ] **Step 1: Write the failing test**

Create `clients/kitabim-ocr/tests/engine/test_queue.py`:
```python
import asyncio
from pathlib import Path
import pytest
from engine.workdir import OcrWorkDir
from engine.queue import BookQueueManager


@pytest.mark.asyncio
async def test_queue_processes_items_sequentially(tmp_path: Path):
    processed = []

    async def mock_runner(workdir: OcrWorkDir):
        processed.append(workdir.root.name)
        await asyncio.sleep(0.05)

    pdf = tmp_path / "mock.pdf"
    pdf.write_bytes(b"%PDF-1.4 mock")

    w1 = OcrWorkDir.create(tmp_path / "b1", source_pdf=pdf, total_pages=1)
    w2 = OcrWorkDir.create(tmp_path / "b2", source_pdf=pdf, total_pages=1)
    w3 = OcrWorkDir.create(tmp_path / "b3", source_pdf=pdf, total_pages=1)

    qm = BookQueueManager(work_root=tmp_path, runner=mock_runner)

    pos1, active1 = await qm.enqueue("b1")
    assert active1 is True
    assert pos1 == 0

    pos2, active2 = await qm.enqueue("b2")
    assert active2 is False
    assert pos2 == 1

    pos3, active3 = await qm.enqueue("b3")
    assert active3 is False
    assert pos3 == 2

    # Wait for queue worker to finish all jobs
    await qm.wait_all()
    assert processed == ["b1", "b2", "b3"]
    assert qm.active_session_id is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/engine/test_queue.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'engine.queue'`).

- [ ] **Step 3: Write minimal implementation**

Create `clients/kitabim-ocr/engine/queue.py`:
- `BookQueueManager`:
  - `__init__(self, work_root: Path, runner: Callable[[OcrWorkDir], Awaitable[None]])`
  - `enqueue(session_id: str) -> tuple[int, bool]`:
    - Loads workdir, sets `queue_status="queued"`, `queued_at=time.time()`, saves.
    - If no active task is running, starts queue processing loop in background task.
  - `_worker_loop()`:
    - Runs while queue is not empty:
      - Pops next session ID.
      - Sets `active_session_id`, sets `queue_status="processing"`, saves.
      - Awaits `runner(workdir)`.
      - On completion, sets `queue_status="completed"` (or `"failed"` if runner threw), saves.
  - `recover_queue()`:
    - Reads all session directories in `work_root`, filters items with `queue_status in ("queued", "processing")`, orders by `queued_at`, and resumes worker loop.

- [ ] **Step 4: Run test to verify it passes**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/engine/test_queue.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/queue.py clients/kitabim-ocr/tests/engine/test_queue.py
git commit -m "feat: implement sequential BookQueueManager"
```

---

### Task 3: Integrate `BookQueueManager` & Upload Status into `preview/app_server.py`

**Files:**
- Modify: `clients/kitabim-ocr/preview/app_server.py`
- Modify: `clients/kitabim-ocr/preview/server.py`
- Test: `clients/kitabim-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: `BookQueueManager`
- Produces:
  - Non-blocking `/api/start/upload` and `/api/start/existing` returning `{ "status": "queued", "sessionId": str, "queuePosition": int, "isProcessing": bool }`
  - `/api/sessions` returning `uploaded: bool`, `uploadedAt: float | None`, `queueStatus: str`, `queuePosition: int | None`
  - `/api/push` updating `workdir.uploaded = True` and saving `book.json`

- [ ] **Step 1: Write the failing test**

Add tests to `clients/kitabim-ocr/tests/preview/test_app_server.py`:
```python
def test_upload_can_queue_multiple_books_without_409(client, work_root):
    # Upload first PDF
    res1 = client.post("/api/start/upload", files={"file": ("book1.pdf", b"%PDF-1.4 mock", "application/pdf")})
    assert res1.status_code == 200
    data1 = res1.json()
    assert data1["queuePosition"] == 0 or data1["isProcessing"] is True

    # Upload second PDF immediately while first is active - must NOT throw 409
    res2 = client.post("/api/start/upload", files={"file": ("book2.pdf", b"%PDF-1.4 mock", "application/pdf")})
    assert res2.status_code == 200
    data2 = res2.json()
    assert data2["queuePosition"] >= 1

    # Check /api/sessions list has queueStatus and uploaded flags
    sessions_res = client.get("/api/sessions")
    assert sessions_res.status_code == 200
    sessions = sessions_res.json()
    assert len(sessions) >= 2
    assert "uploaded" in sessions[0]
    assert "queueStatus" in sessions[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/preview/test_app_server.py -k test_upload_can_queue_multiple_books_without_409 -v`
Expected: FAIL (409 Conflict).

- [ ] **Step 3: Update `app_server.py` & `server.py`**

- In `preview/app_server.py`:
  - Wire `BookQueueManager` into `AppState`.
  - In `list_local_sessions`: add `"uploaded": workdir.uploaded`, `"uploadedAt": workdir.uploaded_at`, `"queueStatus": workdir.queue_status`, `"queuePosition": queue_pos`.
  - In `start_upload`: remove `_require_landing_stage(state)` blocking check. Enqueue session via `queue_manager.enqueue(...)`. Return `{ "status": "queued", "sessionId": workdir.root.name, "queuePosition": pos, "isProcessing": is_active }`.
  - In `start_existing`: similarly remove `_require_landing_stage(state)` blocking check. Enqueue session.
  - In `delete_session`: remove from queue manager if queued before deleting folder.
- In `preview/server.py`:
  - In `push_response`: after `client.push_new_book(...)` or `push_page_correction(...)`, set `workdir.uploaded = True`, `workdir.uploaded_at = time.time()`, and call `workdir.save()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/preview/test_app_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/preview/app_server.py clients/kitabim-ocr/preview/server.py clients/kitabim-ocr/tests/preview/test_app_server.py
git commit -m "feat: integrate queue manager into app_server endpoints and push tracking"
```

---

### Task 4: UI & Locale Updates (Uploaded Column & 10s Auto-Refresh)

**Files:**
- Modify: `clients/kitabim-ocr/locales/ug.json`
- Modify: `clients/kitabim-ocr/locales/en.json`
- Modify: `clients/kitabim-ocr/preview/app_server.py` (HTML table, JS functions)
- Test: `clients/kitabim-ocr/tests/test_i18n.py`

**Interfaces:**
- Consumes: `sessions[i].uploaded`, `sessions[i].queueStatus`, `sessions[i].queuePosition`
- Produces:
  - Table header: `<th>يۈكلەنگەن ھالىتى</th>` / `<th>Uploaded</th>`
  - Table row badges for uploaded state (`✓ Uploaded` / `⏳ Not Uploaded`)
  - Status badges for queue (`🕒 Queued #N` / `كۈتۈلمەكتە #N`)
  - 10-second timer for polling `loadLocalSessions()`

- [ ] **Step 1: Write test for new locale keys**

Update `clients/kitabim-ocr/tests/test_i18n.py` to ensure `th_uploaded`, `status_uploaded`, `status_not_uploaded`, `status_queued`, `toast_queued` exist in both `ug.json` and `en.json`.

- [ ] **Step 2: Run test to verify it fails**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/test_i18n.py -v`
Expected: FAIL (missing keys).

- [ ] **Step 3: Update locales & HTML/JS**

- In `locales/en.json` and `locales/ug.json`:
  - Add keys:
    - `"sessions.th_uploaded"`: "Uploaded" / "يۈكلەنگەن ھالىتى"
    - `"sessions.uploaded_yes"`: "Uploaded" / "يۈكلەنگەن"
    - `"sessions.uploaded_no"`: "Not Uploaded" / "يۈكلەنمىگەن"
    - `"sessions.status_queued"`: "Queued (#{pos})" / "نۆۋەتتە (#{pos})"
    - `"upload.toast_queued"`: "Book added to queue (Position: #{pos})" / "كىتاب نۆۋەتكە قوشۇلدى (نۆۋەت نومۇرى: #{pos})"
- In `preview/app_server.py`:
  - Update `<thead>` of `#tabSessionsContent` table: add `<th>` for Uploaded Status.
  - In `loadLocalSessions()`:
    - Render Uploaded column cell with emerald pill (`tag-badge success`) or amber pill (`tag-badge pending`).
    - If `s.queueStatus === 'queued'`, render queue status badge with position.
    - Set up or maintain `setInterval(loadLocalSessions, 10000)` whenever any session in the list has `queueStatus === 'processing'` or `queueStatus === 'queued'`. Clear interval when all are completed or idle.
  - In upload & start handlers: when response indicates book is queued, stay on landing page, refresh sessions list, and show toast notification.

- [ ] **Step 4: Run test to verify it passes**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/test_i18n.py clients/kitabim-ocr/tests/preview/test_app_server.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/locales/ clients/kitabim-ocr/preview/app_server.py clients/kitabim-ocr/tests/
git commit -m "feat: add Uploaded column, queue badges, and 10s auto-refresh to local client UI"
```

---

### Task 5: Full Regression Testing & Verification

**Files:**
- Run full test suite across `clients/kitabim-ocr/tests/`

- [ ] **Step 1: Execute all client tests**

Run: `clients/kitabim-ocr/.venv/bin/pytest clients/kitabim-ocr/tests/ -v`
Expected: 125+ passed, 0 failures.

- [ ] **Step 2: Commit any final cleanup or formatting**

```bash
git status
```
