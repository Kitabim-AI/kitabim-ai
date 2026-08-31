from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import Optional

import fitz
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page,
)
from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimAPIError

FONTS_DIR = Path(__file__).parent / "static" / "fonts"

_PAGE_HTML = """<!doctype html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kitabim OCR — بەتلەرنى كۆرۈش &amp; تەھرىرلەش</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Arabic:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    @font-face {
      font-family: "ALKATIP Basma";
      src: url("/fonts/alkatip-basma.woff2") format("woff2");
      font-display: swap;
    }

    @font-face {
      font-family: "ALKATIP Basma Tom";
      src: url("/fonts/alkatip-basma-tom.woff2") format("woff2");
      font-display: swap;
    }

    @font-face {
      font-family: "Adobe Arabic";
      src: url("/fonts/adobe-arabic-regular.woff2") format("woff2");
      font-display: swap;
    }

    @font-face {
      font-family: "KFGQPC Uthmanic Script HAFS";
      src: url("/fonts/kfgqpc-uthmanic-script-hafs.woff2") format("woff2");
      font-display: swap;
    }

    :root {
      --primary: #0369a1;
      --primary-hover: #0284c7;
      --primary-light: #e0f2fe;
      --accent-orange: #FF9800;
      --accent-emerald: #10b981;
      --accent-rose: #f43f5e;
      --slate-50: #f8fafc;
      --slate-100: #f1f5f9;
      --slate-200: #e2e8f0;
      --slate-300: #cbd5e1;
      --slate-400: #94a3b8;
      --slate-500: #64748b;
      --slate-600: #475569;
      --slate-700: #334155;
      --slate-800: #1e293b;
      --slate-900: #0f172a;
      --font-uyghur: "ALKATIP Basma", "ALKATIP Basma Tom", "Adobe Arabic", "UKIJ Tuz Tom", "Noto Sans Arabic", "Scheherazade New", ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      --font-ui: "Inter", ui-sans-serif, system-ui, -apple-system, sans-serif;
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: var(--font-uyghur);
    }

    input,
    textarea,
    select,
    button {
      font-family: var(--font-uyghur);
    }

    h1,
    h2,
    h3,
    h4,
    h5,
    h6 {
      font-family: var(--font-uyghur) !important;
      letter-spacing: 0 !important;
    }

    body {
      background: linear-gradient(135deg, #fef5e7 0%, #e8f6f8 50%, #f5f0fb 100%);
      background-attachment: fixed;
      color: var(--slate-800);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      line-height: 1.6;
      -webkit-font-smoothing: antialiased;
      direction: rtl;
    }

    header.app-header {
      position: sticky;
      top: 0;
      z-index: 50;
      background: rgba(255, 255, 255, 0.92);
      backdrop-filter: blur(20px);
      -webkit-backdrop-filter: blur(20px);
      border-bottom: 1px solid rgba(3, 105, 161, 0.12);
      padding: 0.75rem 1.5rem;
    }

    .header-content {
      max-width: 1600px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      text-decoration: none;
      color: inherit;
    }

    .brand-icon {
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      box-shadow: 0 4px 12px rgba(3, 105, 161, 0.3);
    }

    .brand-title {
      font-size: 1.2rem;
      font-weight: 700;
      color: var(--slate-900);
    }

    .brand-badge {
      font-size: 0.75rem;
      font-family: var(--font-ui);
      background: rgba(3, 105, 161, 0.1);
      color: var(--primary);
      padding: 0.15rem 0.6rem;
      border-radius: 9999px;
      border: 1px solid rgba(3, 105, 161, 0.2);
    }

    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.82rem;
      padding: 0.35rem 0.8rem;
      border-radius: 9999px;
      background: white;
      border: 1px solid var(--slate-200);
      color: var(--slate-600);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent-emerald);
      box-shadow: 0 0 8px rgba(16, 185, 129, 0.5);
    }

    main.main-container {
      max-width: 1600px;
      width: 100%;
      margin: 1.5rem auto;
      padding: 0 1.5rem;
      flex: 1;
    }

    .glass-panel {
      background: rgba(255, 255, 255, 0.88);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(3, 105, 161, 0.12);
      border-radius: 20px;
      box-shadow: 0 10px 25px -5px rgba(3, 105, 161, 0.08);
    }

    .glass-card {
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid rgba(3, 105, 161, 0.08);
      border-radius: 16px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }

    .review-toolbar {
      position: sticky;
      top: 68px;
      z-index: 40;
      padding: 0.8rem 1.2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }
    .toolbar-group {
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }

    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.55rem 1.1rem;
      border-radius: 12px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.2s;
      text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      color: white;
      box-shadow: 0 4px 12px rgba(3, 105, 161, 0.25);
    }
    .btn-secondary {
      background: white;
      border-color: var(--slate-300);
      color: var(--slate-700);
    }
    .btn-secondary:hover { background: var(--slate-50); }
    .btn-sm { padding: 0.35rem 0.75rem; font-size: 0.82rem; border-radius: 8px; }

    .pages-list {
      display: flex;
      flex-direction: column;
      gap: 1.5rem;
    }
    .page-card {
      padding: 1.5rem;
      border: 1px solid rgba(3, 105, 161, 0.12);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.92);
    }
    .page-card-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1rem;
      padding-bottom: 0.75rem;
      border-bottom: 1px solid var(--slate-100);
    }
    .page-card-body {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 1.5rem;
      align-items: start;
    }
    @media (max-width: 900px) {
      .page-card-body { grid-template-columns: 1fr; }
    }
    .page-image-wrap {
      border: 1px solid var(--slate-200);
      border-radius: 12px;
      overflow: hidden;
      background: var(--slate-900);
    }
    .page-image-wrap img { width: 100%; display: block; }
    .ocr-textarea {
      width: 100%;
      min-height: 480px;
      padding: 1.2rem;
      border-radius: 12px;
      border: 1.5px solid var(--slate-200);
      background: white;
      font-size: 1.15rem;
      line-height: 2;
      outline: none;
      resize: vertical;
      color: var(--slate-900);
      direction: rtl;
    }
    .ocr-textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(3, 105, 161, 0.1);
    }

    .milestone-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.25rem 0.7rem;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .milestone-ready { background: #dcfce7; color: #166534; }
    .milestone-failed { background: #fee2e2; color: #991b1b; }

    /* Modal */
    .modal-overlay {
      position: fixed;
      top: 0; left: 0; right: 0; bottom: 0;
      background: rgba(15, 23, 42, 0.6);
      backdrop-filter: blur(8px);
      z-index: 100;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1.5rem;
    }
    .modal-overlay.active { display: flex; }
    .modal-content {
      max-width: 520px;
      width: 100%;
      padding: 2rem;
      text-align: center;
    }
  </style>
</head>
<body>
  <header class="app-header">
    <div class="header-content">
      <div class="brand">
        <div class="brand-icon">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10"/></svg>
        </div>
        <div class="brand-title">Kitabim OCR <span class="brand-badge">ئالدىن كۆرۈش</span></div>
      </div>
      <div class="status-pill">
        <span class="status-dot"></span>
        <span>يەرلىك خىزمەت</span>
      </div>
    </div>
  </header>

  <main class="main-container">
    <div class="glass-panel review-toolbar">
      <div class="toolbar-group">
        <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; font-size: 0.9rem; font-weight: 600; padding: 0.4rem 0.8rem; background: var(--slate-100); border-radius: 10px;">
          <input type="checkbox" id="selectAllCheckbox" onchange="toggleSelectAll(this.checked)">
          ھەممىنى تاللاش
        </label>
        <span id="selectedCountBadge" class="status-pill" style="display: none;">0 بەت تاللاندى</span>
      </div>

      <div class="toolbar-group">
        <button class="btn btn-secondary" onclick="redoSelected()" id="redoSelectedBtn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/></svg>
          تاللانغاننى قايتا تونۇتۇش
        </button>
        <button class="btn btn-secondary" onclick="redoAll()" id="redoAllBtn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h7"/><line x1="16" y1="5" x2="22" y2="5"/><line x1="19" y1="2" x2="19" y2="8"/><circle cx="9" cy="9" r="2"/><path d="m21 15-3.086-3.086a2 2 0 0 0-2.828 0L6 21"/></svg>
          ھەممىنى قايتا تونۇتۇش
        </button>
        <button class="btn btn-primary" onclick="push()" id="pushBtn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242"/><path d="M12 12v9"/><path d="m16 16-4-4-4 4"/></svg>
          Kitabim غا يوللاش
        </button>
      </div>
    </div>

    <div id="pages" class="pages-list"></div>
  </main>

  <div id="pushModal" class="modal-overlay">
    <div class="glass-panel modal-content">
      <div style="width: 56px; height: 56px; border-radius: 50%; background: #dcfce7; color: #166534; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
      <h3 style="font-size: 1.3rem; font-weight: 800; color: var(--slate-900); margin-bottom: 0.5rem;">
        بۇلۇتقا مۇۋەپپەقىيەتلىك يوللاندى!
      </h3>
      <p id="pushModalMessage" style="color: var(--slate-600); font-size: 0.95rem; margin-bottom: 1.5rem;"></p>
      <button class="btn btn-primary" onclick="closePushModal()" style="width: 100%;">چۈشەندىم</button>
    </div>
  </div>

  <script>
    async function loadPages() {
      const res = await fetch('/api/pages');
      const pages = await res.json();
      const container = document.getElementById('pages');
      container.innerHTML = '';
      for (const p of pages) {
        const div = document.createElement('div');
        div.className = 'glass-card page-card';
        div.innerHTML = `
          <div class="page-card-header">
            <div style="display: flex; align-items: center; gap: 0.8rem;">
              <input type="checkbox" class="select" value="${p.pageNumber}" onchange="updateSelectedCount()" style="width: 18px; height: 18px; cursor: pointer;">
              <span style="font-weight: 700; font-size: 1.1rem; color: var(--slate-900);">بەت ${p.pageNumber}</span>
              <span class="milestone-badge ${p.status === 'failed' ? 'milestone-failed' : 'milestone-ready'}">
                ${p.status === 'from_kitabim' ? 'Kitabim دىن' : p.status === 'ocrd' ? 'OCR پۈتتى' : p.status === 'failed' ? 'مەغلۇپ بولدى' : p.status}
              </span>
            </div>
            <div style="display: flex; align-items: center; gap: 1rem;">
              <label style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; cursor: pointer; color: var(--slate-700);">
                <input type="checkbox" class="toc-toggle" data-page="${p.pageNumber}" ${p.isToc ? 'checked' : ''} onchange="toggleToc(${p.pageNumber}, this.checked)">
                مۇندەرىجە بەت
              </label>
              <button class="btn btn-secondary btn-sm" onclick="redoSinglePage(${p.pageNumber})">قايتا تونۇتۇش</button>
            </div>
          </div>
          <div class="page-card-body">
            <div class="page-image-wrap">
              <img src="/api/pages/${p.pageNumber}/image?v=${Date.now()}" alt="بەت ${p.pageNumber}" loading="lazy">
            </div>
            <div>
              <textarea class="ocr-textarea" data-page="${p.pageNumber}" oninput="autoSavePageText(${p.pageNumber}, this.value)">${escapeHtml(p.text || '')}</textarea>
            </div>
          </div>
        `;
        container.appendChild(div);
      }
      updateSelectedCount();
    }

    let saveTimeouts = {};
    function autoSavePageText(pageNumber, text) {
      clearTimeout(saveTimeouts[pageNumber]);
      saveTimeouts[pageNumber] = setTimeout(async () => {
        try {
          await fetch(`/api/pages/${pageNumber}/update`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text}),
          });
        } catch (e) {
          console.error('Failed to auto-save page', pageNumber, e);
        }
      }, 500);
    }

    async function toggleToc(pageNumber, isToc) {
      try {
        await fetch(`/api/pages/${pageNumber}/update`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({isToc: isToc}),
        });
      } catch (e) {
        console.error('Failed to update TOC flag', pageNumber, e);
      }
    }

    function selectedPageNumbers() {
      return Array.from(document.querySelectorAll('.select:checked')).map(c => parseInt(c.value));
    }
    function allPageNumbers() {
      return Array.from(document.querySelectorAll('.select')).map(c => parseInt(c.value));
    }

    function toggleSelectAll(checked) {
      document.querySelectorAll('.select').forEach(c => c.checked = checked);
      updateSelectedCount();
    }

    function updateSelectedCount() {
      const selected = selectedPageNumbers();
      const badge = document.getElementById('selectedCountBadge');
      if (selected.length > 0) {
        badge.style.display = 'inline-flex';
        badge.textContent = `${selected.length} بەت تاللاندى`;
      } else {
        badge.style.display = 'none';
      }
    }

    async function redoSinglePage(pageNum) {
      await fetch('/api/pages/redo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pageNumbers: [pageNum]}),
      });
      loadPages();
    }

    async function redoSelected() {
      const pages = selectedPageNumbers();
      if (!pages.length) { alert('ئالدى بىلەن قايتا تونۇتماقچى بولغان بەتلەرنى تاللاڭ'); return; }
      const btn = document.getElementById('redoSelectedBtn');
      btn.disabled = true;
      btn.textContent = 'قايتا تونۇتۇلۇۋاتىدۇ...';
      try {
        await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        await loadPages();
      } finally {
        btn.disabled = false;
        btn.textContent = 'تاللانغاننى قايتا تونۇتۇش';
      }
    }

    async function redoAll() {
      const pages = allPageNumbers();
      if (!pages.length) return;
      if (!confirm('پۈتۈن كىتابتىكى بارلىق بەتلەرنى قايتا تونۇتامسىز؟')) return;
      const btn = document.getElementById('redoAllBtn');
      btn.disabled = true;
      btn.textContent = 'قايتا تونۇتۇلۇۋاتىدۇ...';
      try {
        await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        await loadPages();
      } finally {
        btn.disabled = false;
        btn.textContent = 'ھەممىنى قايتا تونۇتۇش';
      }
    }

    async function push() {
      const btn = document.getElementById('pushBtn');
      btn.disabled = true;
      btn.textContent = 'يوللىنىۋاتىدۇ...';
      try {
        const res = await fetch('/api/push', {method: 'POST'});
        const body = await res.json();
        let message = 'مەشغۇلات مۇۋەپپەقىيەتلىك تاماملاندى: ' + JSON.stringify(body);
        if (body.count) {
          message = `${body.count} بەت تۈزىتىش Kitabim غا يوللاندى.`;
        }
        document.getElementById('pushModalMessage').textContent = message;
        document.getElementById('pushModal').classList.add('active');
      } catch (err) {
        alert('يوللاشتا خاتالىق كۆرۈلدى: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Kitabim غا يوللاش';
      }
    }

    function closePushModal() {
      document.getElementById('pushModal').classList.remove('active');
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    loadPages();
  </script>
</body>
</html>"""


