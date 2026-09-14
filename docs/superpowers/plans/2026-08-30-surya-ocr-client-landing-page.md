# Surya OCR Client — Book-Picker Landing Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a landing page to the Surya OCR client so a user can search/pick an existing Kitabim book to correct, or upload a new local PDF, and watch OCR progress in the browser, instead of typing a book id or PDF path on the command line.

**Architecture:** The existing single-workdir preview FastAPI app (`preview/server.py`) is left untouched except for extracting its route logic into plain functions. A new module, `preview/app_server.py`, adds a second FastAPI app that holds mutable session state (`stage`: `landing` → `processing`/`review` → back to `landing`, plus `error`) across the lifetime of one `cli.py app` run, and reuses the extracted functions once a workdir becomes active. `cli.py app` (new, replacing the `ocr`/`correct` subcommands) reads `KITABIM_BASE_URL` and `KITABIM_WORK_DIR` from the environment and launches this app.

**Tech Stack:** Python 3.13, FastAPI + uvicorn, PyMuPDF (`fitz`), httpx, pytest + pytest-asyncio (`asyncio_mode = auto`).

## Global Constraints

- Local server binds to `127.0.0.1` only (matches existing `preview/server.py:serve`).
- Exactly one book/PDF workdir is active per running `app` process at a time — starting a second one while `stage != "landing"` is rejected with HTTP 409.
- `cli.py app` requires `KITABIM_BASE_URL` and `KITABIM_WORK_DIR` as environment variables; if either is unset, exit immediately with a message naming the missing variable. This is the one place in the client that reads `os.environ` directly — this is a standalone desktop client with no `core/config.py`/settings module, so the backend/worker "no `os.environ.get()`" convention does not apply here; the user explicitly chose env vars for this config during design.
- Test command (run from `clients/surya-ocr/`): `python -m pytest -q` — uses the repo-root shared venv already on `PATH` (confirmed working: 46 tests passing before this plan's changes).
- Every new/changed Python file keeps `from __future__ import annotations` at the top, matching every existing file in this client.
- No behavior change to the `preview`/`push` CLI subcommands or to `engine/recognize.py`, `engine/workdir.py`, `engine/text_cleanup.py`.

---

## Task 1: Extract review-route logic in `preview/server.py` into plain functions

Pure refactor — behavior must not change. `create_app`'s four routes currently close over `workdir`/`client` as fixed parameters; Task 7 needs the same logic usable against a *mutable* current workdir, so it's pulled out into standalone functions `create_app` then calls.

**Files:**
- Modify: `clients/surya-ocr/preview/server.py`
- Test: `clients/surya-ocr/tests/preview/test_server.py` (no edits — used as the regression check)

**Interfaces:**
- Produces (used by Task 7):
  - `list_pages_response(workdir: OcrWorkDir) -> list[dict]`
  - `get_page_image_bytes(workdir: OcrWorkDir, page_number: int) -> bytes`
  - `async def redo_pages_response(workdir: OcrWorkDir, page_numbers: list[int]) -> list[dict]`
  - `push_response(workdir: OcrWorkDir, client) -> dict`
  - `RedoRequest` (pydantic model, already exists — unchanged, just reused)

- [ ] **Step 1: Extract the four helper functions above `create_app` in `preview/server.py`**

Replace the body of `create_app` (currently lines 86–159) with:

```python
def list_pages_response(workdir: OcrWorkDir) -> list[dict]:
    return [
        {
            "pageNumber": p.page_number,
            "text": p.text,
            "isToc": p.is_toc,
            "confidence": p.confidence,
            "status": p.status,
        }
        for p in workdir.all_pages()
    ]


def get_page_image_bytes(workdir: OcrWorkDir, page_number: int) -> bytes:
    return workdir.image_path(page_number).read_bytes()


async def redo_pages_response(
    workdir: OcrWorkDir, page_numbers: list[int]
) -> list[dict]:
    doc = fitz.open(workdir.source_pdf)
    predictor = await get_recognition_predictor()
    for page_number in page_numbers:
        fitz_page = doc.load_page(page_number - 1)
        try:
            text = await ocr_page_with_surya(fitz_page, predictor)
            workdir.set_page(
                page_number, text=text, is_toc=False, confidence=1.0, status="ocrd"
            )
        except LowConfidenceOcrError as exc:
            # Never silently push a page that failed OCR - flag it and
            # keep going, so one bad page doesn't abort the whole batch.
            try:
                previous_text = workdir.get_page(page_number).text
            except KeyError:
                previous_text = ""
            workdir.set_page(
                page_number,
                text=previous_text,
                is_toc=False,
                confidence=0.0,
                status="failed",
                error=str(exc),
            )
    workdir.save()
    return [
        {
            "pageNumber": p.page_number,
            "text": p.text,
            "status": p.status,
            "error": p.error,
        }
        for p in workdir.all_pages()
    ]


def push_response(workdir: OcrWorkDir, client) -> dict:
    if workdir.book_id is None:
        return client.push_new_book(workdir.source_pdf, workdir.all_pages())
    results = []
    for page in workdir.all_pages():
        results.append(client.push_page_correction(workdir.book_id, page))
    return {"status": "corrections_pushed", "count": len(results)}


def create_app(workdir: OcrWorkDir, client) -> FastAPI:
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _PAGE_HTML

    @app.get("/api/pages")
    def list_pages():
        return list_pages_response(workdir)

    @app.get("/api/pages/{page_number}/image")
    def get_page_image(page_number: int):
        return Response(
            content=get_page_image_bytes(workdir, page_number),
            media_type="image/png",
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        return await redo_pages_response(workdir, body.pageNumbers)

    @app.post("/api/push")
    def push():
        return push_response(workdir, client)

    return app
```

Leave everything else in the file (`_PAGE_HTML`, `RedoRequest`, `serve`) unchanged.

- [ ] **Step 2: Run the existing preview server tests to confirm no regression**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_server.py -v`
Expected: all 6 tests still PASS (same assertions as before — this is a pure refactor, the HTTP behavior is identical).

- [ ] **Step 3: Commit**

```bash
git add clients/surya-ocr/preview/server.py
git commit -m "refactor(surya-ocr-client): extract preview route logic into plain functions"
```

---

## Task 2: `KitabimClient.list_books()`

**Files:**
- Modify: `clients/surya-ocr/kitabim_client/api.py`
- Test: `clients/surya-ocr/tests/kitabim_client/test_api.py`

**Interfaces:**
- Produces (used by Task 4): `KitabimClient.list_books(self, q: str = "", page: int = 1, page_size: int = 20) -> dict`

- [ ] **Step 1: Write the failing test**

Add to `clients/surya-ocr/tests/kitabim_client/test_api.py`:

```python
def test_list_books_gets_paginated_books_with_query_params(tmp_path: Path):
    client = _client(tmp_path)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "books": [{"id": "b1", "title": "Tarikh"}],
        "total": 1,
        "totalReady": 1,
        "page": 2,
        "pageSize": 20,
    }

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_response) as mock_get,
    ):
        result = client.list_books(q="tarikh", page=2)

    assert result["total"] == 1
    assert result["books"][0]["id"] == "b1"
    call = mock_get.call_args
    assert call.args[0] == "http://localhost:8000/books/"
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok123"
    assert call.kwargs["params"] == {
        "q": "tarikh",
        "page": 2,
        "pageSize": 20,
        "sortBy": "title",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_api.py::test_list_books_gets_paginated_books_with_query_params -v`
Expected: FAIL with `AttributeError: 'KitabimClient' object has no attribute 'list_books'`

- [ ] **Step 3: Implement `list_books`**

Add to `clients/surya-ocr/kitabim_client/api.py`, after `get_book_pages`:

```python
    def list_books(self, q: str = "", page: int = 1, page_size: int = 20) -> dict:
        response = httpx.get(
            f"{self.base_url}/books/",
            headers=self._headers(),
            params={"q": q, "page": page, "pageSize": page_size, "sortBy": "title"},
            timeout=30.0,
        )
        return self._check(response)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clients/surya-ocr && python -m pytest tests/kitabim_client/test_api.py -v`
Expected: all tests PASS (5 existing + 1 new)

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/kitabim_client/api.py clients/surya-ocr/tests/kitabim_client/test_api.py
git commit -m "feat(surya-ocr-client): add KitabimClient.list_books"
```

---

## Task 3: `preview/app_server.py` skeleton — state machine, landing page HTML, `/api/state`, `/api/reset`

**Files:**
- Create: `clients/surya-ocr/preview/app_server.py`
- Test: `clients/surya-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: nothing from other tasks yet.
- Produces (used by Tasks 4–8):
  - `AppState` dataclass: `client`, `work_root: Path`, `stage: str = "landing"`, `workdir: Optional[OcrWorkDir] = None`, `error: Optional[str] = None`
  - `create_landing_app(client, work_root: Path) -> FastAPI`
  - `_require_landing_stage(state: AppState) -> None` (raises `HTTPException(409, ...)` unless `state.stage == "landing"`)
  - `_require_active_workdir(state: AppState) -> None` (raises `HTTPException(409, ...)` if `state.workdir is None`)

- [ ] **Step 1: Write the failing tests**

Create `clients/surya-ocr/tests/preview/test_app_server.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from preview.app_server import create_landing_app


def test_index_returns_landing_page_html(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="landing"' in response.text
    assert 'id="processing"' in response.text
    assert 'id="review"' in response.text


def test_state_defaults_to_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing", "error": None}


def test_reset_from_landing_is_a_no_op(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'preview.app_server'`

- [ ] **Step 3: Write `preview/app_server.py`**

```python
from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from kitabim_client.api import KitabimClient
from engine.workdir import OcrWorkDir

_APP_HTML = """<!doctype html>
<html><head><title>Surya OCR Client</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; }
  section { display: none; }
  section.active { display: block; }
  .book-row { display: flex; gap: 1rem; align-items: center; border-bottom: 1px solid #ccc; padding: 0.5rem 0; }
  .book-row .title { flex: 1; }
  .progress-bar { background: #eee; height: 1rem; border-radius: 4px; overflow: hidden; max-width: 400px; }
  .progress-bar-fill { background: #4a90d9; height: 100%; width: 0%; }
  .page { display: flex; gap: 1rem; border-bottom: 1px solid #ccc; padding: 0.75rem 0; }
  .page img { max-width: 300px; }
  .page textarea { flex: 1; min-height: 200px; }
  .error { color: #b00020; }
  button { margin: 0.25rem; }
</style>
</head><body>
<h1>Surya OCR Client</h1>

<section id="landing">
  <h2>Correct an existing Kitabim book</h2>
  <input type="text" id="bookSearch" placeholder="Search by title or author...">
  <div id="bookResults"></div>

  <h2>OCR a new local PDF</h2>
  <form id="uploadForm">
    <input type="file" id="uploadFile" accept="application/pdf" required>
    <button type="submit">Start OCR</button>
  </form>
  <p id="landingError" class="error"></p>
</section>

<section id="processing">
  <h2>Processing...</h2>
  <div class="progress-bar"><div class="progress-bar-fill" id="progressFill"></div></div>
  <p id="progressLabel"></p>
</section>

<section id="review">
  <div>
    <button onclick="backToLibrary()">&larr; Back to library</button>
    <button onclick="redoSelected()">Redo selected pages</button>
    <button onclick="redoAll()">Redo whole book</button>
    <button onclick="push()">Push to Kitabim</button>
  </div>
  <div id="pages"></div>
</section>

<script>
const sections = {
  landing: document.getElementById('landing'),
  processing: document.getElementById('processing'),
  review: document.getElementById('review'),
};
function showSection(name) {
  for (const key in sections) sections[key].classList.toggle('active', key === name);
}

let searchTimer = null;
document.getElementById('bookSearch').addEventListener('input', (e) => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => searchBooks(e.target.value), 300);
});

async function searchBooks(q) {
  const res = await fetch('/api/books?q=' + encodeURIComponent(q));
  const body = await res.json();
  const container = document.getElementById('bookResults');
  container.innerHTML = '';
  for (const b of body.books) {
    const row = document.createElement('div');
    row.className = 'book-row';
    row.innerHTML = `<span class="title">${b.title} — ${b.author} (${b.totalPages}p, ${b.ocrMilestone})</span><button>Correct this book</button>`;
    row.querySelector('button').onclick = () => startExisting(b.id);
    container.appendChild(row);
  }
}

async function startExisting(bookId) {
  const res = await fetch('/api/start/existing', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({bookId: bookId}),
  });
  if (!res.ok) { showLandingError(await res.text()); return; }
  const body = await res.json();
  if (body.stage === 'review') { showSection('review'); loadPages(); }
}

document.getElementById('uploadForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById('uploadFile');
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);
  const res = await fetch('/api/start/upload', {method: 'POST', body: formData});
  if (!res.ok) { showLandingError(await res.text()); return; }
  showSection('processing');
  pollProgress();
});

function showLandingError(text) {
  document.getElementById('landingError').textContent = text;
}

async function pollProgress() {
  const res = await fetch('/api/pages');
  const pages = await res.json();
  const total = pages.length;
  const done = pages.filter(p => p.status !== 'pending').length;
  document.getElementById('progressLabel').textContent = done + ' / ' + total + ' pages';
  document.getElementById('progressFill').style.width = total ? ((done / total) * 100) + '%' : '0%';

  const stateRes = await fetch('/api/state');
  const state = await stateRes.json();
  if (state.stage === 'review') { showSection('review'); loadPages(); return; }
  if (state.stage === 'error') { showSection('landing'); showLandingError(state.error || 'Processing failed'); return; }
  setTimeout(pollProgress, 1000);
}

async function loadPages() {
  const res = await fetch('/api/pages');
  const pages = await res.json();
  const container = document.getElementById('pages');
  container.innerHTML = '';
  for (const p of pages) {
    const div = document.createElement('div');
    div.className = 'page';
    div.innerHTML = `
      <input type="checkbox" class="select" value="${p.pageNumber}">
      <img src="/api/pages/${p.pageNumber}/image">
      <textarea data-page="${p.pageNumber}">${p.text}</textarea>
    `;
    container.appendChild(div);
  }
}
function selectedPageNumbers() {
  return Array.from(document.querySelectorAll('.select:checked')).map(c => parseInt(c.value));
}
function allPageNumbers() {
  return Array.from(document.querySelectorAll('.select')).map(c => parseInt(c.value));
}
async function redoSelected() {
  await fetch('/api/pages/redo', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pageNumbers: selectedPageNumbers()}),
  });
  loadPages();
}
async function redoAll() {
  await fetch('/api/pages/redo', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pageNumbers: allPageNumbers()}),
  });
  loadPages();
}
async function push() {
  const res = await fetch('/api/push', {method: 'POST'});
  const body = await res.json();
  alert('Push result: ' + JSON.stringify(body));
}
async function backToLibrary() {
  await fetch('/api/reset', {method: 'POST'});
  document.getElementById('bookResults').innerHTML = '';
  document.getElementById('landingError').textContent = '';
  showSection('landing');
}

async function init() {
  const res = await fetch('/api/state');
  const state = await res.json();
  if (state.stage === 'processing') { showSection('processing'); pollProgress(); }
  else if (state.stage === 'review') { showSection('review'); loadPages(); }
  else {
    showSection('landing');
    searchBooks('');
    if (state.error) showLandingError(state.error);
  }
}
init();
</script>
</body></html>"""


@dataclass
class AppState:
    client: KitabimClient
    work_root: Path
    stage: str = "landing"
    workdir: Optional[OcrWorkDir] = None
    error: Optional[str] = None


def _require_landing_stage(state: AppState) -> None:
    if state.stage != "landing":
        raise HTTPException(
            status_code=409, detail="A book is already active; reset first"
        )


def _require_active_workdir(state: AppState) -> None:
    if state.workdir is None:
        raise HTTPException(status_code=409, detail="No active book")


def create_landing_app(client: KitabimClient, work_root: Path) -> FastAPI:
    state = AppState(client=client, work_root=work_root)
    app = FastAPI()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return _APP_HTML

    @app.get("/api/state")
    def get_state():
        return {"stage": state.stage, "error": state.error}

    @app.post("/api/reset")
    def reset():
        if state.stage == "processing":
            raise HTTPException(
                status_code=409, detail="Cannot reset while processing"
            )
        state.workdir = None
        state.stage = "landing"
        state.error = None
        return {"stage": "landing"}

    return app


def serve_app(
    client: KitabimClient, work_root: Path, port: int = 8765, open_browser: bool = True
) -> None:
    app = create_landing_app(client, work_root)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/app_server.py clients/surya-ocr/tests/preview/test_app_server.py
git commit -m "feat(surya-ocr-client): add landing-page app skeleton with state machine"
```

---

## Task 4: `GET /api/books` route

**Files:**
- Modify: `clients/surya-ocr/preview/app_server.py`
- Test: `clients/surya-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: `KitabimClient.list_books(q, page, page_size)` (Task 2), `AppState`/`create_landing_app` (Task 3).
- Produces: nothing new consumed elsewhere.

- [ ] **Step 1: Write the failing test**

Add to `clients/surya-ocr/tests/preview/test_app_server.py`:

```python
def test_list_books_route_proxies_to_client(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.list_books.return_value = {
        "books": [{"id": "b1", "title": "Tarikh"}],
        "total": 1,
    }
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/books?q=tarikh&page=2")

    assert response.status_code == 200
    assert response.json() == {"books": [{"id": "b1", "title": "Tarikh"}], "total": 1}
    mock_client.list_books.assert_called_once_with(q="tarikh", page=2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py::test_list_books_route_proxies_to_client -v`
Expected: FAIL with 404 (`/api/books` doesn't exist)

- [ ] **Step 3: Add the route**

In `clients/surya-ocr/preview/app_server.py`, inside `create_landing_app`, add (after `reset`, before `return app`):

```python
    @app.get("/api/books")
    def list_books_route(q: str = "", page: int = 1):
        return state.client.list_books(q=q, page=page)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/app_server.py clients/surya-ocr/tests/preview/test_app_server.py
git commit -m "feat(surya-ocr-client): add /api/books search route to landing app"
```

---

## Task 5: `_start_existing_book` + `POST /api/start/existing`

**Files:**
- Modify: `clients/surya-ocr/preview/app_server.py`
- Test: `clients/surya-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: `OcrWorkDir.create`/`.load`/`.set_page`/`.save`/`.image_path` (`engine/workdir.py`, unchanged), `KitabimClient.download_book_pdf(book_id, dest) -> Path` and `.get_book_pages(book_id) -> list[dict]` (unchanged, existing), `AppState`/`_require_landing_stage` (Task 3).
- Produces (used by Task 8's manual QA only — no other task calls these directly):
  - `render_page_png(doc: "fitz.Document", page_number: int, zoom: float = RENDER_ZOOM) -> bytes`
  - `_start_existing_book(book_id: str, client: KitabimClient, work_root: Path) -> OcrWorkDir`

- [ ] **Step 1: Write the failing tests**

Add to `clients/surya-ocr/tests/preview/test_app_server.py` (add `import fitz` and `patch` to the existing imports at the top of the file):

```python
import fitz
from unittest.mock import MagicMock, patch

from preview.app_server import _start_existing_book, create_landing_app
from engine.workdir import OcrWorkDir


def _minimal_pdf_bytes(num_pages: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def test_start_existing_book_downloads_and_seeds_workdir_when_new(tmp_path: Path):
    work_root = tmp_path / "work"
    pdf_bytes = _minimal_pdf_bytes(2)
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(pdf_bytes) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "existing one", "isToc": False},
        {"pageNumber": 2, "text": "existing two", "isToc": True},
    ]

    workdir = _start_existing_book("book123", mock_client, work_root)

    assert workdir.book_id == "book123"
    assert workdir.total_pages == 2
    assert workdir.get_page(1).text == "existing one"
    assert workdir.get_page(1).status == "from_kitabim"
    assert workdir.get_page(2).is_toc is True
    assert workdir.image_path(1).exists()
    mock_client.download_book_pdf.assert_called_once()


def test_start_existing_book_resumes_without_redownloading(tmp_path: Path):
    work_root = tmp_path / "work"
    out_dir = work_root / "book123"
    wd = OcrWorkDir.create(
        out_dir, source_pdf=out_dir / "book.pdf", total_pages=1, book_id="book123"
    )
    wd.set_page(1, text="already here", is_toc=False, confidence=1.0, status="from_kitabim")
    wd.save()
    mock_client = MagicMock()

    workdir = _start_existing_book("book123", mock_client, work_root)

    assert workdir.get_page(1).text == "already here"
    mock_client.download_book_pdf.assert_not_called()
    mock_client.get_book_pages.assert_not_called()


def test_start_existing_route_flips_stage_to_review(tmp_path: Path):
    pdf_bytes = _minimal_pdf_bytes(1)
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(pdf_bytes) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "hi", "isToc": False}
    ]
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)

    response = client.post("/api/start/existing", json={"bookId": "book123"})

    assert response.status_code == 200
    assert response.json() == {"stage": "review"}
    assert client.get("/api/state").json()["stage"] == "review"


