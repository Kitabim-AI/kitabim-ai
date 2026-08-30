from __future__ import annotations

import asyncio
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_surya,
)
from kitabim_client.api import KitabimClient
from engine.workdir import OcrWorkDir
from preview.server import (
    RedoRequest,
    get_page_image_bytes,
    list_pages_response,
    push_response,
    redo_pages_response,
)

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
            raise HTTPException(status_code=409, detail="Cannot reset while processing")
        state.workdir = None
        state.stage = "landing"
        state.error = None
        return {"stage": "landing"}

    @app.get("/api/books")
    def list_books_route(q: str = "", page: int = 1):
        return state.client.list_books(q=q, page=page)

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

    @app.get("/api/pages")
    def list_pages():
        _require_active_workdir(state)
        return list_pages_response(state.workdir)

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

    return app


def serve_app(
    client: KitabimClient, work_root: Path, port: int = 8765, open_browser: bool = True
) -> None:
    app = create_landing_app(client, work_root)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