class RedoRequest(BaseModel):
    pageNumbers: list[int]


class UpdatePageRequest(BaseModel):
    text: Optional[str] = None
    isToc: Optional[bool] = None


def list_pages_response(workdir: OcrWorkDir) -> list[dict]:
    return [
        {
            "pageNumber": p.page_number,
            "text": p.text,
            "isToc": p.is_toc,
            "confidence": p.confidence,
            "status": p.status,
            "error": p.error,
        }
        for p in workdir.all_pages()
    ]


def get_page_image_bytes(workdir: OcrWorkDir, page_number: int) -> bytes:
    return workdir.image_path(page_number).read_bytes()


def update_page_response(
    workdir: OcrWorkDir, page_number: int, body: UpdatePageRequest
) -> dict:
    try:
        page = workdir.get_page(page_number)
    except KeyError:
        raise HTTPException(status_code=404, detail="Page not found")

    text = body.text if body.text is not None else page.text
    is_toc = body.isToc if body.isToc is not None else page.is_toc
    status = "reviewed" if page.status != "failed" else "failed"

    workdir.set_page(
        page_number,
        text=text,
        is_toc=is_toc,
        confidence=page.confidence,
        status=status,
        error=page.error,
    )
    workdir.save()
    return {"status": "ok", "pageNumber": page_number}