def test_start_existing_route_rejects_when_not_landing(tmp_path: Path):
    mock_client = MagicMock()
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/reset")  # no-op, still landing
    # force out of landing via a first successful start
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [{"pageNumber": 1, "text": "hi"}]
    client.post("/api/start/existing", json={"bookId": "book123"})

    response = client.post("/api/start/existing", json={"bookId": "otherbook"})

    assert response.status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v -k start_existing`
Expected: FAIL (`ImportError: cannot import name '_start_existing_book'`, then 404s once that's fixed)

- [ ] **Step 3: Implement `render_page_png`, `_start_existing_book`, and the route**

In `clients/surya-ocr/preview/app_server.py`:

Add `import fitz` and `from pydantic import BaseModel` to the imports at the top of the file (the `fastapi` import line already has `FastAPI, HTTPException` from Task 3 — leave it as-is).

Add module-level constant and functions (after the `_APP_HTML` constant, before `AppState`):

```python
RENDER_ZOOM = 1.5


def render_page_png(
    doc: "fitz.Document", page_number: int, zoom: float = RENDER_ZOOM
) -> bytes:
    page = doc.load_page(page_number - 1)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    return pix.tobytes("png")


def _start_existing_book(
    book_id: str, client: KitabimClient, work_root: Path
) -> OcrWorkDir:
    out_dir = work_root / book_id
    if (out_dir / "book.json").exists():
        return OcrWorkDir.load(out_dir)

    pdf_path = out_dir / "book.pdf"
    out_dir.mkdir(parents=True, exist_ok=True)
    client.download_book_pdf(book_id, pdf_path)

    existing_pages = client.get_book_pages(book_id)
    doc = fitz.open(pdf_path)

    workdir = OcrWorkDir.create(
        out_dir, source_pdf=pdf_path, total_pages=len(doc), book_id=book_id
    )
    for page in existing_pages:
        workdir.image_path(page["pageNumber"]).write_bytes(
            render_page_png(doc, page["pageNumber"])
        )
        workdir.set_page(
            page["pageNumber"],
            text=page.get("text") or "",
            is_toc=bool(page.get("isToc")),
            confidence=1.0,
            status="from_kitabim",
        )
    workdir.save()
    return workdir


