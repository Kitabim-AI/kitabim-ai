from __future__ import annotations

import webbrowser

import fitz
import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page_with_surya,
)
from engine.workdir import OcrWorkDir

_PAGE_HTML = """<!doctype html>
<html><head><title>Surya OCR Preview</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 1rem; }
  .page { display: flex; gap: 1rem; border-bottom: 1px solid #ccc; padding: 0.75rem 0; }
  .page img { max-width: 300px; }
  .page textarea { flex: 1; min-height: 200px; }
  button { margin: 0.25rem; }
</style>
</head><body>
<h1>Surya OCR Preview</h1>
<div>
  <button onclick="redoSelected()">Redo selected pages</button>
  <button onclick="redoAll()">Redo whole book</button>
  <button onclick="push()">Push to Kitabim</button>
</div>
<div id="pages"></div>
<script>
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
    body: JSON.stringify({pageNumbers: selectedPageNumbers()})
  });
  loadPages();
}
async function redoAll() {
  await fetch('/api/pages/redo', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({pageNumbers: allPageNumbers()})
  });
  loadPages();
}
async function push() {
  const res = await fetch('/api/push', {method: 'POST'});
  const body = await res.json();
  alert('Push result: ' + JSON.stringify(body));
}
loadPages();
</script>
</body></html>"""


class RedoRequest(BaseModel):
    pageNumbers: list[int]


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


def serve(
    workdir: OcrWorkDir, client, port: int = 8765, open_browser: bool = True
) -> None:
    app = create_app(workdir, client)
    if open_browser:
        webbrowser.open(f"http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port)