async def redo_pages_response(
    workdir: OcrWorkDir, page_numbers: list[int], concurrency: int = 4
) -> list[dict]:
    doc = fitz.open(workdir.source_pdf)
    predictor = await get_recognition_predictor()
    sem = asyncio.Semaphore(max(1, concurrency))
    save_lock = asyncio.Lock()

    async def redo_one(page_number: int):
        async with sem:
            fitz_page = doc.load_page(page_number - 1)
            try:
                text = await ocr_page(fitz_page, predictor)
                async with save_lock:
                    workdir.set_page(
                        page_number,
                        text=text,
                        is_toc=False,
                        confidence=1.0,
                        status="ocrd",
                    )
                    workdir.save()
            except LowConfidenceOcrError as exc:
                try:
                    previous_text = workdir.get_page(page_number).text
                except KeyError:
                    previous_text = ""
                async with save_lock:
                    workdir.set_page(
                        page_number,
                        text=previous_text,
                        is_toc=False,
                        confidence=0.0,
                        status="failed",
                        error=str(exc),
                    )
                    workdir.save()

    tasks = [redo_one(p) for p in page_numbers]
    await asyncio.gather(*tasks)
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
    if client is None:
        raise HTTPException(
            status_code=400, detail="Cannot push without KitabimClient configured"
        )
    try:
        if workdir.book_id is None:
            return client.push_new_book(
                workdir.source_pdf,
                workdir.all_pages(),
                filename=workdir.original_filename,
            )
        results = []
        for page in workdir.all_pages():
            results.append(client.push_page_correction(workdir.book_id, page))
        return {"status": "corrections_pushed", "count": len(results)}
    except KitabimAPIError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def create_app(workdir: OcrWorkDir, client) -> FastAPI:
    app = FastAPI()

    @app.get("/fonts/{filename}")
    def serve_font(filename: str):
        font_path = FONTS_DIR / filename
        if not font_path.is_file():
            raise HTTPException(status_code=404, detail="Font not found")
        return FileResponse(font_path, media_type="font/woff2")

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
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        return await redo_pages_response(workdir, body.pageNumbers)

    @app.post("/api/pages/{page_number}/update")
    def update_page(page_number: int, body: UpdatePageRequest):
        return update_page_response(workdir, page_number, body)

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