class StartExistingRequest(BaseModel):
    bookId: str
```

Add the route inside `create_landing_app` (after `list_books_route`, before `return app`):

```python
    @app.post("/api/start/existing")
    def start_existing(body: StartExistingRequest):
        _require_landing_stage(state)
        try:
            state.workdir = _start_existing_book(
                body.bookId, state.client, state.work_root
            )
        except Exception as exc:
            state.stage = "error"
            state.error = str(exc)
            raise HTTPException(status_code=502, detail=str(exc))
        state.stage = "review"
        state.error = None
        return {"stage": "review"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/app_server.py clients/surya-ocr/tests/preview/test_app_server.py
git commit -m "feat(surya-ocr-client): add existing-book start route with resume support"
```

---

## Task 6: `_create_upload_workdir` + `_run_ocr_background` + `POST /api/start/upload`

**Files:**
- Modify: `clients/surya-ocr/preview/app_server.py`
- Test: `clients/surya-ocr/tests/preview/test_app_server.py`
- Modify: `clients/surya-ocr/requirements.txt` (add `python-multipart`, required by FastAPI's `UploadFile`/`File`)

**Interfaces:**
- Consumes: `render_page_png` (Task 5), `AppState`/`_require_landing_stage`/`_require_active_workdir` (Task 3), `engine.recognize.{LowConfidenceOcrError, get_recognition_predictor, ocr_page_with_surya}` (unchanged), `list_pages_response` (Task 1).
- Produces: `_start_background_task(coro) -> None` — thin wrapper around `asyncio.create_task`, overridden in tests so HTTP-level tests don't depend on real background-task timing.

> **Execution note:** the `test_start_upload_route_creates_pending_pages_and_schedules_background_task` test below needs `GET /api/pages` to observe the pre-populated pending pages, but that route was originally scheduled for Task 7. Pulled it forward here: `GET /api/pages` (using `list_pages_response` from Task 1) is added in this task instead, and Task 7 below only adds the remaining three routes (image/redo/push).

- [ ] **Step 1: Write the failing tests**

Add to `clients/surya-ocr/tests/preview/test_app_server.py` (add `AsyncMock` to the `unittest.mock` import and `import asyncio` at the top):

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from engine.recognize import LowConfidenceOcrError
from preview.app_server import AppState, _create_upload_workdir, _run_ocr_background


def test_create_upload_workdir_pre_populates_pending_pages(tmp_path: Path):
    work_root = tmp_path / "work"
    pdf_bytes = _minimal_pdf_bytes(3)

    workdir = _create_upload_workdir(pdf_bytes, work_root)

    assert workdir.total_pages == 3
    assert workdir.book_id is None
    for page_number in (1, 2, 3):
        page = workdir.get_page(page_number)
        assert page.status == "pending"
        assert page.text == ""
        assert workdir.image_path(page_number).exists()


def test_create_upload_workdir_rejects_invalid_pdf(tmp_path: Path):
    work_root = tmp_path / "work"

    with pytest.raises(Exception):
        _create_upload_workdir(b"not a pdf", work_root)

    assert not work_root.exists()


async def test_run_ocr_background_ocrs_every_page_then_marks_review(tmp_path: Path):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(2), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir
    state.stage = "processing"

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.app_server.ocr_page_with_surya",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    assert workdir.get_page(1).text == "text one"
    assert workdir.get_page(1).status == "ocrd"
    assert workdir.get_page(2).text == "text two"
    assert state.stage == "review"


async def test_run_ocr_background_flags_failed_page_and_continues(tmp_path: Path):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(2), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.app_server.ocr_page_with_surya",
            AsyncMock(side_effect=[LowConfidenceOcrError("bad page"), "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    assert workdir.get_page(1).status == "failed"
    assert "bad page" in workdir.get_page(1).error
    assert workdir.get_page(2).text == "text two"
    assert state.stage == "review"


async def test_run_ocr_background_sets_error_stage_on_unexpected_failure(tmp_path: Path):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(1), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir

    with patch(
        "preview.app_server.get_recognition_predictor",
        AsyncMock(side_effect=RuntimeError("model load failed")),
    ):
        await _run_ocr_background(workdir, state)

    assert state.stage == "error"
    assert "model load failed" in state.error


def test_start_upload_route_creates_pending_pages_and_schedules_background_task(
    tmp_path: Path,
):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    pdf_bytes = _minimal_pdf_bytes(2)

    with patch("preview.app_server._start_background_task") as mock_start:
        response = client.post(
            "/api/start/upload",
            files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json() == {"stage": "processing"}
    mock_start.assert_called_once()
    assert client.get("/api/state").json()["stage"] == "processing"
    pages = client.get("/api/pages").json()
    assert len(pages) == 2
    assert all(p["status"] == "pending" for p in pages)


def test_start_upload_route_rejects_invalid_pdf(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.post(
        "/api/start/upload",
        files={"file": ("book.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert client.get("/api/state").json()["stage"] == "landing"


def test_start_upload_route_rejects_when_not_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    with patch("preview.app_server._start_background_task"):
        client.post(
            "/api/start/upload",
            files={"file": ("book.pdf", _minimal_pdf_bytes(1), "application/pdf")},
        )

    response = client.post(
        "/api/start/upload",
        files={"file": ("book.pdf", _minimal_pdf_bytes(1), "application/pdf")},
    )

    assert response.status_code == 409
```

You'll also need `import pytest` at the top of the test file if it isn't already there (it is, from Task 5's usage isn't required, so add it explicitly).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v -k "upload or run_ocr_background"`
Expected: FAIL (`ImportError`, then 404s / 422s once imports are fixed)

- [ ] **Step 3: Implement**

In `clients/surya-ocr/preview/app_server.py`, add imports:

```python
import asyncio
import time

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_surya,
)
```

Update the `fastapi` import line to add `File` and `UploadFile`:

```python
from fastapi import FastAPI, File, HTTPException, UploadFile
```

Add functions (after `_start_existing_book`/`StartExistingRequest`, before `AppState`):

```python
def _create_upload_workdir(pdf_bytes: bytes, work_root: Path) -> OcrWorkDir:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    out_dir = work_root / f"upload-{int(time.time() * 1000)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "book.pdf"
    pdf_path.write_bytes(pdf_bytes)

    workdir = OcrWorkDir.create(out_dir, source_pdf=pdf_path, total_pages=total_pages)
    for page_number in range(1, total_pages + 1):
        workdir.image_path(page_number).write_bytes(render_page_png(doc, page_number))
        workdir.set_page(
            page_number, text="", is_toc=False, confidence=0.0, status="pending"
        )
    workdir.save()
    return workdir


async def _run_ocr_background(workdir: OcrWorkDir, state: "AppState") -> None:
    try:
        doc = fitz.open(workdir.source_pdf)
        predictor = await get_recognition_predictor()
        for page_number in range(1, workdir.total_pages + 1):
            fitz_page = doc.load_page(page_number - 1)
            try:
                text = await ocr_page_with_surya(fitz_page, predictor)
                workdir.set_page(
                    page_number, text=text, is_toc=False, confidence=1.0, status="ocrd"
                )
            except LowConfidenceOcrError as exc:
                workdir.set_page(
                    page_number,
                    text="",
                    is_toc=False,
                    confidence=0.0,
                    status="failed",
                    error=str(exc),
                )
            workdir.save()
        state.stage = "review"
    except Exception as exc:
        state.stage = "error"
        state.error = str(exc)


def _start_background_task(coro) -> None:
    asyncio.create_task(coro)
```

Note: `_create_upload_workdir` and `_run_ocr_background` reference `AppState`, which is defined further down in the file — Python resolves this fine at call time since `_run_ocr_background`'s type hint is a string literal (`"AppState"`) and the actual reference to `state.stage`/`state.error` only happens when the function runs, by which point the module is fully loaded. No reordering needed.

Add the route inside `create_landing_app` (after `start_existing`, before `return app`):

```python
    @app.post("/api/start/upload")
    async def start_upload(file: UploadFile = File(...)):
        _require_landing_stage(state)
        pdf_bytes = await file.read()
        try:
            workdir = await asyncio.to_thread(
                _create_upload_workdir, pdf_bytes, state.work_root
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Not a valid PDF: {exc}")
        state.workdir = workdir
        state.stage = "processing"
        state.error = None
        _start_background_task(_run_ocr_background(workdir, state))
        return {"stage": "processing"}
```

Add `python-multipart` to `clients/surya-ocr/requirements.txt` (after `fastapi`):

```
python-multipart
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/app_server.py clients/surya-ocr/tests/preview/test_app_server.py clients/surya-ocr/requirements.txt
git commit -m "feat(surya-ocr-client): add local-PDF upload route with background OCR"
```

---

## Task 7: Mount review routes (`/api/pages`, `/api/pages/{n}/image`, `/api/pages/redo`, `/api/push`) on the landing app

**Files:**
- Modify: `clients/surya-ocr/preview/app_server.py`
- Test: `clients/surya-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: `list_pages_response`, `get_page_image_bytes`, `redo_pages_response`, `push_response`, `RedoRequest` (all from `preview/server.py`, Task 1); `_require_active_workdir` (Task 3).

- [ ] **Step 1: Write the failing tests**

Add to `clients/surya-ocr/tests/preview/test_app_server.py`:

```python
def test_pages_routes_require_an_active_workdir(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    assert client.get("/api/pages").status_code == 409
    assert client.post("/api/pages/redo", json={"pageNumbers": [1]}).status_code == 409
    assert client.post("/api/push").status_code == 409


def test_pages_routes_work_once_a_book_is_active(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "hi", "isToc": False}
    ]
    mock_client.push_page_correction.return_value = {"status": "page_updated"}
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/start/existing", json={"bookId": "book123"})

    pages = client.get("/api/pages").json()
    assert pages[0]["text"] == "hi"

    image_response = client.get("/api/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.content.startswith(b"\x89PNG")

    push_response = client.post("/api/push")
    assert push_response.status_code == 200
    mock_client.push_page_correction.assert_called_once()


def test_back_to_library_clears_active_workdir(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [{"pageNumber": 1, "text": "hi"}]
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/start/existing", json={"bookId": "book123"})

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert client.get("/api/state").json()["stage"] == "landing"
    assert client.get("/api/pages").status_code == 409
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v -k "pages_routes or back_to_library"`
Expected: FAIL with 404s (routes don't exist yet)

- [ ] **Step 3: Add the routes**

In `clients/surya-ocr/preview/app_server.py` (`GET /api/pages` was already added in Task 6, per that task's execution note — this task adds the remaining three):

Update the `fastapi.responses` import line to add `Response` (it already imports `HTMLResponse` from Task 3):

```python
from fastapi.responses import HTMLResponse, Response
```

Update the `preview.server` import line (it already imports `list_pages_response` from Task 6) to add the rest of the review-route helpers:

```python
from preview.server import (
    RedoRequest,
    get_page_image_bytes,
    list_pages_response,
    push_response,
    redo_pages_response,
)
```

Add routes inside `create_landing_app` (after `list_pages`, before `return app`):

```python
    @app.get("/api/pages/{page_number}/image")
    def get_page_image(page_number: int):
        _require_active_workdir(state)
        return Response(
            content=get_page_image_bytes(state.workdir, page_number),
            media_type="image/png",
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        _require_active_workdir(state)
        return await redo_pages_response(state.workdir, body.pageNumbers)

    @app.post("/api/push")
    def push():
        _require_active_workdir(state)
        return push_response(state.workdir, state.client)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/preview/test_app_server.py -v`
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add clients/surya-ocr/preview/app_server.py clients/surya-ocr/tests/preview/test_app_server.py
git commit -m "feat(surya-ocr-client): mount review routes on the landing app"
```

---

## Task 8: `cli.py app` command + remove `ocr`/`correct` + update README

**Files:**
- Modify: `clients/surya-ocr/cli.py`
- Modify: `clients/surya-ocr/tests/test_cli.py`
- Modify: `clients/surya-ocr/README.md`

**Interfaces:**
- Consumes: `preview.app_server.serve_app(client: KitabimClient, work_root: Path, port: int = 8765, open_browser: bool = True) -> None` (Task 3).

- [ ] **Step 1: Write the failing tests**

In `clients/surya-ocr/tests/test_cli.py`, replace the whole file with:

```python
import os
from pathlib import Path
from unittest.mock import patch

import pytest

import cli


def test_build_parser_app_command():
    parser = cli.build_parser()
    args = parser.parse_args(["app"])
    assert args.command == "app"


def test_build_parser_preview_command():
    parser = cli.build_parser()
    args = parser.parse_args(["preview", "workdir"])
    assert args.command == "preview"
    assert args.workdir == "workdir"


def test_build_parser_push_command():
    parser = cli.build_parser()
    args = parser.parse_args(["push", "workdir", "--base-url", "http://x"])
    assert args.command == "push"
    assert args.base_url == "http://x"


def test_cmd_app_requires_kitabim_base_url_env_var(monkeypatch):
    monkeypatch.delenv("KITABIM_BASE_URL", raising=False)
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with pytest.raises(SystemExit, match="KITABIM_BASE_URL"):
        cli.cmd_app()


def test_cmd_app_requires_kitabim_work_dir_env_var(monkeypatch):
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.delenv("KITABIM_WORK_DIR", raising=False)

    with pytest.raises(SystemExit, match="KITABIM_WORK_DIR"):
        cli.cmd_app()


def test_cmd_app_starts_server_with_env_config(monkeypatch):
    monkeypatch.setenv("KITABIM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("KITABIM_WORK_DIR", "/tmp/work")

    with patch("cli.serve_app") as mock_serve_app:
        cli.cmd_app()

    mock_serve_app.assert_called_once()
    client_arg, work_root_arg = mock_serve_app.call_args.args
    assert isinstance(client_arg, cli.KitabimClient)
    assert client_arg.base_url == "http://localhost:8000"
    assert work_root_arg == Path("/tmp/work")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd clients/surya-ocr && python -m pytest tests/test_cli.py -v`
Expected: FAIL — `argparse` errors on `"app"` (unrecognized command) and `AttributeError: module 'cli' has no attribute 'cmd_app'`

- [ ] **Step 3: Rewrite `cli.py`**

Replace the full contents of `clients/surya-ocr/cli.py`:

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimClient
from preview.app_server import serve_app
from preview.server import serve

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "surya-ocr-client" / "token.json"


def cmd_app() -> None:
    base_url = os.environ.get("KITABIM_BASE_URL")
    if not base_url:
        raise SystemExit("KITABIM_BASE_URL environment variable is required")
    work_dir = os.environ.get("KITABIM_WORK_DIR")
    if not work_dir:
        raise SystemExit("KITABIM_WORK_DIR environment variable is required")

    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
    serve_app(client, Path(work_dir))


def cmd_preview(workdir_path: Path, base_url: str | None) -> None:
    workdir = OcrWorkDir.load(workdir_path)
    client = (
        KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
        if base_url
        else None
    )
    serve(workdir, client=client)


def cmd_push(workdir_path: Path, base_url: str) -> None:
    workdir = OcrWorkDir.load(workdir_path)
    client = KitabimClient(base_url=base_url, config_path=DEFAULT_CONFIG_PATH)
    if workdir.book_id is None:
        result = client.push_new_book(workdir.source_pdf, workdir.all_pages())
    else:
        for page in workdir.all_pages():
            client.push_page_correction(workdir.book_id, page)
        result = {"status": "corrections_pushed", "count": len(workdir.all_pages())}
    print(result)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local Surya OCR client for Kitabim")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser(
        "app",
        help=(
            "Open the book-picker landing page (correct an existing Kitabim book "
            "or OCR a new local PDF). Reads KITABIM_BASE_URL and KITABIM_WORK_DIR "
            "from the environment."
        ),
    )

    preview_parser = sub.add_parser(
        "preview", help="Reopen the preview UI for an existing work directory"
    )
    preview_parser.add_argument("workdir")
    preview_parser.add_argument("--base-url")

    push_parser = sub.add_parser(
        "push", help="Push a work directory's results to Kitabim without opening the UI"
    )
    push_parser.add_argument("workdir")
    push_parser.add_argument("--base-url", required=True)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "app":
        cmd_app()
    elif args.command == "preview":
        cmd_preview(Path(args.workdir), args.base_url)
    elif args.command == "push":
        cmd_push(Path(args.workdir), args.base_url)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd clients/surya-ocr && python -m pytest tests/test_cli.py -v`
Expected: all 6 tests PASS

- [ ] **Step 5: Run the full client test suite**

Run: `cd clients/surya-ocr && python -m pytest -q`
Expected: all tests PASS (no leftover references to removed `cmd_ocr`/`cmd_correct`/`render_page_png` in `cli.py`)

- [ ] **Step 6: Update `README.md`**

Replace the `## Usage` section of `clients/surya-ocr/README.md` with:

```markdown
## Usage

    export KITABIM_BASE_URL=https://api.kitabim.ai
    export KITABIM_WORK_DIR=~/surya-ocr-work

    python cli.py app                              # open the book picker in your browser
    python cli.py preview <workdir>                 # reopen a previous session directly
    python cli.py push <workdir> --base-url https://api.kitabim.ai

`app` opens a landing page where you can search for and pick an existing
Kitabim book to correct, or upload a new local PDF to OCR from scratch —
progress and the review UI (redo pages, push to Kitabim) both happen in
the same browser tab. `KITABIM_WORK_DIR` is where each book's local OCR
session (images, extracted text, review state) is stored between runs.

See `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` and
`docs/superpowers/specs/2026-08-30-surya-ocr-client-landing-page-design.md`
in the main kitabim-ai repo for the full design.
```

- [ ] **Step 7: Commit**

```bash
git add clients/surya-ocr/cli.py clients/surya-ocr/tests/test_cli.py clients/surya-ocr/README.md
git commit -m "feat(surya-ocr-client): replace ocr/correct subcommands with app landing page"
```

---

## Task 9: Manual end-to-end verification

This client drives a real browser UI and a real local Surya model — automated tests cover all the logic, but the actual click-through needs a human (or an agent with a real backend + GPU/CPU headroom to run Surya). Perform this against a local Kitabim dev backend.

- [ ] **Step 1: Set up environment**

```bash
cd clients/surya-ocr
source ../../venv/bin/activate   # or your own venv per README's Setup section
export KITABIM_BASE_URL=http://localhost:30800
export KITABIM_WORK_DIR=/tmp/surya-ocr-work
```

Ensure the local dev backend is running (`./deploy/local/rebuild-and-restart.sh backend` from the repo root if it isn't).

- [ ] **Step 2: Launch and log in**

```bash
python cli.py app
```

Expected: browser opens to `http://127.0.0.1:8765/` showing the landing page (search box + upload form). The first action that needs auth (a book search or an upload) triggers the existing lazy OAuth login flow in a new tab.

- [ ] **Step 3: Verify the "correct an existing book" flow**

Type a few characters of an existing book's title into the search box. Expected: matching rows appear within ~1s, each showing title/author/page count/OCR milestone. Click "Correct this book" on one. Expected: the page switches directly to the review section (no progress bar — this path has no OCR to run) showing that book's pages and existing text.

Click "← Back to library". Expected: the page returns to the landing section, and a fresh `GET /api/state` shows `"stage": "landing"`.

- [ ] **Step 4: Verify the "new local PDF" flow**

Choose a short (1-3 page) local PDF via the upload form and click "Start OCR". Expected: the page switches to the processing section, a progress bar advances as pages complete (e.g. "1 / 2 pages" → "2 / 2 pages"), and once done it automatically switches to the review section with each page's OCR'd text and rendered image visible.

- [ ] **Step 5: Verify redo and push**

From the review section: select one page's checkbox and click "Redo selected pages" — expect that page's text to change/refresh. Click "Push to Kitabim" — expect a JS alert showing the push result (`bookId`/`status` for a new book, or `corrections_pushed` count for a correction).

- [ ] **Step 6: Verify the double-start guard**

While a book is active (mid-processing or in review), open a second browser tab to `http://127.0.0.1:8765/api/start/existing` via `curl -X POST http://127.0.0.1:8765/api/start/existing -H 'Content-Type: application/json' -d '{"bookId": "anything"}'`. Expected: HTTP 409.

- [ ] **Step 7: Report results**

Note any deviations from the expected behavior above before considering this plan complete.

---

## Plan Self-Review Notes

- **Spec coverage:** every section of `docs/superpowers/specs/2026-08-30-surya-ocr-client-landing-page-design.md` maps to a task — landing screen (Tasks 3–4), starting processing for both flows (Tasks 5–6), progress display (Task 6's pending-page pre-population + Task 3's `_APP_HTML` polling JS), review screen "back to library" (Task 7), CLI/config changes (Task 8), error handling table (409 guards in Tasks 5–7, 400 on bad PDF in Task 6, error-stage on background failure in Task 6), testing (every task carries its own tests plus Task 9's manual pass).
- **Type consistency checked:** `AppState.workdir: Optional[OcrWorkDir]`, `_start_existing_book(...) -> OcrWorkDir`, `_create_upload_workdir(...) -> OcrWorkDir`, `_run_ocr_background(workdir: OcrWorkDir, state: AppState) -> None`, `serve_app(client: KitabimClient, work_root: Path, ...) -> None` are used consistently across Tasks 3, 5, 6, 8.
- **No placeholders:** every step has complete, runnable code — no "add error handling" or "similar to Task N" shortcuts.
