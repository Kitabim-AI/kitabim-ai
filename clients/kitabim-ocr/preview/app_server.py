from __future__ import annotations

import asyncio
import logging
import shutil
import socket
import threading
import time
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import fitz
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from backfill import (
    _append_page_checkpoint,
    acquire_surya_gpu_lock_async,
    backfill_single_book,
    prevent_macos_sleep,
    read_backfill_audit_log,
)
from engine.config import (
    get_configured_concurrency,
    get_configured_engine,
    get_configured_page_timeout,
    resolve_concurrency,
)
from engine.line_ends import apply_cross_page_dehyphenation, text_ends_with_hyphen
from engine.queue import BookQueueManager
from engine.recognize import (
    OCR_ENGINE_VERSION,
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page,
    pop_last_page_ocr_meta,
)
from engine.text_cleanup import is_toc_page
from engine.workdir import OcrWorkDir, PageState
from kitabim_client.api import KitabimClient
from locales.i18n import get_translations, get_translations_json
from preview.server import (
    RedoRequest,
    UpdatePageRequest,
    get_page_image_bytes,
    list_pages_response,
    push_response,
    redo_pages_response,
    update_page_response,
)

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).parent / "static" / "fonts"

_APP_HTML = """<!doctype html>
<html lang="ug" dir="rtl">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Kitabim OCR Client — يەرلىك OCR نازارەتچىسى</title>
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
      --primary-rgb: 3, 105, 161;
      --accent-orange: #FF9800;
      --accent-gold: #FFD54F;
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

    /* Traditional Uyghur Pattern Overlay */
    body::before {
      content: '';
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-image:
        radial-gradient(circle at 20% 20%, rgba(3, 105, 161, 0.05) 0%, transparent 40%),
        radial-gradient(circle at 80% 80%, rgba(255, 152, 0, 0.04) 0%, transparent 40%),
        radial-gradient(circle at 50% 50%, rgba(156, 39, 176, 0.03) 0%, transparent 50%);
      pointer-events: none;
      z-index: -1;
    }

    .uyghur-text {
      direction: rtl;
      font-variant-ligatures: common-ligatures contextual;
      font-feature-settings: "kern" 1, "liga" 1, "calt" 1, "ccmp" 1;
    }

    .latin-text {
      direction: ltr;
      font-family: var(--font-ui);
    }

    /* Glassmorphism Panels */
    .glass-panel {
      background: rgba(255, 255, 255, 0.88);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(3, 105, 161, 0.12);
      border-radius: 20px;
      box-shadow: 0 10px 25px -5px rgba(3, 105, 161, 0.08), 0 8px 10px -6px rgba(3, 105, 161, 0.04);
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    }

    .glass-card {
      background: rgba(255, 255, 255, 0.95);
      border: 1px solid rgba(3, 105, 161, 0.08);
      border-radius: 16px;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }

    /* Navigation Bar */
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
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      display: flex;
      align-items: center;
      justify-content: center;
      color: white;
      box-shadow: 0 4px 12px rgba(3, 105, 161, 0.3);
    }

    .brand-title {
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--slate-900);
      display: flex;
      align-items: center;
      gap: 0.5rem;
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

    .header-badges {
      display: flex;
      align-items: center;
      gap: 0.75rem;
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
      box-shadow: 0 2px 5px rgba(0,0,0,0.02);
    }

    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--slate-400);
    }
    .status-dot.active { background: var(--accent-emerald); box-shadow: 0 0 8px rgba(16, 185, 129, 0.5); }
    .status-dot.pulsing { background: var(--accent-orange); animation: pulse 1.5s infinite; }
    .status-dot.error { background: var(--accent-rose); }

    /* Steps Breadcrumbs */
    .steps-indicator {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 0.85rem;
      background: var(--slate-100);
      padding: 0.3rem 0.8rem;
      border-radius: 9999px;
    }
    .step-item {
      color: var(--slate-400);
      display: flex;
      align-items: center;
      gap: 0.3rem;
    }
    .step-item.active {
      color: var(--primary);
      font-weight: 700;
    }

    /* Main Container */
    main.main-container {
      max-width: 1600px;
      width: 100%;
      margin: 1.5rem auto;
      padding: 0 1.5rem 1.5rem 1.5rem;
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }

    section { display: none; }
    section.active { display: flex; flex-direction: column; flex: 1; animation: fadeIn 0.4s ease-out; min-height: 0; }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.4; transform: scale(1.2); }
    }
    @keyframes spin {
      to { transform: rotate(360deg); }
    }

    /* Section Tabs */
    .tab-bar {
      display: flex;
      gap: 0.5rem;
      background: rgba(3, 105, 161, 0.08);
      padding: 0.35rem;
      border-radius: 14px;
      margin-bottom: 1.5rem;
      max-width: 100%;
      width: fit-content;
      overflow-x: auto;
    }
    .tag-badge {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      font-size: 0.8rem;
      padding: 0.25rem 0.65rem;
      border-radius: 9999px;
      font-weight: 600;
    }
    .tag-badge.success {
      background: #dcfce7;
      color: #15803d;
      border: 1px solid #86efac;
    }
    .tag-badge.pending {
      background: #fef3c7;
      color: #b45309;
      border: 1px solid #fcd34d;
    }
    .tag-badge.idle {
      background: var(--slate-100);
      color: var(--slate-600);
      border: 1px solid var(--slate-200);
    }
    .tab-btn {
      flex: 0 0 auto;
      padding: 0.65rem 1.4rem;
      border: none;
      background: transparent;
      border-radius: 10px;
      color: var(--slate-600);
      font-size: 0.95rem;
      font-weight: 600;
      cursor: pointer;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      white-space: nowrap;
      transition: all 0.2s;
    }
    .tab-btn.active {
      background: white;
      color: var(--primary);
      box-shadow: 0 2px 8px rgba(3, 105, 161, 0.15);
    }

    /* Search & Stats Bar */
    .search-row {
      display: flex;
      gap: 1rem;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 1.5rem;
      flex-wrap: wrap;
    }
    .search-input-wrap {
      position: relative;
      flex: 1;
      max-width: 480px;
      min-width: 280px;
    }
    .search-input {
      width: 100%;
      padding: 0.8rem 2.8rem 0.8rem 2.5rem;
      border-radius: 14px;
      border: 2px solid rgba(3, 105, 161, 0.15);
      background: white;
      font-size: 1rem;
      outline: none;
      transition: all 0.2s;
      box-shadow: 0 2px 8px rgba(0,0,0,0.02);
    }
    .search-input:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 4px rgba(3, 105, 161, 0.12);
    }
    .search-icon {
      position: absolute;
      right: 1rem;
      top: 50%;
      transform: translateY(-50%);
      color: var(--primary);
      pointer-events: none;
    }
    .search-clear {
      position: absolute;
      left: 0.8rem;
      top: 50%;
      transform: translateY(-50%);
      border: none;
      background: none;
      color: var(--slate-400);
      cursor: pointer;
      padding: 0.2rem;
      display: none;
    }

    .count-pill {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.9rem;
      color: var(--primary);
      background: var(--primary-light);
      padding: 0.6rem 1.2rem;
      border-radius: 9999px;
      border: 1px solid rgba(3, 105, 161, 0.2);
    }

    /* Tables */
    .table-container {
      overflow: auto;
      max-inline-size: 100%;
      container-type: inline-size;
      border-radius: 16px;
      border: 1px solid rgba(3, 105, 161, 0.12);
      background: white;
    }
    table.books-table {
      width: 100%;
      border-collapse: separate;
      border-spacing: 0;
      text-align: right;
    }
    table.books-table thead {
      position: sticky;
      inset-block-start: 0;
      z-index: 1;
      background: #f3f9fc;
      border-bottom: 1px solid rgba(3, 105, 161, 0.12);
    }
    table.books-table th {
      padding: 1rem 1.25rem;
      font-size: 0.9rem;
      color: var(--primary);
      font-weight: 700;
    }
    table.books-table tbody tr {
      border-bottom: 1px solid var(--slate-100);
      transition: background 0.15s;
    }
    table.books-table tbody tr:hover {
      background: rgba(3, 105, 161, 0.03);
    }
    table.books-table td {
      padding: 1rem 1.25rem;
      font-size: 0.95rem;
      vertical-align: middle;
    }

    .book-title-cell {
      display: flex;
      align-items: center;
      gap: 0.8rem;
    }
    .book-avatar {
      width: 38px;
      height: 38px;
      border-radius: 10px;
      background: var(--primary-light);
      color: var(--primary);
      display: flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
    }
    .book-main-title {
      font-weight: 700;
      color: var(--slate-900);
      font-size: 1.05rem;
    }
    .book-sub-info {
      font-size: 0.8rem;
      color: var(--slate-500);
    }

    /* Milestone Badges */
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
    .milestone-in_progress { background: #fef3c7; color: #92400e; }
    .milestone-failed { background: #fee2e2; color: #991b1b; }
    .milestone-idle { background: var(--slate-100); color: var(--slate-600); }

    /* Action Buttons */
    .btn {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 0.5rem;
      padding: 0.6rem 1.2rem;
      border-radius: 12px;
      font-size: 0.9rem;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid transparent;
      transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
      text-decoration: none;
    }
    .btn-primary {
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      color: white;
      box-shadow: 0 4px 12px rgba(3, 105, 161, 0.25);
    }
    .btn-primary:hover {
      box-shadow: 0 6px 16px rgba(3, 105, 161, 0.35);
      transform: translateY(-1px);
    }
    .btn-secondary {
      background: white;
      border-color: var(--slate-300);
      color: var(--slate-700);
    }
    .btn-secondary:hover {
      background: var(--slate-50);
      border-color: var(--slate-400);
    }
    .btn-sm {
      padding: 0.4rem 0.8rem;
      font-size: 0.82rem;
      border-radius: 8px;
    }
    .btn-success {
      background: linear-gradient(135deg, #10b981, #059669);
      color: white;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
    }
    .btn-warning {
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: white;
      box-shadow: 0 4px 12px rgba(245, 158, 11, 0.25);
    }
    .btn-warning:hover {
      box-shadow: 0 6px 16px rgba(245, 158, 11, 0.35);
      transform: translateY(-1px);
    }
    .btn:disabled {
      opacity: 0.6;
      cursor: not-allowed;
      transform: none !important;
      box-shadow: none !important;
    }

    /* Drag & Drop Upload Zone */
    .upload-zone {
      border: 2px dashed rgba(3, 105, 161, 0.3);
      border-radius: 20px;
      padding: 3.5rem 2rem;
      text-align: center;
      background: rgba(255, 255, 255, 0.7);
      transition: all 0.25s;
      cursor: pointer;
      position: relative;
    }
    .upload-zone:hover, .upload-zone.dragover {
      border-color: var(--primary);
      background: var(--primary-light);
    }
    .upload-icon-wrap {
      width: 72px;
      height: 72px;
      border-radius: 20px;
      background: var(--primary-light);
      color: var(--primary);
      display: flex;
      align-items: center;
      justify-content: center;
      margin: 0 auto 1.25rem;
    }
    .file-input-hidden {
      position: absolute;
      top: 0; left: 0; width: 100%; height: 100%;
      opacity: 0;
      cursor: pointer;
    }
    .file-preview-card {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 1rem;
      background: white;
      border-radius: 14px;
      border: 1px solid var(--slate-200);
      margin-top: 1.5rem;
      max-width: 450px;
      margin-left: auto;
      margin-right: auto;
    }

    /* Monitoring / Processing Screen */
    .monitor-card {
      padding: 2rem;
      margin-bottom: 0;
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .progress-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 1rem;
      flex-shrink: 0;
    }
    .progress-track {
      background: var(--slate-100);
      height: 20px;
      border-radius: 10px;
      overflow: hidden;
      box-shadow: inset 0 2px 4px rgba(0,0,0,0.06);
      position: relative;
      flex-shrink: 0;
    }
    .progress-bar-fill {
      background: linear-gradient(90deg, #0369a1, #38bdf8, #10b981);
      height: 100%;
      width: 0%;
      border-radius: 10px;
      transition: width 0.4s ease-out;
    }
    .matrix-wrapper {
      margin-top: 1.5rem;
      flex: 1;
      display: flex;
      flex-direction: column;
      min-height: 0;
    }
    .page-matrix {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
      gap: 0.6rem;
      flex: 1;
      min-height: 250px;
      overflow-y: auto;
      padding: 0.75rem;
      border: 1px solid rgba(3, 105, 161, 0.08);
      border-radius: 14px;
      background: rgba(248, 250, 252, 0.6);
    }
    .matrix-tile {
      height: 54px;
      border-radius: 10px;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      font-size: 0.8rem;
      font-weight: 700;
      border: 1px solid var(--slate-200);
      background: white;
      transition: all 0.2s;
    }
    .matrix-tile.pending { background: var(--slate-100); color: var(--slate-400); }
    .matrix-tile.processing {
      background: #fef3c7;
      color: #b45309;
      border-color: #f59e0b;
      animation: pulse 1s infinite;
      box-shadow: 0 0 10px rgba(245, 158, 11, 0.4);
    }
    .matrix-tile.done { background: #dcfce7; color: #15803d; border-color: #86efac; }
    .matrix-tile.skipped { background: #e0f2fe; color: #0369a1; border-color: #7dd3fc; }
    .matrix-tile.failed { background: #fee2e2; color: #b91c1c; border-color: #fca5a5; }
    .matrix-tile.selected-tile {
      outline: 3px solid var(--primary);
      outline-offset: 1px;
      transform: translateY(-2px);
    }
    .matrix-tile.clickable {
      cursor: pointer;
    }
    .matrix-tile.clickable:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
      border-color: #10b981;
    }
    .backfill-sbs-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      align-items: stretch;
    }
    @media (max-width: 960px) {
      .backfill-sbs-grid {
        grid-template-columns: 1fr;
      }
    }

    /* Review Screen Layout */
    .review-toolbar {
      position: sticky;
      top: 72px;
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
      position: relative;
    }
    .page-image-wrap img {
      width: 100%;
      display: block;
      transition: transform 0.2s;
    }
    .page-editor-wrap {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
      height: 100%;
    }
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
      transition: border-color 0.2s;
    }
    .ocr-textarea:focus {
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(3, 105, 161, 0.1);
    }
    .error-banner {
      background: #fef2f2;
      border: 1px solid #fecaca;
      color: #991b1b;
      padding: 0.75rem 1rem;
      border-radius: 12px;
      margin-bottom: 1rem;
      display: flex;
      align-items: center;
      gap: 0.6rem;
    }

    /* Modal dialog */
    dialog:modal {
      overscroll-behavior: contain;
    }
    dialog::backdrop {
      overflow: hidden;
      overscroll-behavior: contain;
      background: rgba(15, 23, 42, 0.55);
      backdrop-filter: blur(6px);
    }
    dialog.backfill-completed-dialog {
      border: 1px solid rgba(255, 255, 255, 0.8);
      border-radius: 20px;
      padding: 0;
      max-width: 960px;
      width: 92vw;
      max-height: 85vh;
      margin: auto;
      color: var(--slate-900);
      direction: rtl;
      box-shadow: 0 25px 50px -12px rgba(15, 23, 42, 0.25);
    }
    dialog.backfill-completed-dialog[open] {
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
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
    .modal-overlay.active { display: flex; animation: fadeIn 0.2s; }
    .modal-content {
      max-width: 520px;
      width: 100%;
      padding: 2rem;
      text-align: center;
    }
    .preview-modal-content {
      max-width: 1600px;
      width: 95vw;
      height: 92vh;
      max-height: 94vh;
      display: flex;
      flex-direction: column;
      padding: 1.25rem 1.75rem;
      text-align: right;
      overflow: hidden;
    }
    .preview-modal-body {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 1.5rem;
      flex: 1;
      min-height: 0;
      overflow: hidden;
      margin-top: 0.75rem;
      margin-bottom: 0.75rem;
    }
    @media (max-width: 860px) {
      .preview-modal-body {
        grid-template-columns: 1fr;
        overflow-y: auto;
      }
    }
    .preview-image-wrap {
      background: var(--slate-900);
      border-radius: 12px;
      padding: 0.75rem;
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;
      height: 100%;
      min-height: 0;
    }
    .preview-image-wrap img {
      max-width: 100%;
      max-height: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: 6px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
    }
    .preview-text-wrap {
      display: flex;
      flex-direction: column;
      height: 100%;
      min-height: 0;
    }
    .preview-textarea {
      flex: 1;
      width: 100%;
      height: 100%;
      min-height: 0;
      padding: 1.25rem 1.5rem;
      border-radius: 12px;
      border: 1px solid var(--slate-200);
      font-size: 1.15rem;
      line-height: 2.0;
      background: white;
      resize: none;
      direction: rtl;
      font-family: inherit;
      overflow-y: auto;
    }
    .preview-textarea::-webkit-scrollbar {
      width: 6px;
    }
    .preview-textarea::-webkit-scrollbar-track {
      background: transparent;
    }
    .preview-textarea::-webkit-scrollbar-thumb {
      background: var(--slate-300);
      border-radius: 4px;
    }
  </style>
</head>
<body>

  <!-- Header -->
  <header class="app-header">
    <div class="header-content">
      <a href="javascript:void(0)" onclick="backToLibrary()" class="brand">
        <div class="brand-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/><path d="M6 6h10"/><path d="M6 10h10"/></svg>
        </div>
        <div>
          <div class="brand-title">Kitabim OCR <span class="brand-badge">يەرلىك نۇسخا</span></div>
        </div>
      </a>

      <div class="steps-indicator">
        <div class="step-item active" id="step1Indicator" onclick="backToLibrary()" style="cursor: pointer;" title="باش بەتكە قايتىش">1. كىتاب تاللاش</div>
        <div>&larr;</div>
        <div class="step-item" id="step2Indicator" onclick="openActiveProcessingMonitor()" style="cursor: pointer;" title="OCR نازارەت بېتىگە ئۆتۈش">2. OCR نازارەت</div>
        <div>&larr;</div>
        <div class="step-item" id="step3Indicator">3. تەكشۈرۈش &amp; تەھرىرلەش</div>
      </div>

      <div class="header-badges">
        <div class="status-pill">
          <span class="status-dot active"></span>
          <span>__OCR_ENGINE_LABEL__</span>
        </div>
        <div class="status-pill">
          <span class="status-dot active"></span>
          <span>Kitabim API</span>
        </div>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="main-container">

    <!-- 1. LANDING SECTION -->
    <section id="landing">
      <div id="landingError" class="error-banner" style="display: none;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span id="landingErrorText"></span>
      </div>

      <div class="tab-bar">
        <button class="tab-btn active" id="tabSessionsBtn" onclick="switchLandingTab('sessions')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>
          <span id="tabSessionsLabel">يەرلىكتىكى خىزمەتلەر</span>
          <span id="localSessionsBadge" class="brand-badge" style="display: none; margin-right: 0.3rem;">0</span>
        </button>
        <button class="tab-btn" id="tabLibraryBtn" onclick="switchLandingTab('library')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
          <span id="tabLibraryLabel">Kitabim كىتابلار ئامبىرى</span>
        </button>
        <button class="tab-btn" id="tabUploadBtn" onclick="switchLandingTab('upload')">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          <span id="tabUploadLabel">يېڭى PDF ھۆججەت</span>
        </button>
      </div>

      <!-- TAB 0: LOCAL SESSIONS TABLE -->
      <div id="tabSessionsContent" class="glass-panel" style="padding: 1.5rem;">
        <div class="search-row">
          <div>
            <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--slate-900);">
              كومپيۇتېرىڭىزدىكى OCR خىزمەتلىرى
            </h3>
            <p style="color: var(--slate-500); font-size: 0.88rem; margin-top: 0.2rem;">
              ئىلگىرى باشلانغان ياكى پۈتكەن كىتابلارنى بۇ يەردىن بىۋاسىتە داۋاملاشتۇرالايسىز
            </p>
          </div>
          <button class="btn btn-secondary" onclick="loadLocalSessions()" style="padding: 0.4rem 0.8rem; font-size: 0.85rem;">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
            يېڭىلاش
          </button>
        </div>

        <div class="table-container">
          <table class="books-table">
            <thead>
              <tr>
                <th data-i18n="sessions.th_book_file">كىتاب / ھۆججەت</th>
                <th data-i18n="sessions.th_progress">بەت سانى ۋە تەرەققىياتى</th>
                <th data-i18n="sessions.th_status">ھالىتى</th>
                <th data-i18n="sessions.th_uploaded">يۈكلەنگەن ھالىتى</th>
                <th data-i18n="sessions.th_modified">ئۆزگەرتىلگەن ۋاقتى</th>
                <th style="text-align: left;" data-i18n="sessions.th_action">مەشغۇلات</th>
              </tr>
            </thead>
            <tbody id="sessionsTableBody">
              <tr>
                <td colspan="6" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                  <div style="display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;">
                    <span style="width: 18px; height: 18px; border: 2px solid rgba(3, 105, 161, 0.2); border-top-color: var(--primary); border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
                    <span data-i18n="sessions.checking">يەرلىك خىزمەتلەر تەكشۈرۈلۈۋاتىدۇ...</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- TAB 1: KITABIM CLOUD BOOKS TABLE (WITH INTEGRATED BACKFILL CONTROLS & LIVE MONITOR) -->
      <div id="tabLibraryContent" class="glass-panel" style="padding: 1.5rem; display: none;">
        <!-- Backfill Toolbar & Status Bar -->
        <div class="glass-card" style="padding: 1.1rem 1.25rem; margin-bottom: 1.25rem; border: 1px solid rgba(3, 105, 161, 0.14); background: rgba(240, 249, 255, 0.55);">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap;">
            <div>
              <div style="font-size: 1.05rem; font-weight: 800; color: var(--slate-900);" data-i18n="backfill.title">
                ئىشلەپچىقىرىش كىتابلىرىنى قايتا تونۇتۇش (Backfill نازارەتچىسى)
              </div>
              <div style="font-size: 0.85rem; color: var(--slate-600); margin-top: 0.15rem;" data-i18n="backfill.subtitle">
                ئاپتوماتىك بىر تەرەپ قىلىش ئەڭ كونا يۈكلەنگەن كىتابتىن باشلاپ تەرتىپ بويىچە ئىشلەيدۇ. توختىتىلغاندا ھەر بىر كىتابنى ئايرىم تاللاپ ئىجرا قىلالايسىز.
              </div>
            </div>
            <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
              <button type="button" class="btn btn-success" id="backfillAutoToggleBtn" onclick="toggleAutoBackfill()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                <span id="backfillAutoToggleLabel" data-i18n="backfill.btn_start_auto">ئاپتوماتىك بىر تەرەپ قىلىشنى باشلاش</span>
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="loadBackfillCandidates(true); searchBooks(bookSearchQuery, true);" id="backfillRefreshBtn">
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67"/></svg>
                <span data-i18n="backfill.btn_refresh">يېڭىلاش</span>
              </button>
            </div>
          </div>

          <div id="backfillErrorBanner" class="error-banner" style="display: none; margin-top: 0.85rem; margin-bottom: 0;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span id="backfillErrorText"></span>
          </div>

          <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; margin-top: 0.85rem; padding-top: 0.75rem; border-top: 1px solid rgba(3, 105, 161, 0.1);">
            <div class="status-pill" id="backfillModePill">
              <span class="status-dot" id="backfillModeDot"></span>
              <span id="backfillModeText" data-i18n="backfill.status_idle">توختىتىلغان (قولدا تاللاشقا بولىدۇ)</span>
            </div>
            <div class="status-pill" id="backfillCurrentBookPill" onclick="openActiveProcessingMonitor()" title="OCR نازارەت بېتىنى ئېچىش" style="display: none; background: #fef3c7; border-color: #f59e0b; color: #92400e; font-weight: 700; cursor: pointer;">
              <span>⚡</span>
              <span id="backfillCurrentBookText"></span>
            </div>
            <button type="button" class="status-pill" id="backfillEligibleStatPill" onclick="setLibraryViewMode('all')" title="بارلىق كىتابلار تىزىملىكىنى كۆرۈش" style="cursor: pointer;">
              <span id="backfillEligibleStatText">قالغان كىتابلار: 0</span>
            </button>
            <div class="status-pill" id="backfillBacklogStatPill">
              <span id="backfillBacklogStatText">مۇلازىمېتىر ئىندېكس نۆۋىتى: 0 / 3</span>
            </div>
            <button type="button" class="status-pill" id="backfillSessionDoneStatPill" onclick="toggleBackfillCompletedView()" title="تاماملانغان كىتابلار تىزىملىكىنى كۆرۈش" style="cursor: pointer; background: #ecfdf5; border-color: #a7f3d0; color: #065f46; font-weight: 700;">
              <span>✓</span>
              <span id="backfillSessionDoneStatText">تاماملانغان كىتابلار: 0</span>
            </button>
          </div>
        </div>

        <div id="libraryAllBooksPanel">
          <div class="search-row">
            <div class="search-input-wrap">
              <span class="search-icon">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
              </span>
              <input type="text" id="bookSearch" class="search-input" placeholder="كىتاب نامى ياكى ئاپتور بويىچە ئىزدەش...">
              <button id="bookSearchClear" class="search-clear" onclick="clearBookSearch()">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap;">
              <button type="button" class="btn btn-secondary btn-sm" id="bookSortOrderBtn" onclick="toggleBookSortOrder()" title="يوللانغان ۋاقتى بويىچە تىزىش">
                <span id="bookSortOrderLabel">تەرتىپى: ئەڭ كونا ئاۋۋال ↑</span>
              </button>
              <div class="count-pill" id="bookCountBadge">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
                <span id="totalBooksCount">0</span> كىتاب تېپىلدى
              </div>
            </div>
          </div>

          <div class="table-container" tabindex="0" role="region" aria-label="Kitabim books library">
            <table class="books-table">
              <thead>
                <tr>
                  <th>كىتاب نامى</th>
                  <th>توم / بەت سانى</th>
                  <th>ئاپتور</th>
                  <th>OCR ھالىتى / نەشرى</th>
                  <th style="text-align: left;">مەشغۇلات</th>
                </tr>
              </thead>
              <tbody id="booksTableBody">
                <tr>
                  <td colspan="5" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                    <div style="display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;">
                      <span style="width: 18px; height: 18px; border: 2px solid rgba(3, 105, 161, 0.2); border-top-color: var(--primary); border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
                      <span>كىتابلار يۈكلىنىۋاتىدۇ...</span>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
            <div id="booksLoader" style="display: none; padding: 1.5rem; text-align: center; background: rgba(3, 105, 161, 0.02);">
              <div style="display: inline-flex; align-items: center; gap: 0.5rem; color: var(--primary); font-size: 0.9rem; font-weight: 600;">
                <span class="spinner" style="width: 18px; height: 18px; border: 2px solid rgba(3, 105, 161, 0.2); border-top-color: var(--primary); border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
                <span>يۈكلىنىۋاتىدۇ...</span>
              </div>
            </div>
            <div id="booksEndOfList" style="display: none; padding: 1.25rem; text-align: center; color: var(--slate-400); font-size: 0.85rem; border-top: 1px solid var(--slate-100);">
              <span>باشقا كىتاب قالمىدى</span>
            </div>
            <div id="booksScrollSentinel" style="height: 20px; width: 100%;"></div>
          </div>
        </div>

        <div id="libraryCompletedBooksPanel" style="display: none;">
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 1rem; flex-wrap: wrap; margin-bottom: 1rem;">
            <div style="display: flex; align-items: center; gap: 0.65rem;">
              <h3 style="font-size: 1.1rem; font-weight: 800; color: var(--slate-900); margin: 0;" data-i18n="backfill.history_title">قايتا تونۇتۇلغان كىتابلار تىزىملىكى</h3>
              <span id="backfillCompletedCountBadge" class="count-pill" style="font-size: 0.85rem; padding: 0.25rem 0.7rem;">0</span>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="setLibraryViewMode('all')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
              <span>بارلىق كىتابلار تىزىملىكىگە قايتىش</span>
            </button>
          </div>
          <div class="table-container" tabindex="0" role="region" aria-label="Completed backfill books">
            <table class="books-table">
              <thead>
                <tr>
                  <th style="width: 48px;">#</th>
                  <th>كىتاب نامى</th>
                  <th>بەت تەپسىلاتى</th>
                  <th>ۋاقتى</th>
                  <th style="text-align: left;">مەشغۇلات</th>
                </tr>
              </thead>
              <tbody id="backfillCompletedTableBody">
                <tr>
                  <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--slate-400);">ھازىرچە قايتا تونۇتۇلغان كىتاب يوق</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <!-- TAB 2: UPLOAD LOCAL PDF -->
      <div id="tabUploadContent" class="glass-panel" style="padding: 2.5rem; display: none;">
        <form id="uploadForm">
          <div class="upload-zone" id="dropZone">
            <input type="file" id="uploadFile" class="file-input-hidden" accept="application/pdf" required>
            <div class="upload-icon-wrap">
              <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--slate-900); margin-bottom: 0.5rem;">
              يەرلىكتىكى PDF ھۆججىتىنى سۆرەپ ئەكىلىڭ ياكى تاللاڭ
            </h3>
            <p style="color: var(--slate-500); font-size: 0.9rem;">
              Surya OCR موتورى كومپيۇتېرىڭىزنىڭ GPU/CPU كۈچى بىلەن تولۇق بەت ھۆججەتنى تونۇيدۇ
            </p>
          </div>

          <div id="selectedFileCard" class="file-preview-card" style="display: none;">
            <div class="book-avatar">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/></svg>
            </div>
            <div style="flex: 1; overflow: hidden;">
              <div id="fileNameDisplay" style="font-weight: 700; text-overflow: ellipsis; white-space: nowrap; overflow: hidden;"></div>
              <div id="fileSizeDisplay" style="font-size: 0.8rem; color: var(--slate-500);"></div>
            </div>
            <button type="submit" class="btn btn-primary" id="startUploadBtn">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              OCR نى باشلاش
            </button>
          </div>
        </form>
      </div>
    </section>

    <!-- 2. PROCESSING & MONITORING SECTION -->
    <section id="processing">
      <div class="glass-panel review-toolbar">
        <div class="toolbar-group">
          <button class="btn btn-secondary" onclick="backToLibrary()" id="processingBackBtn">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            <span id="processingBackLabel">باش بەتكە قايتىش</span>
          </button>
          <button type="button" class="btn btn-warning" onclick="toggleAutoBackfill()" id="processingBackfillToggleBtn" style="display: none; align-items: center; gap: 0.4rem;">
            <span id="processingBackfillToggleLabel">ئاپتوماتىك بىر تەرەپ قىلىشنى توختىتىش</span>
          </button>
          <button class="btn btn-primary" onclick="openCompletedReview()" id="processingReviewBtn" style="display: none; align-items: center; gap: 0.4rem;">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
            <span id="processingReviewLabel">نەتىجىنى كۆرۈش</span>
          </button>
        </div>
        <div class="toolbar-group" style="font-size: 0.88rem; color: var(--slate-600); font-weight: 500;">
          <span class="status-dot active" id="processingStatusDot"></span>
          <span id="processingBackgroundBadge">ئارقا سەھنىدە ئىشلەۋاتىدۇ</span>
        </div>
      </div>

      <div class="glass-panel monitor-card">
        <div class="progress-header">
          <div>
            <h2 style="font-size: 1.4rem; font-weight: 800; color: var(--slate-900); margin-bottom: 0.25rem;" id="processingHeaderTitle">
              ھۆججەت بىر تەرەپ قىلىنىۋاتىدۇ...
            </h2>
            <p style="color: var(--primary); font-weight: 700; font-size: 1.05rem; margin-bottom: 0.25rem;" id="processingBookTitle"></p>
            <p style="color: var(--slate-500); font-size: 0.95rem;" id="progressSubLabel">
              Surya OCR موتورى بەتلەرنى تەرتىپ بويىچە ئوقۇۋاتىدۇ
            </p>
          </div>
          <div class="count-pill" id="progressLabel" style="font-size: 1.1rem; font-weight: 700;">
            0 / 0 بەت
          </div>
        </div>

        <div class="progress-track">
          <div class="progress-bar-fill" id="progressFill"></div>
        </div>

        <div class="matrix-wrapper">
          <h3 style="font-size: 1.05rem; font-weight: 700; color: var(--slate-800); margin-bottom: 0.75rem;">
            بەتلەرنىڭ ھالىتى (Page Matrix):
          </h3>
          <div class="page-matrix" id="pageMatrixGrid"></div>
        </div>
      </div>
    </section>

    <!-- 3. REVIEW & EDITING SECTION -->
    <section id="review">
      <div class="glass-panel review-toolbar">
        <div class="toolbar-group">
          <button class="btn btn-secondary" onclick="backToLibrary()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
            كىتابخانىغا قايتىش
          </button>

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
    </section>

  </main>

  <!-- Push Result Dialog -->
  <div id="pushModal" class="modal-overlay">
    <div class="glass-panel modal-content">
      <div style="width: 56px; height: 56px; border-radius: 50%; background: #dcfce7; color: #166534; display: flex; align-items: center; justify-content: center; margin: 0 auto 1rem;">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
      <h3 style="font-size: 1.3rem; font-weight: 800; color: var(--slate-900); margin-bottom: 0.5rem;">
        بۇلۇتقا مۇۋەپپەقىيەتلىك يوللاندى!
      </h3>
      <p id="pushModalMessage" style="color: var(--slate-600); font-size: 0.95rem; margin-bottom: 1.5rem;"></p>
      <button class="btn btn-primary" onclick="closePushModal()" style="width: 100%;">
        چۈشەندىم
      </button>
    </div>
  </div>

  <!-- Live Page OCR Preview Modal -->
  <div id="livePreviewModal" class="modal-overlay" onclick="handlePreviewOverlayClick(event)">
    <div class="glass-panel preview-modal-content" onclick="event.stopPropagation()">
      <div style="display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid var(--slate-200); padding-bottom: 0.75rem;">
        <div style="display: flex; align-items: center; gap: 0.75rem;">
          <h3 id="previewModalTitle" style="font-size: 1.2rem; font-weight: 800; color: var(--slate-900); margin: 0;">بەت نەتىجىسى</h3>
          <span id="previewModalBadge" class="milestone-badge milestone-ready">OCR پۈتتى</span>
        </div>
        <div style="display: flex; align-items: center; gap: 0.6rem;">
          <button id="previewRedoBtn" class="btn btn-secondary btn-sm" onclick="redoPreviewPage()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
            قايتا تونۇتۇش
          </button>
          <button class="btn btn-secondary btn-sm" onclick="closeLivePreview()" style="padding: 0.35rem 0.6rem;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
          </button>
        </div>
      </div>

      <div class="preview-modal-body">
        <div class="preview-image-wrap">
          <img id="previewModalImage" src="" alt="Page image">
        </div>
        <div class="preview-text-wrap">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <div style="display: flex; align-items: center; gap: 0.6rem;">
              <span style="font-size: 0.85rem; font-weight: 700; color: var(--slate-700);">تەھرىرلەش / تېكىست نەتىجىسى:</span>
              <span id="previewSaveStatus" class="status-pill" style="display: none; font-size: 0.75rem; padding: 0.2rem 0.5rem;">ساقلاندى ✓</span>
            </div>
            <button id="previewCopyBtn" class="btn btn-secondary btn-sm" onclick="copyLivePreviewText()">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
              كۆچۈرۈۋېلىش
            </button>
          </div>
          <textarea id="previewModalText" class="preview-textarea uyghur-text" placeholder="بەت تېكىستى كىرگۈزۈڭ ياكى تەھرىرلەڭ..." oninput="handleLivePreviewInput(this.value)"></textarea>
        </div>
      </div>

      <div style="display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--slate-200); padding-top: 0.75rem;">
        <div style="display: flex; gap: 0.5rem;">
          <button id="previewPrevBtn" class="btn btn-secondary btn-sm" onclick="navigateLivePreview(-1)">
            &rarr; ئالدىنقى پۈتكەن بەت
          </button>
          <button id="previewNextBtn" class="btn btn-secondary btn-sm" onclick="navigateLivePreview(1)">
            كېيىنكى پۈتكەن بەت &larr;
          </button>
        </div>
        <button class="btn btn-secondary btn-sm" onclick="closeLivePreview()">تاقاش</button>
      </div>
    </div>
  </div>

  <script>
    const I18N = __I18N_JSON__;
    function t(key, params = {}) {
      const parts = key.split('.');
      let curr = I18N;
      for (const part of parts) {
        if (curr && typeof curr === 'object' && part in curr) {
          curr = curr[part];
        } else {
          return key;
        }
      }
      if (typeof curr !== 'string') return key;
      return curr.replace(/{(\\w+)}/g, (_, k) => params[k] !== undefined ? params[k] : `{${k}}`);
    }

    const sections = {
      landing: document.getElementById('landing'),
      processing: document.getElementById('processing'),
      review: document.getElementById('review'),
    };

    let progressPollTimer = null;
    function clearProgressPoll() {
      if (progressPollTimer) {
        clearTimeout(progressPollTimer);
        progressPollTimer = null;
      }
    }

    function resetProcessingSectionUI() {
      const reviewBtn = document.getElementById('processingReviewBtn');
      if (reviewBtn) reviewBtn.style.display = 'none';
      const headerTitle = document.getElementById('processingHeaderTitle');
      if (headerTitle) headerTitle.textContent = t('processing.title');
      const subLabel = document.getElementById('progressSubLabel');
      if (subLabel) subLabel.textContent = t('processing.subtitle');
      const bgBadge = document.getElementById('processingBackgroundBadge');
      if (bgBadge) bgBadge.textContent = t('processing.running_in_background');
      const dot = document.getElementById('processingStatusDot');
      if (dot) {
        dot.className = 'status-dot active';
        dot.style.background = '';
      }
      queueCompletionToastShown = false;
    }

    function showSection(name) {
      if (name !== 'processing') {
        clearProgressPoll();
      } else {
        resetProcessingSectionUI();
      }
      for (const key in sections) {
        sections[key].classList.toggle('active', key === name);
      }
      document.getElementById('step1Indicator').classList.toggle('active', name === 'landing');
      document.getElementById('step2Indicator').classList.toggle('active', name === 'processing');
      document.getElementById('step3Indicator').classList.toggle('active', name === 'review');
    }

    function switchLandingTab(tab) {
      document.getElementById('tabSessionsBtn').classList.toggle('active', tab === 'sessions');
      document.getElementById('tabLibraryBtn').classList.toggle('active', tab === 'library');
      document.getElementById('tabUploadBtn').classList.toggle('active', tab === 'upload');

      document.getElementById('tabSessionsContent').style.display = tab === 'sessions' ? 'block' : 'none';
      document.getElementById('tabLibraryContent').style.display = tab === 'library' ? 'block' : 'none';
      document.getElementById('tabUploadContent').style.display = tab === 'upload' ? 'block' : 'none';

      if (tab === 'library') {
        loadBackfillCandidates(false);
        pollBackfillStatus();
      }
    }

    let bookSearchQuery = '';
    let bookCurrentPage = 1;
    let bookSortOrder = 1; // 1 = oldest upload first (matches backfill order), -1 = newest first
    const BOOK_PAGE_SIZE = 40;
    let bookIsLoading = false;
    let bookHasMore = true;
    let totalBooksCount = 0;
    let booksObserver = null;

    function toggleBookSortOrder() {
      bookSortOrder = bookSortOrder === 1 ? -1 : 1;
      const lbl = document.getElementById('bookSortOrderLabel');
      if (lbl) {
        lbl.textContent = bookSortOrder === 1
          ? 'تەرتىپى: ئەڭ كونا ئاۋۋال ↑'
          : 'تەرتىپى: ئەڭ يېڭى ئاۋۋال ↓';
      }
      searchBooks(bookSearchQuery, true);
    }

    let searchTimer = null;
    document.getElementById('bookSearch').addEventListener('input', (e) => {
      clearTimeout(searchTimer);
      const val = e.target.value;
      document.getElementById('bookSearchClear').style.display = val ? 'block' : 'none';
      searchTimer = setTimeout(() => {
        bookSearchQuery = val;
        searchBooks(val, true);
      }, 300);
    });

    function clearBookSearch() {
      const input = document.getElementById('bookSearch');
      input.value = '';
      document.getElementById('bookSearchClear').style.display = 'none';
      bookSearchQuery = '';
      searchBooks('', true);
    }

    async function searchBooks(q = '', reset = true) {
      if (reset) {
        bookSearchQuery = q;
        bookCurrentPage = 1;
        bookHasMore = true;
        bookIsLoading = false;
        const tbody = document.getElementById('booksTableBody');
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 3rem; color: var(--slate-400);">
              <div style="display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;">
                <span style="width: 18px; height: 18px; border: 2px solid rgba(3, 105, 161, 0.2); border-top-color: var(--primary); border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
                <span>كىتابلار يۈكلىنىۋاتىدۇ...</span>
              </div>
            </td>
          </tr>
        `;
        const loader = document.getElementById('booksLoader');
        if (loader) loader.style.display = 'none';
        const end = document.getElementById('booksEndOfList');
        if (end) end.style.display = 'none';
      }

      if (bookIsLoading || (!reset && !bookHasMore)) return;

      bookIsLoading = true;
      if (!reset) {
        const loader = document.getElementById('booksLoader');
        if (loader) loader.style.display = 'block';
      }

      try {
        const pageToFetch = reset ? 1 : bookCurrentPage + 1;
        const url = `/api/books?q=${encodeURIComponent(bookSearchQuery)}&page=${pageToFetch}&pageSize=${BOOK_PAGE_SIZE}&sortBy=uploadDate&order=${bookSortOrder}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(await res.text());
        const body = await res.json();

        const books = body.books || [];
        totalBooksCount = (body.total !== undefined && body.total !== null) ? body.total : books.length;
        document.getElementById('totalBooksCount').textContent = totalBooksCount;

        if (reset) {
          document.getElementById('booksTableBody').innerHTML = '';
          if (!books.length) {
            document.getElementById('booksTableBody').innerHTML = `
              <tr>
                <td colspan="5" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                  بۇنداق كىتاب تېپىلمىدى
                </td>
              </tr>
            `;
            bookHasMore = false;
            return;
          }
        }

        appendBooksToTable(books);
        bookCurrentPage = pageToFetch;

        const renderedCount = document.getElementById('booksTableBody').querySelectorAll('tr').length;
        bookHasMore = renderedCount < totalBooksCount && books.length > 0;

        const end = document.getElementById('booksEndOfList');
        if (end) {
          if (!bookHasMore && renderedCount > 0 && renderedCount >= totalBooksCount) {
            end.style.display = 'block';
          } else {
            end.style.display = 'none';
          }
        }
      } catch (err) {
        if (reset) {
          renderBooksError(err.message);
        } else {
          console.error('Failed to load more books:', err);
        }
      } finally {
        bookIsLoading = false;
        const loader = document.getElementById('booksLoader');
        if (loader) loader.style.display = 'none';
      }
    }

    function appendBooksToTable(books) {
      const tbody = document.getElementById('booksTableBody');
      for (const b of books) {
        const tr = document.createElement('tr');
        tr.id = `book-row-${b.id}`;
        tr.dataset.bookId = String(b.id);
        tr.dataset.bookTitle = b.title || '';
        tr.dataset.bookAuthor = b.author || '';
        tr.dataset.bookTotalPages = String(b.totalPages || 0);
        tr.dataset.bookUploadDate = b.uploadDate || b.upload_date || '';
        tr.dataset.ocrVersion = b.ocrVersion || b.ocr_version || '';

        const milestone = b.ocrMilestone || 'idle';
        let milestoneClass = 'milestone-idle';
        let milestoneText = t('processing.status_pending');

        if (milestone === 'ready' || milestone === 'complete') {
          milestoneClass = 'milestone-ready';
          milestoneText = t('processing.status_completed');
        } else if (milestone === 'in_progress') {
          milestoneClass = 'milestone-in_progress';
          milestoneText = t('processing.status_processing');
        } else if (milestone === 'failed') {
          milestoneClass = 'milestone-failed';
          milestoneText = t('processing.status_failed');
        }

        const uploadDateStr = (b.uploadDate || b.upload_date)
          ? new Date(b.uploadDate || b.upload_date).toLocaleDateString()
          : '';

        tr.innerHTML = `
          <td>
            <div class="book-title-cell">
              <div class="book-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
              </div>
              <div>
                <div class="book-main-title">${escapeHtml(b.title || '—')}</div>
                <div class="book-sub-info">${b.totalPages || 0} ${t('library.pages_suffix')} ${uploadDateStr ? '· ' + escapeHtml(uploadDateStr) : ''} · <span style="font-family: monospace;">${escapeHtml(String(b.id))}</span></div>
              </div>
            </div>
          </td>
          <td>${b.volume !== null && b.volume !== undefined ? b.volume + '-' + t('library.vol_prefix') : '—'}</td>
          <td>${escapeHtml(b.author || t('library.author_unknown'))}</td>
          <td>
            <div style="display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap;">
              <span class="milestone-badge ${milestoneClass}">${milestoneText}</span>
              <span id="ocr-ver-badge-${b.id}"></span>
            </div>
          </td>
          <td style="text-align: left;">
            <div style="display: flex; align-items: center; gap: 0.45rem; justify-content: flex-end; flex-wrap: wrap;">
              <span id="backfill-action-slot-${b.id}"></span>
              <button class="btn btn-primary btn-sm" id="btn-start-${b.id}">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
                ${t('library.btn_download_correct')}
              </button>
            </div>
          </td>
        `;
        tr.querySelector(`#btn-start-${b.id}`).onclick = () => startExisting(b.id);
        tbody.appendChild(tr);
      }
      syncLibraryBackfillRows();
      updateBackfillHeaderStats();
    }

    function initBooksInfiniteScroll() {
      const sentinel = document.getElementById('booksScrollSentinel');
      if (!sentinel) return;

      if (booksObserver) {
        booksObserver.disconnect();
      }

      booksObserver = new IntersectionObserver((entries) => {
        if (entries[0].isIntersecting && !bookIsLoading && bookHasMore) {
          searchBooks(bookSearchQuery, false);
        }
      }, {
        rootMargin: '600px',
        threshold: 0.05
      });

      booksObserver.observe(sentinel);
    }

    function renderBooksError(msg) {
      const tbody = document.getElementById('booksTableBody');
      tbody.innerHTML = `
        <tr>
          <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--accent-rose);">
            ${t('errors.generic', {error: escapeHtml(msg)})}
          </td>
        </tr>
      `;
    }

    async function startExisting(bookId) {
      const btn = document.getElementById(`btn-start-${bookId}`);
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span style="display:inline-block; animation: spin 1s infinite linear;">⚙️</span> يۈكلىنىۋاتىدۇ...';
      }
      try {
        const res = await fetch('/api/start/existing', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({bookId: bookId}),
        });
        if (!res.ok) {
          showLandingError(await res.text());
          if (btn) { btn.disabled = false; btn.textContent = 'تەھرىرلەش / تۈزىتىش'; }
          return;
        }
        const body = await res.json();
        if (body.stage === 'review') {
          showSection('review');
          loadPages();
        } else if (body.isProcessing) {
          showSection('processing');
          pollProgress();
        } else {
          if (btn) { btn.disabled = false; btn.textContent = 'نۆۋەتتە'; }
          switchLandingTab('sessions');
          loadLocalSessions();
          showToast(t('upload.toast_queued', {pos: body.queuePosition || 1}));
        }
      } catch (err) {
        showLandingError(err.message);
        if (btn) { btn.disabled = false; btn.textContent = 'تەھرىرلەش / تۈزىتىش'; }
      }
    }

    // Drag & Drop & File Select
    const dropZone = document.getElementById('dropZone');
    const uploadFileInput = document.getElementById('uploadFile');

    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('dragover');
    });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('dragover');
      if (e.dataTransfer.files.length) {
        uploadFileInput.files = e.dataTransfer.files;
        handleFileChosen(uploadFileInput.files[0]);
      }
    });

    uploadFileInput.addEventListener('change', (e) => {
      if (e.target.files.length) {
        handleFileChosen(e.target.files[0]);
      }
    });

    function handleFileChosen(file) {
      if (!file) return;
      document.getElementById('fileNameDisplay').textContent = file.name;
      document.getElementById('fileSizeDisplay').textContent = (file.size / (1024 * 1024)).toFixed(2) + ' MB';
      document.getElementById('selectedFileCard').style.display = 'flex';
    }

    document.getElementById('uploadForm').addEventListener('submit', async (e) => {
      e.preventDefault();
      const fileInput = document.getElementById('uploadFile');
      if (!fileInput.files[0]) return;

      const formData = new FormData();
      formData.append('file', fileInput.files[0]);

      const startBtn = document.getElementById('startUploadBtn');
      startBtn.disabled = true;
      startBtn.innerHTML = '<span style="display:inline-block; animation: spin 1s infinite linear;">⚙️</span> ' + t('upload.starting');

      try {
        const res = await fetch('/api/start/upload', {method: 'POST', body: formData});
        if (!res.ok) {
          showLandingError(await res.text());
          startBtn.disabled = false;
          startBtn.textContent = t('upload.btn_start');
          return;
        }
        const data = await res.json();
        if (data.isProcessing) {
          showSection('processing');
          pollProgress();
        } else {
          startBtn.disabled = false;
          startBtn.textContent = t('upload.btn_start');
          fileInput.value = '';
          document.getElementById('selectedFileCard').style.display = 'none';
          switchLandingTab('sessions');
          loadLocalSessions();
          showToast(t('upload.toast_queued', {pos: data.queuePosition || 1}));
        }
      } catch (err) {
        showLandingError(err.message);
        startBtn.disabled = false;
        startBtn.textContent = t('upload.btn_start');
      }
    });

    let toastTimeout = null;
    function showToast(msg, isError = false) {
      let toast = document.getElementById('globalToast');
      if (!toast) {
        toast = document.createElement('div');
        toast.id = 'globalToast';
        toast.style.position = 'fixed';
        toast.style.bottom = '2rem';
        toast.style.left = '50%';
        toast.style.transform = 'translateX(-50%)';
        toast.style.padding = '0.75rem 1.5rem';
        toast.style.borderRadius = '9999px';
        toast.style.boxShadow = '0 10px 25px -5px rgba(0, 0, 0, 0.3)';
        toast.style.fontSize = '0.95rem';
        toast.style.fontWeight = '600';
        toast.style.zIndex = '9999';
        toast.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
        toast.style.opacity = '0';
        toast.style.pointerEvents = 'none';
        toast.style.direction = 'rtl';
        document.body.appendChild(toast);
      }
      toast.style.background = isError ? '#dc2626' : 'var(--slate-900)';
      toast.style.color = '#fff';
      toast.textContent = msg;
      toast.style.opacity = '1';
      toast.style.transform = 'translateX(-50%) translateY(0)';
      if (toastTimeout) clearTimeout(toastTimeout);
      toastTimeout = setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateX(-50%) translateY(10px)';
      }, 4000);
    }

    function showLandingError(text) {
      const banner = document.getElementById('landingError');
      const errSpan = document.getElementById('landingErrorText');
      if (text) {
        banner.style.display = 'flex';
        errSpan.textContent = text;
      } else {
        banner.style.display = 'none';
      }
    }

    let currentProcessingSessionId = null;
    let currentProcessingBookTitle = '';
    let lastCompletedSessionId = null;
    let queueCompletionToastShown = false;

    async function openCompletedReview() {
      const sId = lastCompletedSessionId || currentProcessingSessionId;
      if (sId) {
        viewResults(sId);
      }
    }

    async function openActiveProcessingMonitor() {
      try {
        const res = await fetch('/api/state');
        if (res.ok) {
          const st = await res.json();
          if (st.activeSessionId || st.isBackfill) {
            showSection('processing');
            pollProgress();
            return;
          }
        }
      } catch (_) {}
      if (backfillStatus && backfillStatus.isBusy) {
        showSection('processing');
        pollProgress();
      }
    }

    async function pollProgress() {
      clearProgressPoll();
      if (!sections.processing.classList.contains('active')) {
        return;
      }
      try {
        const stateRes = await fetch('/api/state');
        const state = await stateRes.json();
        if (!sections.processing.classList.contains('active')) {
          return;
        }

        const isBackfill = Boolean(state.isBackfill);
        const bfBtn = document.getElementById('processingBackfillToggleBtn');
        if (bfBtn) {
          if (isBackfill) {
            bfBtn.style.display = 'inline-flex';
            if (state.backfillAutoRunning) {
              bfBtn.className = 'btn btn-warning';
              bfBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg><span>${escapeHtml(t('backfill.btn_pause_auto'))}</span>`;
            } else if (state.backfillMode === 'pausing') {
              bfBtn.className = 'btn btn-primary';
              bfBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${escapeHtml(t('backfill.btn_resume_auto'))}</span>`;
            } else {
              bfBtn.className = 'btn btn-success';
              bfBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${escapeHtml(t('backfill.btn_start_auto'))}</span>`;
            }
          } else {
            bfBtn.style.display = 'none';
          }
        }

        if (state.stage === 'landing' && !isBackfill) {
          currentProcessingSessionId = null;
          currentProcessingBookTitle = '';
          lastCompletedSessionId = null;
          queueCompletionToastShown = false;
          showSection('landing');
          loadLocalSessions();
          loadBackfillCandidates(false);
          searchBooks(bookSearchQuery, true);
          return;
        }
        if (state.stage === 'error') {
          currentProcessingSessionId = null;
          currentProcessingBookTitle = '';
          lastCompletedSessionId = null;
          queueCompletionToastShown = false;
          showSection('landing');
          showLandingError(state.error || t('errors.processing_failed'));
          return;
        }

        const activeId = state.activeSessionId;
        const queuedCount = Array.isArray(state.queuedSessions) ? state.queuedSessions.length : 0;
        const isQueueActive = Boolean(activeId || queuedCount > 0 || isBackfill);

        // Transition from finished book to next active book in queue / auto-backfill
        if (activeId && currentProcessingSessionId && activeId !== currentProcessingSessionId) {
          lastCompletedSessionId = currentProcessingSessionId;
          const finishedTitle = currentProcessingBookTitle || t('processing.previous_book');
          showToast(t('processing.toast_book_completed_next_started', {
            finished: finishedTitle,
            next: state.title || activeId
          }));
          currentProcessingSessionId = activeId;
          currentProcessingBookTitle = state.title || '';
          currentProcessingPages = [];
          currentSessionVersion = Date.now();
          const grid = document.getElementById('pageMatrixGrid');
          if (grid) grid.innerHTML = '';
          const fill = document.getElementById('progressFill');
          if (fill) fill.style.width = '0%';
          resetProcessingSectionUI();
          if (state.title) {
            const pTitle = document.getElementById('processingBookTitle');
            if (pTitle) pTitle.textContent = state.title;
          }
          progressPollTimer = setTimeout(pollProgress, 4800);
          return;
        } else if (activeId && !currentProcessingSessionId) {
          currentProcessingSessionId = activeId;
          currentProcessingBookTitle = state.title || '';
        }

        if (state.title) {
          const pTitle = document.getElementById('processingBookTitle');
          if (pTitle) pTitle.textContent = state.title;
        }
        if (isBackfill) {
          const subLabel = document.getElementById('progressSubLabel');
          if (subLabel) {
            if (state.backfillPhase === 'downloading') {
              subLabel.textContent = t('backfill.phase_downloading');
            } else if (state.backfillPhase === 'submitting') {
              subLabel.textContent = t('backfill.phase_submitting');
            } else {
              subLabel.textContent = t('backfill.phase_ocr');
            }
          }
        }

        let isDone = false;
        const res = await fetch('/api/pages');
        if (res.ok) {
          const pages = await res.json();
          const total = pages.length;
          const done = pages.filter(p => p.status === 'ocrd' || p.status === 'skipped' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed').length;
          document.getElementById('progressLabel').textContent = t('sessions.pages_completed_stat', {done: done, total: total});
          document.getElementById('progressFill').style.width = total ? ((done / total) * 100) + '%' : '0%';
          renderPageMatrix(pages);
          if (total > 0 && done === total) {
            isDone = true;
          }
        }

        if (!sections.processing.classList.contains('active')) {
          return;
        }

        // If current book is done but queue or backfill is still processing:
        // Continue polling to advance to next book smoothly without opening review page.
        if (isDone && isQueueActive) {
          progressPollTimer = setTimeout(pollProgress, 4800);
          return;
        }

        // If current book is done and the queue has no more active or queued items:
        // Do NOT auto open the review page. Show completion status and provide action buttons.
        if (isDone && !isQueueActive) {
          if (currentProcessingSessionId) {
            lastCompletedSessionId = currentProcessingSessionId;
          }
          const isBackfillSession = String(lastCompletedSessionId || '').startsWith('backfill-');
          const reviewBtn = document.getElementById('processingReviewBtn');
          if (reviewBtn) reviewBtn.style.display = isBackfillSession ? 'none' : 'inline-flex';
          const dot = document.getElementById('processingStatusDot');
          if (dot) {
            dot.className = 'status-dot';
            dot.style.background = '#10b981';
          }
          const bgBadge = document.getElementById('processingBackgroundBadge');
          if (bgBadge) bgBadge.textContent = t('processing.status_completed');
          const headerTitle = document.getElementById('processingHeaderTitle');
          if (headerTitle) headerTitle.textContent = t('processing.all_completed_title');
          const subLabel = document.getElementById('progressSubLabel');
          if (subLabel) subLabel.textContent = t('processing.all_completed_subtitle');
          if (!queueCompletionToastShown) {
            queueCompletionToastShown = true;
            showToast(t('processing.toast_all_completed'));
          }
          return;
        }

        progressPollTimer = setTimeout(pollProgress, 9000);
      } catch (err) {
        if (sections.processing.classList.contains('active')) {
          progressPollTimer = setTimeout(pollProgress, 24000);
        }
      }
    }

    let currentProcessingPages = [];
    let currentPreviewPageNumber = null;
    let currentSessionVersion = Date.now();

    function renderPageMatrix(pages) {
      currentProcessingPages = pages || [];
      const matrix = document.getElementById('pageMatrixGrid');
      matrix.innerHTML = '';
      for (const p of pages) {
        const div = document.createElement('div');
        let statusClass = 'pending';
        let statusIcon = '⏳';
        let isClickable = false;
        let tooltip = t('review.page_title_format', {pageNumber: p.pageNumber});

        if (p.status === 'ocrd' || p.status === 'from_kitabim' || p.status === 'reviewed') {
          statusClass = 'done';
          statusIcon = '✓';
          isClickable = true;
          tooltip = `${t('review.page_title_format', {pageNumber: p.pageNumber})}: ${t('review.status_ocrd_badge')}`;
        } else if (p.status === 'skipped') {
          statusClass = 'skipped';
          statusIcon = '↷';
          isClickable = true;
          tooltip = `${t('review.page_title_format', {pageNumber: p.pageNumber})}: ${t('backfill.badge_skipped')}`;
        } else if (p.status === 'failed') {
          statusClass = 'failed';
          statusIcon = '✕';
          isClickable = true;
          tooltip = `${t('review.page_title_format', {pageNumber: p.pageNumber})}: ${t('processing.status_failed')}`;
        } else if (p.status === 'processing') {
          statusClass = 'processing';
          statusIcon = '⚙️';
          tooltip = `${t('review.page_title_format', {pageNumber: p.pageNumber})}: ${t('processing.status_processing')}`;
        }

        div.className = `matrix-tile ${statusClass} ${isClickable ? 'clickable' : ''}`;
        div.title = tooltip;
        div.innerHTML = `<span>${p.pageNumber}</span><span style="font-size:0.7rem;">${statusIcon}</span>`;
        if (isClickable) {
          div.onclick = () => openLivePreview(p.pageNumber);
        }
        matrix.appendChild(div);
      }

      // If preview modal is currently open, keep its content updated
      if (currentPreviewPageNumber !== null) {
        const activePage = currentProcessingPages.find(p => p.pageNumber === currentPreviewPageNumber);
        if (activePage) {
          updateLivePreviewContent(activePage);
        }
      }
    }

    function openLivePreview(pageNumber) {
      const page = currentProcessingPages.find(p => p.pageNumber === pageNumber);
      if (!page) return;
      currentPreviewPageNumber = pageNumber;
      updateLivePreviewContent(page);
      document.getElementById('livePreviewModal').classList.add('active');
    }

    function updateLivePreviewContent(page) {
      document.getElementById('previewModalTitle').textContent = `${t('review.page_title_format', {pageNumber: page.pageNumber})} - ${t('preview_modal.title')}`;
      const badge = document.getElementById('previewModalBadge');
      if (page.status === 'failed') {
        badge.className = 'milestone-badge milestone-failed';
        badge.textContent = t('processing.status_failed');
      } else if (page.status === 'skipped') {
        badge.className = 'milestone-badge milestone-idle';
        badge.textContent = t('backfill.badge_skipped');
      } else {
        badge.className = 'milestone-badge milestone-ready';
        badge.textContent = page.status === 'from_kitabim' ? t('review.status_from_kitabim_badge') : t('review.status_ocrd_badge');
      }
      const imgEl = document.getElementById('previewModalImage');
      const targetSrc = `/api/pages/${page.pageNumber}/image?v=${currentSessionVersion}`;
      if (imgEl && imgEl.getAttribute('src') !== targetSrc) {
        imgEl.src = targetSrc;
      }
      
      const textArea = document.getElementById('previewModalText');
      if (document.activeElement !== textArea) {
        textArea.value = page.text || (page.error ? `${t('errors.generic', {error: page.error})}` : '');
      }

      const completedPages = currentProcessingPages.filter(p => p.status === 'ocrd' || p.status === 'skipped' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed');
      const currentIndex = completedPages.findIndex(p => p.pageNumber === page.pageNumber);
      document.getElementById('previewPrevBtn').disabled = currentIndex <= 0;
      document.getElementById('previewNextBtn').disabled = currentIndex === -1 || currentIndex >= completedPages.length - 1;
    }

    function handleLivePreviewInput(text) {
      if (currentPreviewPageNumber === null) return;
      const saveStatus = document.getElementById('previewSaveStatus');
      if (saveStatus) {
        saveStatus.style.display = 'inline-block';
        saveStatus.textContent = '...';
        saveStatus.style.color = 'var(--slate-500)';
      }

      // Update in-memory state so flipping pages preserves changes
      const page = currentProcessingPages.find(p => p.pageNumber === currentPreviewPageNumber);
      if (page) {
        page.text = text;
      }
      const loadedPage = allLoadedPages.find(p => p.pageNumber === currentPreviewPageNumber);
      if (loadedPage) {
        loadedPage.text = text;
      }

      // Sync with review screen textarea if present in DOM
      const reviewTextarea = document.querySelector(`.ocr-textarea[data-page="${currentPreviewPageNumber}"]`);
      if (reviewTextarea && reviewTextarea !== document.activeElement) {
        reviewTextarea.value = text;
      }

      // Auto-save to backend
      clearTimeout(saveTimeouts[currentPreviewPageNumber]);
      saveTimeouts[currentPreviewPageNumber] = setTimeout(async () => {
        try {
          await fetch(`/api/pages/${currentPreviewPageNumber}/update`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({text: text}),
          });
          if (saveStatus) {
            saveStatus.textContent = t('preview_modal.saved');
            saveStatus.style.color = '#15803d';
            setTimeout(() => {
              if (saveStatus && saveStatus.textContent === t('preview_modal.saved')) {
                saveStatus.style.display = 'none';
              }
            }, 1800);
          }
        } catch (e) {
          console.error('Failed to auto-save page in preview', currentPreviewPageNumber, e);
          if (saveStatus) {
            saveStatus.textContent = '✕';
            saveStatus.style.color = '#b91c1c';
          }
        }
      }, 500);
    }

    async function redoPreviewPage() {
      if (currentPreviewPageNumber === null) return;
      const pageNum = currentPreviewPageNumber;
      const btn = document.getElementById('previewRedoBtn');
      btn.disabled = true;
      btn.innerHTML = `<span style="display:inline-block; animation: spin 1s infinite linear;">⚙️</span> ${t('review.redo_in_progress')}`;
      const badge = document.getElementById('previewModalBadge');
      let prevBadgeClass = '';
      let prevBadgeText = '';
      if (badge) {
        prevBadgeClass = badge.className;
        prevBadgeText = badge.textContent;
        badge.className = 'milestone-badge milestone-in_progress';
        badge.textContent = t('review.status_processing_badge');
      }
      showToast(t('review.redo_page_in_progress', {pageNumber: pageNum}));
      try {
        const res = await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: [pageNum]}),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        currentSessionVersion = Date.now();
        showToast(t('review.redo_page_success', {pageNumber: pageNum}));
        const pagesRes = await fetch('/api/pages');
        if (pagesRes.ok) {
          const pages = await pagesRes.json();
          currentProcessingPages = pages;
          renderPageMatrix(pages);
          const page = pages.find(p => p.pageNumber === pageNum);
          if (page) {
            updateLivePreviewContent(page);
          }
        }
      } catch (e) {
        console.error('Failed to redo page from preview', pageNum, e);
        showToast(t('review.redo_page_error', {pageNumber: pageNum, error: e.message || e}), true);
        if (badge && prevBadgeClass) {
          badge.className = prevBadgeClass;
          badge.textContent = prevBadgeText;
        }
      } finally {
        btn.disabled = false;
        btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg> ${t('review.btn_re_ocr')}`;
      }
    }

    function closeLivePreview() {
      currentPreviewPageNumber = null;
      document.getElementById('livePreviewModal').classList.remove('active');
    }

    function handlePreviewOverlayClick(event) {
      if (event.target === document.getElementById('livePreviewModal')) {
        closeLivePreview();
      }
    }

    function navigateLivePreview(direction) {
      if (currentPreviewPageNumber === null) return;
      const completedPages = currentProcessingPages.filter(p => p.status === 'ocrd' || p.status === 'skipped' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed');
      const currentIndex = completedPages.findIndex(p => p.pageNumber === currentPreviewPageNumber);
      if (currentIndex === -1) return;
      const targetIndex = currentIndex + direction;
      if (targetIndex >= 0 && targetIndex < completedPages.length) {
        openLivePreview(completedPages[targetIndex].pageNumber);
      }
    }

    async function copyLivePreviewText() {
      const text = document.getElementById('previewModalText').value;
      if (!text) return;
      try {
        await navigator.clipboard.writeText(text);
        const btn = document.getElementById('previewCopyBtn');
        const orig = btn.innerHTML;
        btn.innerHTML = `✓ ${t('preview_modal.copied')}`;
        btn.style.color = '#15803d';
        setTimeout(() => {
          btn.innerHTML = orig;
          btn.style.color = '';
        }, 1500);
      } catch (e) {
        console.error('Failed to copy', e);
      }
    }

    document.addEventListener('keydown', (e) => {
      if (currentPreviewPageNumber !== null) {
        if (e.key === 'Escape') {
          closeLivePreview();
          return;
        }
        const isEditing = ['TEXTAREA', 'INPUT'].includes(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
        if (isEditing) {
          return;
        }
        if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
          navigateLivePreview(-1);
        } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
          navigateLivePreview(1);
        }
      }
    });

    let allLoadedPages = [];

    async function loadPages() {
      try {
        const res = await fetch('/api/pages');
        if (!res.ok) throw new Error(await res.text());
        allLoadedPages = await res.json();
        renderPagesList(allLoadedPages);
        updateSelectedCount();
      } catch (err) {
        console.error('Failed to load pages', err);
      }
    }

    function renderPagesList(pages) {
      const container = document.getElementById('pages');
      if (!container) return;

      // Full rebuild on first load or if page count changed
      if (container.children.length !== pages.length) {
        container.innerHTML = '';
        for (const p of pages) {
          const div = document.createElement('div');
          div.className = 'glass-card page-card';
          div.id = `page-card-${p.pageNumber}`;
          const statusBadgeText = p.status === 'from_kitabim' ? t('review.status_from_kitabim_badge') : p.status === 'ocrd' ? t('review.status_ocrd_badge') : p.status === 'failed' ? t('processing.status_failed') : p.status;
          div.innerHTML = `
            <div class="page-card-header">
              <div style="display: flex; align-items: center; gap: 0.8rem;">
                <input type="checkbox" class="select" value="${p.pageNumber}" onchange="updateSelectedCount()" style="width: 18px; height: 18px; cursor: pointer;">
                <span style="font-weight: 700; font-size: 1.1rem; color: var(--slate-900);">${t('review.page_title_format', {pageNumber: p.pageNumber})}</span>
                <span class="milestone-badge ${p.status === 'failed' ? 'milestone-failed' : 'milestone-ready'}">
                  ${statusBadgeText}
                </span>
              </div>
              <div style="display: flex; align-items: center; gap: 1rem;">
                <label style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.85rem; cursor: pointer; color: var(--slate-700);">
                  <input type="checkbox" class="toc-toggle" data-page="${p.pageNumber}" ${p.isToc ? 'checked' : ''} onchange="toggleToc(${p.pageNumber}, this.checked)">
                  ${t('review.chk_toc_label')}
                </label>
                <button class="btn btn-secondary btn-sm" id="redoBtn-${p.pageNumber}" onclick="redoSinglePage(${p.pageNumber})">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg>
                  ${t('review.btn_re_ocr')}
                </button>
              </div>
            </div>
            <div class="page-card-body">
              <div class="page-image-wrap">
                <img src="/api/pages/${p.pageNumber}/image?v=${currentSessionVersion}" alt="${t('review.page_title_format', {pageNumber: p.pageNumber})}" loading="lazy">
              </div>
              <div class="page-editor-wrap">
                <textarea class="ocr-textarea uyghur-text" data-page="${p.pageNumber}" oninput="autoSavePageText(${p.pageNumber}, this.value)" placeholder="${t('review.textarea_placeholder')}">${escapeHtml(p.text || '')}</textarea>
              </div>
            </div>
          `;
          container.appendChild(div);
        }
        return;
      }

      // Targeted reconciliation for existing cards to preserve active typing & cursor position
      for (const p of pages) {
        const card = document.getElementById(`page-card-${p.pageNumber}`);
        if (!card) continue;

        const badge = card.querySelector('.milestone-badge');
        if (badge) {
          const statusBadgeText = p.status === 'from_kitabim' ? t('review.status_from_kitabim_badge') : p.status === 'ocrd' ? t('review.status_ocrd_badge') : p.status === 'failed' ? t('processing.status_failed') : p.status;
          badge.textContent = statusBadgeText;
          badge.className = `milestone-badge ${p.status === 'failed' ? 'milestone-failed' : 'milestone-ready'}`;
        }

        const img = card.querySelector('img');
        if (img) {
          const newSrc = `/api/pages/${p.pageNumber}/image?v=${currentSessionVersion}`;
          if (img.getAttribute('src') !== newSrc) {
            img.src = newSrc;
          }
        }

        const textarea = card.querySelector('.ocr-textarea');
        if (textarea) {
          const isFocused = document.activeElement === textarea;
          const hasPendingSave = Boolean(saveTimeouts[p.pageNumber]);
          // Only update textarea content if user is NOT actively typing in it
          if (!isFocused && !hasPendingSave && textarea.value !== (p.text || '')) {
            textarea.value = p.text || '';
          }
        }
      }
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
        badge.textContent = t('review.selected_count', {count: selected.length});
      } else {
        badge.style.display = 'none';
      }
    }

    async function redoSinglePage(pageNum) {
      showToast(t('review.redo_page_in_progress', {pageNumber: pageNum}));

      const btn = document.getElementById(`redoBtn-${pageNum}`);
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span style="display:inline-block; animation: spin 1s infinite linear;">⚙️</span> ${t('review.redo_in_progress')}`;
      }

      const card = document.getElementById(`page-card-${pageNum}`);
      const badge = card ? card.querySelector('.milestone-badge') : null;
      let prevBadgeClass = '';
      let prevBadgeText = '';
      if (badge) {
        prevBadgeClass = badge.className;
        prevBadgeText = badge.textContent;
        badge.className = 'milestone-badge milestone-in_progress';
        badge.textContent = t('review.status_processing_badge');
      }

      currentSessionVersion = Date.now();
      try {
        const res = await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: [pageNum]}),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        showToast(t('review.redo_page_success', {pageNumber: pageNum}));
        await loadPages();
      } catch (err) {
        console.error('Failed to redo page', pageNum, err);
        showToast(t('review.redo_page_error', {pageNumber: pageNum, error: err.message || err}), true);
        if (badge && prevBadgeClass) {
          badge.className = prevBadgeClass;
          badge.textContent = prevBadgeText;
        }
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/></svg> ${t('review.btn_re_ocr')}`;
        }
      }
    }

    async function redoSelected() {
      const pages = selectedPageNumbers();
      if (!pages.length) return;
      currentSessionVersion = Date.now();
      const btn = document.getElementById('redoSelectedBtn');
      btn.disabled = true;
      btn.textContent = t('review.redo_in_progress');
      if (pages.length === 1) {
        showToast(t('review.redo_page_in_progress', {pageNumber: pages[0]}));
      } else {
        const pagesStr = pages.length <= 5 ? pages.join(', ') : `${pages.slice(0, 3).join(', ')}... (${pages.length})`;
        showToast(t('review.redo_pages_in_progress', {pages: pagesStr}));
      }
      try {
        const res = await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        if (pages.length === 1) {
          showToast(t('review.redo_page_success', {pageNumber: pages[0]}));
        } else {
          showToast(t('review.redo_pages_success'));
        }
        await loadPages();
      } catch (err) {
        showToast(t('errors.generic', {error: err.message || err}), true);
      } finally {
        btn.disabled = false;
        btn.textContent = t('review.btn_redo_selected');
      }
    }

    async function redoAll() {
      const pages = allPageNumbers();
      if (!pages.length) return;
      if (!confirm(t('review.redo_all_confirm'))) return;
      currentSessionVersion = Date.now();
      const btn = document.getElementById('redoAllBtn');
      btn.disabled = true;
      btn.textContent = t('review.redo_in_progress');
      showToast(t('review.redo_all_in_progress'));
      try {
        const res = await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        showToast(t('review.redo_all_success'));
        await loadPages();
      } catch (err) {
        showToast(t('errors.generic', {error: err.message || err}), true);
      } finally {
        btn.disabled = false;
        btn.textContent = t('review.btn_redo_all');
      }
    }

    async function push() {
      const btn = document.getElementById('pushBtn');
      btn.disabled = true;
      btn.textContent = t('review.push_in_progress');
      try {
        const res = await fetch('/api/push', {method: 'POST'});
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `Push failed (HTTP ${res.status})`);
        }
        const body = await res.json();
        let message = body.count ? t('push_modal.corrections_message', {count: body.count}) : t('push_modal.new_book_message');
        document.getElementById('pushModalMessage').textContent = message;
        document.getElementById('pushModal').classList.add('active');
      } catch (err) {
        alert(t('errors.failed_to_push', {error: err.message}));
      } finally {
        btn.disabled = false;
        btn.textContent = t('review.btn_push');
      }
    }

    function closePushModal() {
      document.getElementById('pushModal').classList.remove('active');
    }

    let sessionsAutoRefreshTimer = null;

    function ensureSessionsAutoRefresh() {
      if (sessionsAutoRefreshTimer) return;
      sessionsAutoRefreshTimer = setInterval(() => {
        const isLanding = sections.landing && sections.landing.classList.contains('active');
        const isSessionsTab = document.getElementById('tabSessionsContent') && document.getElementById('tabSessionsContent').style.display !== 'none';
        if (isLanding && (isSessionsTab || window._hasQueuedOrProcessing)) {
          loadLocalSessions();
        }
      }, 60000);
    }

    async function loadLocalSessions() {
      const tbody = document.getElementById('sessionsTableBody');
      try {
        const res = await fetch('/api/sessions');
        const sessions = await res.json();
        const badge = document.getElementById('localSessionsBadge');
        if (sessions && sessions.length > 0) {
          badge.textContent = sessions.length;
          badge.style.display = 'inline-block';
        } else {
          badge.style.display = 'none';
        }

        window._hasQueuedOrProcessing = sessions && sessions.some(s => s.queueStatus === 'queued' || s.queueStatus === 'processing' || !s.isComplete);

        if (!sessions || sessions.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="6" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                ${t('sessions.empty')}
              </td>
            </tr>
          `;
          return sessions;
        }

        tbody.innerHTML = sessions.map(s => {
          const pct = s.totalPages > 0 ? Math.round((s.completedPages / s.totalPages) * 100) : 0;
          let statusBadge;
          if (s.queueStatus === 'queued') {
            statusBadge = `<span class="tag-badge" style="background: rgba(99, 102, 241, 0.12); color: #4f46e5; font-size: 0.78rem;">⏳ ${t('sessions.status_queued', {pos: s.queuePosition || 1})}</span>`;
          } else if (s.isComplete) {
            statusBadge = `<span class="tag-badge success">${t('sessions.status_completed', {count: s.completedPages})}</span>`;
          } else {
            statusBadge = `<span class="tag-badge pending">${t('sessions.status_processing', {done: s.completedPages, total: s.totalPages, pct: pct})}</span>`;
          }

          const uploadedBadge = s.uploaded
            ? `<span class="tag-badge success" onclick="toggleUploaded('${escapeHtml(s.id)}')" title="ئۆزگەرتىش ئۈچۈن چېكىڭ / Click to toggle" style="cursor: pointer; user-select: none; font-size: 0.78rem;">✓ ${t('sessions.uploaded_yes')}</span>`
            : `<span class="tag-badge" onclick="toggleUploaded('${escapeHtml(s.id)}')" title="ئۆزگەرتىش ئۈچۈن چېكىڭ / Click to toggle" style="cursor: pointer; user-select: none; background: rgba(245, 158, 11, 0.12); color: #d97706; font-size: 0.78rem;">⏳ ${t('sessions.uploaded_no')}</span>`;

          const dateStr = s.modifiedAt ? new Date(s.modifiedAt * 1000).toLocaleString() : '-';

          return `
            <tr>
              <td>
                <div style="font-weight: 700; color: var(--slate-900); font-size: 0.95rem;">${escapeHtml(s.title)}</div>
                <div style="font-size: 0.78rem; color: var(--slate-400); font-family: monospace;">${escapeHtml(s.id)}</div>
              </td>
              <td>
                <div style="display: flex; align-items: center; gap: 0.6rem; min-width: 140px;">
                  <div style="flex: 1; height: 8px; background: var(--slate-100); border-radius: 4px; overflow: hidden;">
                    <div style="width: ${pct}%; height: 100%; background: ${s.isComplete ? 'var(--accent-emerald)' : 'var(--primary)'}; border-radius: 4px;"></div>
                  </div>
                  <span style="font-size: 0.82rem; font-weight: 700; color: var(--slate-700);">${pct}%</span>
                </div>
                <div style="font-size: 0.78rem; color: var(--slate-500); margin-top: 0.2rem;">
                  ${t('sessions.pages_completed_stat', {done: s.completedPages, total: s.totalPages})} ${s.failedPages > 0 ? `<span style="color: var(--accent-rose);">${t('sessions.pages_error_stat', {count: s.failedPages})}</span>` : ''}
                </div>
              </td>
              <td>${statusBadge}</td>
              <td>${uploadedBadge}</td>
              <td style="font-size: 0.82rem; color: var(--slate-500);">${escapeHtml(dateStr)}</td>
              <td>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                  ${s.isComplete ? `
                  <button class="btn btn-primary" onclick="viewResults('${escapeHtml(s.id)}')" style="padding: 0.35rem 0.85rem; font-size: 0.85rem;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg>
                    ${t('sessions.btn_view_results')}
                  </button>
                  ` : `
                  <button class="btn btn-primary" onclick="resumeSession('${escapeHtml(s.id)}')" style="padding: 0.35rem 0.85rem; font-size: 0.85rem;">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                    ${t('sessions.btn_resume')}
                  </button>
                  `}
                  <button class="btn btn-secondary" onclick="deleteSession('${escapeHtml(s.id)}')" title="${t('sessions.btn_delete')}" style="padding: 0.35rem 0.6rem; color: var(--accent-rose);">
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                  </button>
                </div>
              </td>
            </tr>
          `;
        }).join('');

        return sessions;
      } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 2rem; color: var(--accent-rose);">${t('errors.generic', {error: escapeHtml(err.message)})}</td></tr>`;
      }
    }

    async function toggleUploaded(sessionId) {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/toggle-uploaded`, {method: 'POST'});
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Failed to toggle status');
        }
        loadLocalSessions();
      } catch (err) {
        alert(err.message);
      }
    }

    async function viewResults(sessionId) {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/open`, {method: 'POST'});
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Failed to open results');
        }
        showSection('review');
        loadPages();
      } catch (err) {
        alert(t('errors.failed_to_start', {error: err.message}));
      }
    }

    async function resumeSession(sessionId) {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/resume`, {method: 'POST'});
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Resume failed');
        }
        const body = await res.json();
        if (body.stage === 'processing') {
          showSection('processing');
          pollProgress();
        } else if (body.stage === 'review') {
          showSection('review');
          loadPages();
        } else if (body.stage === 'queued') {
          loadLocalSessions();
        }
      } catch (err) {
        alert(t('errors.failed_to_start', {error: err.message}));
      }
    }

    async function deleteSession(sessionId) {
      if (!confirm(t('sessions.delete_confirm'))) return;
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}`, {method: 'DELETE'});
        if (!res.ok) throw new Error('Delete failed');
        loadLocalSessions();
      } catch (err) {
        alert(t('errors.failed_to_delete', {error: err.message}));
      }
    }

    async function backToLibrary() {
      currentProcessingSessionId = null;
      currentProcessingBookTitle = '';
      lastCompletedSessionId = null;
      queueCompletionToastShown = false;
      try {
        await fetch('/api/reset', {method: 'POST'});
      } catch (_) {}
      showLandingError('');
      showSection('landing');
      const sessions = await loadLocalSessions();
      if (sessions && sessions.length > 0) {
        switchLandingTab('sessions');
      } else {
        switchLandingTab('library');
      }
      searchBooks('', true);
      initBooksInfiniteScroll();
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

    // --- BACKFILL MONITOR LOGIC (INTEGRATED INTO KITABIM LIBRARY TAB) ---
    let backfillCandidates = [];
    let backfillAuditHistory = [];
    let backfillCompletedIds = new Set();
    let backfillStatus = {
      mode: 'idle',
      autoRunning: false,
      pauseRequested: false,
      isBusy: false,
      activeBook: null,
      sessionProcessedCount: 0,
      pendingIndexBooks: 0,
      maxServerBacklog: 3,
      error: null,
    };
    let backfillPollTimer = null;
    let backfillAutoFollow = true;
    let backfillSelectedPageNumber = null;
    let backfillActiveBookIdTracker = null;
    let backfillLastProcessedCount = 0;
    let backfillSaveTimeout = null;

    function isLibraryTabVisible() {
      const landingActive = sections.landing && sections.landing.classList.contains('active');
      const tabEl = document.getElementById('tabLibraryContent');
      return Boolean(landingActive && tabEl && tabEl.style.display !== 'none');
    }

    async function loadBackfillCandidates(force = false) {
      try {
        const res = await fetch('/api/backfill/candidates');
        if (!res.ok) throw new Error(await res.text());
        const data = await res.json();
        backfillCandidates = data.candidates || [];
        backfillAuditHistory = data.auditHistory || [];
        for (const item of backfillAuditHistory) {
          if (item && item.book_id) {
            backfillCompletedIds.add(String(item.book_id));
          }
        }
        if (typeof data.pendingIndexBooks === 'number') {
          backfillStatus.pendingIndexBooks = data.pendingIndexBooks;
        }
        if (typeof data.maxServerBacklog === 'number') {
          backfillStatus.maxServerBacklog = data.maxServerBacklog;
        }
        updateBackfillHeaderStats();
        syncLibraryBackfillRows();
      } catch (err) {
        console.error('Failed to load backfill candidates:', err);
        if (force) {
          showBackfillError(err.message || String(err));
        }
      }
    }

    function showBackfillError(msg) {
      const banner = document.getElementById('backfillErrorBanner');
      const txt = document.getElementById('backfillErrorText');
      if (!banner || !txt) return;
      if (msg) {
        banner.style.display = 'flex';
        txt.textContent = msg;
      } else {
        banner.style.display = 'none';
        txt.textContent = '';
      }
    }

    let libraryViewMode = 'all';

    function updateBackfillHeaderStats() {
      const eligEl = document.getElementById('backfillEligibleStatText');
      if (eligEl) {
        eligEl.textContent = t('backfill.stat_eligible', {count: backfillCandidates.length});
      }
      const backlogEl = document.getElementById('backfillBacklogStatText');
      if (backlogEl) {
        backlogEl.textContent = t('backfill.stat_backlog', {
          current: backfillStatus.pendingIndexBooks || 0,
          max: backfillStatus.maxServerBacklog || 3,
        });
      }
      const doneEl = document.getElementById('backfillSessionDoneStatText');
      if (doneEl) {
        const completedCount = Math.max(
          getBackfillCompletedBooks().length,
          backfillStatus.totalCompletedCount || 0,
          backfillStatus.sessionProcessedCount || 0
        );
        doneEl.textContent = t('backfill.stat_completed', {count: completedCount});
      }
      if (libraryViewMode === 'completed') {
        renderBackfillCompletedList();
      }
    }

    function getBackfillCompletedBooks() {
      const merged = [];
      const seen = new Set();
      const statusCompleted = Array.isArray(backfillStatus.completedBooks) ? backfillStatus.completedBooks : [];
      const lastOne = backfillStatus.lastCompletedBook ? [backfillStatus.lastCompletedBook] : [];
      const auditList = Array.isArray(backfillAuditHistory) ? backfillAuditHistory : [];
      for (const item of [...statusCompleted, ...lastOne, ...auditList]) {
        if (!item || !item.book_id) continue;
        const bid = String(item.book_id);
        if (seen.has(bid)) continue;
        seen.add(bid);
        merged.push(item);
      }
      const tbody = document.getElementById('booksTableBody');
      if (tbody) {
        const rows = tbody.querySelectorAll('tr[data-book-id]');
        rows.forEach(tr => {
          const bid = String(tr.dataset.bookId || '');
          const ocrVer = tr.dataset.ocrVersion || '';
          const uploadDate = tr.dataset.bookUploadDate || '';
          if (bid && !seen.has(bid) && ocrVer === 'surya-2.5-v2' && (!uploadDate || uploadDate < '2026-11-08')) {
            seen.add(bid);
            merged.push({
              book_id: bid,
              title: tr.dataset.bookTitle || `Kitabim #${bid}`,
              author: tr.dataset.bookAuthor || '',
              total_pages: Number(tr.dataset.bookTotalPages || 0),
              ocr_version: ocrVer,
              upload_date: uploadDate,
            });
          }
        });
      }
      return merged;
    }

    function renderBackfillCompletedList() {
      const tbody = document.getElementById('backfillCompletedTableBody');
      const badge = document.getElementById('backfillCompletedCountBadge');
      if (!tbody) return;
      const items = getBackfillCompletedBooks();
      if (badge) {
        badge.textContent = String(items.length);
      }
      if (!items.length) {
        tbody.innerHTML = `
          <tr>
            <td colspan="5" style="text-align: center; padding: 2.5rem; color: var(--slate-400);">
              ${escapeHtml(t('backfill.empty_history'))}
            </td>
          </tr>
        `;
        return;
      }
      tbody.innerHTML = items.map((item, idx) => {
        const bid = String(item.book_id || '');
        const rowEl = document.getElementById(`book-row-${bid}`);
        const title = item.title || (rowEl && rowEl.dataset.bookTitle) || `Kitabim #${bid}`;
        const totalPages = item.total_pages || 0;
        const ocrdPages = item.ocrd_pages || 0;
        const skippedPages = item.skipped_pages || 0;
        const updatedPages = item.pages_updated !== undefined ? item.pages_updated : ocrdPages;
        const elapsedStr = item.elapsed_s ? `${item.elapsed_s}s` : '';
        const tsStr = item.timestamp ? new Date(item.timestamp * 1000).toLocaleString() : '—';
        return `
          <tr>
            <td style="font-weight: 700; color: var(--slate-500);">${idx + 1}</td>
            <td>
              <div style="font-weight: 700; color: var(--slate-900); font-size: 0.95rem;">${escapeHtml(title)}</div>
              <div style="font-size: 0.78rem; color: var(--slate-400); font-family: monospace;">#${escapeHtml(bid)}</div>
            </td>
            <td>
              <div style="font-size: 0.85rem; color: var(--slate-700); font-weight: 600;">
                ${totalPages} ${escapeHtml(t('library.pages_suffix'))} · OCR: ${ocrdPages} · ${escapeHtml(t('backfill.badge_skipped'))}: ${skippedPages}
              </div>
              <div style="font-size: 0.76rem; color: var(--slate-500); margin-top: 0.15rem;">
                يېڭىلانغان: ${updatedPages} بەت ${elapsedStr ? '· ' + escapeHtml(elapsedStr) : ''}
              </div>
            </td>
            <td style="font-size: 0.82rem; color: var(--slate-500);">${escapeHtml(tsStr)}</td>
            <td style="text-align: left;">
              <button type="button" class="btn btn-primary btn-sm" onclick="startExisting('${escapeHtml(bid)}')">
                ${escapeHtml(t('library.btn_download_correct'))}
              </button>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function setLibraryViewMode(mode) {
      libraryViewMode = mode === 'completed' ? 'completed' : 'all';
      const allPanel = document.getElementById('libraryAllBooksPanel');
      const completedPanel = document.getElementById('libraryCompletedBooksPanel');
      const donePill = document.getElementById('backfillSessionDoneStatPill');
      const eligPill = document.getElementById('backfillEligibleStatPill');
      if (allPanel) {
        allPanel.style.display = libraryViewMode === 'all' ? 'block' : 'none';
      }
      if (completedPanel) {
        completedPanel.style.display = libraryViewMode === 'completed' ? 'block' : 'none';
      }
      if (donePill) {
        donePill.style.boxShadow = libraryViewMode === 'completed' ? '0 0 0 2px #059669' : '';
      }
      if (eligPill) {
        eligPill.style.boxShadow = libraryViewMode === 'all' ? '0 0 0 2px var(--primary)' : '';
      }
      if (libraryViewMode === 'completed') {
        renderBackfillCompletedList();
        try {
          const res = await fetch('/api/backfill/status');
          if (res.ok) {
            const st = await res.json();
            renderBackfillState(st);
            renderBackfillCompletedList();
          }
        } catch (_) {}
      }
    }

    function toggleBackfillCompletedView() {
      setLibraryViewMode(libraryViewMode === 'completed' ? 'all' : 'completed');
    }

    async function toggleAutoBackfill() {
      const btn = document.getElementById('backfillAutoToggleBtn');
      const procBtn = document.getElementById('processingBackfillToggleBtn');
      if (btn) btn.disabled = true;
      if (procBtn) procBtn.disabled = true;
      try {
        const shouldPause = Boolean(backfillStatus.autoRunning);
        const endpoint = shouldPause ? '/api/backfill/pause' : '/api/backfill/start';
        const res = await fetch(endpoint, {method: 'POST'});
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const status = await res.json();
        renderBackfillState(status);
        pollBackfillStatus();
        if (!shouldPause) {
          showSection('processing');
          pollProgress();
        } else if (sections.processing.classList.contains('active')) {
          pollProgress();
        }
      } catch (err) {
        showBackfillError(err.message || String(err));
      } finally {
        if (btn) btn.disabled = false;
        if (procBtn) procBtn.disabled = false;
      }
    }

    async function runBackfillOnDemand(bookId) {
      try {
        showBackfillError('');
        const row = document.getElementById(`book-row-${bookId}`);
        const cand = backfillCandidates.find(c => String(c.id) === String(bookId)) || {};
        const title = (row && row.dataset.bookTitle) || cand.title || null;
        const author = (row && row.dataset.bookAuthor) || cand.author || null;
        const uploadDate = (row && row.dataset.bookUploadDate) || cand.uploadDate || cand.upload_date || null;

        const res = await fetch(`/api/backfill/run/${encodeURIComponent(bookId)}`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({
            title: title,
            author: author,
            uploadDate: uploadDate,
          }),
        });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${res.status}`);
        }
        const status = await res.json();
        renderBackfillState(status);
        pollBackfillStatus();
        showSection('processing');
        pollProgress();
      } catch (err) {
        showBackfillError(err.message || String(err));
      }
    }

    async function pollBackfillStatus() {
      if (backfillPollTimer) {
        clearTimeout(backfillPollTimer);
        backfillPollTimer = null;
      }
      try {
        const res = await fetch('/api/backfill/status');
        if (res.ok) {
          const status = await res.json();
          const prevProcessed = backfillLastProcessedCount;
          if (status.lastCompletedBook && status.lastCompletedBook.book_id) {
            backfillCompletedIds.add(String(status.lastCompletedBook.book_id));
          }
          renderBackfillState(status);
          if ((status.sessionProcessedCount || 0) !== prevProcessed) {
            backfillLastProcessedCount = status.sessionProcessedCount || 0;
            loadBackfillCandidates(false);
          }
        }
      } catch (err) {
        console.error('Failed to poll backfill status:', err);
      }

      if (backfillStatus.isBusy || isLibraryTabVisible()) {
        const delay = backfillStatus.isBusy ? 7200 : 30000;
        backfillPollTimer = setTimeout(pollBackfillStatus, delay);
      }
    }

    function renderBackfillState(status) {
      backfillStatus = status || backfillStatus;

      if (backfillStatus.error) {
        showBackfillError(backfillStatus.error);
      } else {
        showBackfillError('');
      }

      // Update Mode Pill & Auto Toggle Button
      const dot = document.getElementById('backfillModeDot');
      const modeText = document.getElementById('backfillModeText');
      const toggleBtn = document.getElementById('backfillAutoToggleBtn');

      if (backfillStatus.autoRunning) {
        if (dot) dot.className = 'status-dot active';
        if (modeText) {
          modeText.textContent = backfillStatus.mode === 'throttled'
            ? t('backfill.status_throttled')
            : t('backfill.status_auto');
        }
        if (toggleBtn) {
          toggleBtn.className = 'btn btn-warning';
          toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg><span>${escapeHtml(t('backfill.btn_pause_auto'))}</span>`;
        }
      } else if (backfillStatus.mode === 'pausing') {
        if (dot) dot.className = 'status-dot pulsing';
        if (modeText) modeText.textContent = t('backfill.status_pausing');
        if (toggleBtn) {
          toggleBtn.className = 'btn btn-primary';
          toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${escapeHtml(t('backfill.btn_resume_auto'))}</span>`;
        }
      } else if (backfillStatus.mode === 'on_demand') {
        if (dot) dot.className = 'status-dot active';
        if (modeText) modeText.textContent = t('backfill.status_on_demand');
        if (toggleBtn) {
          toggleBtn.className = 'btn btn-success';
          toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${escapeHtml(t('backfill.btn_start_auto'))}</span>`;
        }
      } else {
        if (dot) dot.className = 'status-dot';
        if (modeText) modeText.textContent = t('backfill.status_idle');
        if (toggleBtn) {
          toggleBtn.className = 'btn btn-success';
          toggleBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg><span>${escapeHtml(t('backfill.btn_start_auto'))}</span>`;
        }
      }

      updateBackfillHeaderStats();

      const currentBookPill = document.getElementById('backfillCurrentBookPill');
      const currentBookText = document.getElementById('backfillCurrentBookText');
      const activeBook = backfillStatus.activeBook;

      if (!activeBook) {
        if (currentBookPill) currentBookPill.style.display = 'none';
        syncLibraryBackfillRows();
        return;
      }

      if (currentBookPill && currentBookText) {
        currentBookPill.style.display = 'inline-flex';
        const doneCount = activeBook.donePages || 0;
        const totalCount = activeBook.totalPages || 0;
        const progressSuffix = totalCount > 0 ? ` (${doneCount} / ${totalCount} بەت)` : '';
        currentBookText.textContent = `${activeBook.title || activeBook.bookId} (#${activeBook.bookId})${progressSuffix}`;
      }

      syncLibraryBackfillRows();
      updateBackfillHeaderStats();
    }

    function syncLibraryBackfillRows() {
      const tbody = document.getElementById('booksTableBody');
      if (!tbody) return;
      const activeId = backfillStatus.activeBook ? String(backfillStatus.activeBook.bookId) : null;
      const canRunOnDemand = !backfillStatus.autoRunning && !backfillStatus.isBusy;

      const rows = tbody.querySelectorAll('tr[data-book-id]');
      rows.forEach(tr => {
        const bid = tr.dataset.bookId;
        const ocrVer = tr.dataset.ocrVersion || '';
        const isUpgraded = ocrVer === 'surya-2.5-v2' || backfillCompletedIds.has(bid);
        const isCurrent = activeId === bid;

        tr.style.background = isCurrent ? 'rgba(245, 158, 11, 0.08)' : '';

        const verBadgeSlot = document.getElementById(`ocr-ver-badge-${bid}`);
        if (verBadgeSlot) {
          if (isUpgraded) {
            verBadgeSlot.innerHTML = `<span class="tag-badge success" style="font-size: 0.72rem; font-family: var(--font-ui);">✓ surya-2.5-v2</span>`;
          } else {
            verBadgeSlot.innerHTML = `<span class="tag-badge pending" style="font-size: 0.72rem;">Backfill كېرەك</span>`;
          }
        }

        const actionSlot = document.getElementById(`backfill-action-slot-${bid}`);
        if (actionSlot) {
          if (isCurrent) {
            actionSlot.innerHTML = `<span class="milestone-badge milestone-in_progress">⚡ ${escapeHtml(t('processing.status_processing'))}</span>`;
          } else if (isUpgraded) {
            actionSlot.innerHTML = '';
          } else {
            actionSlot.innerHTML = `
              <button type="button" class="btn btn-success btn-sm" id="btn-backfill-${escapeHtml(bid)}" onclick="runBackfillOnDemand('${escapeHtml(bid)}')" ${canRunOnDemand ? '' : 'disabled'}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                ${escapeHtml(t('backfill.btn_process_now'))}
              </button>
            `;
          }
        }
      });
    }

    function applyStaticI18n() {
      const tabSessionsLabel = document.getElementById('tabSessionsLabel');
      if (tabSessionsLabel) tabSessionsLabel.textContent = t('tabs.sessions');
      const tabLibraryLabel = document.getElementById('tabLibraryLabel');
      if (tabLibraryLabel) tabLibraryLabel.textContent = t('tabs.library');
      const tabUploadLabel = document.getElementById('tabUploadLabel');
      if (tabUploadLabel) tabUploadLabel.textContent = t('tabs.upload');
      const processingBackLabel = document.getElementById('processingBackLabel');
      if (processingBackLabel) processingBackLabel.textContent = t('processing.btn_back_home');
      const processingReviewLabel = document.getElementById('processingReviewLabel');
      if (processingReviewLabel) processingReviewLabel.textContent = t('processing.btn_view_results');
      const processingBackgroundBadge = document.getElementById('processingBackgroundBadge');
      if (processingBackgroundBadge) processingBackgroundBadge.textContent = t('processing.running_in_background');

      document.querySelectorAll('[data-i18n]').forEach(el => {
        const key = el.getAttribute('data-i18n');
        if (key) el.textContent = t(key);
      });
    }

    async function init() {
      applyStaticI18n();
      ensureSessionsAutoRefresh();
      const res = await fetch('/api/state');
      const state = await res.json();
      if (state.stage === 'processing') {
        showSection('processing');
        pollProgress();
      } else if (state.stage === 'review' && state.manualReviewSessionId) {
        showSection('review');
        loadPages();
      } else {
        showSection('landing');
        const sessions = await loadLocalSessions();
        loadBackfillCandidates(false);
        pollBackfillStatus();
        if (sessions && sessions.length > 0) {
          switchLandingTab('sessions');
        } else {
          switchLandingTab('library');
        }
        searchBooks('', true);
        initBooksInfiniteScroll();
        if (state.error) showLandingError(state.error);
      }
    }
    init();
  </script>
</body>
</html>"""


def get_app_html(lang: str = "ug", engine: Optional[str] = None) -> str:
    i18n_json = get_translations_json(lang)
    engine_label = "Surya OCR"
    return _APP_HTML.replace("__I18N_JSON__", i18n_json).replace(
        "__OCR_ENGINE_LABEL__", engine_label
    )


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


def _create_upload_workdir(
    pdf_bytes: bytes, work_root: Path, filename: Optional[str] = None
) -> OcrWorkDir:
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    total_pages = len(doc)

    out_dir = work_root / f"upload-{int(time.time() * 1000)}"
    out_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = out_dir / "book.pdf"
    pdf_path.write_bytes(pdf_bytes)

    workdir = OcrWorkDir.create(
        out_dir,
        source_pdf=pdf_path,
        total_pages=total_pages,
        original_filename=filename,
    )
    for page_number in range(1, total_pages + 1):
        workdir.set_page(
            page_number, text="", is_toc=False, confidence=0.0, status="pending"
        )
    workdir.save()
    return workdir


def _was_abandoned(state: "AppState", workdir: OcrWorkDir) -> bool:
    """Whether the user explicitly navigated away from this session (reset)
    while it kept processing in the background.

    Consumes the marker: once checked, the session is no longer considered
    abandoned, so a later restart of the same session_id is unaffected.
    """
    session_id = workdir.root.name
    if session_id in state.abandoned_session_ids:
        state.abandoned_session_ids.discard(session_id)
        return True
    return False


async def _run_ocr_background(
    workdir: OcrWorkDir,
    state: "AppState",
    concurrency: Optional[int] = None,
) -> None:
    target_concurrency = resolve_concurrency(
        state.engine, concurrency if concurrency is not None else state.concurrency
    )
    try:
        async with acquire_surya_gpu_lock_async(state.work_root):
            doc = fitz.open(workdir.source_pdf)
            predictor = await get_recognition_predictor(state.engine)
            sem = asyncio.Semaphore(max(1, target_concurrency))
            fresh_pages: set[int] = set()
            hyphen_pages: set[int] = set()

            async def process_one(page_number: int):
                current_page = workdir._pages.get(page_number)
                if current_page and current_page.status in (
                    "ocrd",
                    "reviewed",
                    "from_kitabim",
                ):
                    return

                async with sem:
                    with workdir.save_lock:
                        workdir.set_page(
                            page_number,
                            text="",
                            is_toc=False,
                            confidence=0.0,
                            status="processing",
                        )
                        workdir.save()

                    fitz_page = doc.load_page(page_number - 1)
                    img_path = workdir.image_path(page_number)
                    if not img_path.exists():
                        try:
                            img_path.parent.mkdir(parents=True, exist_ok=True)
                            img_path.write_bytes(render_page_png(doc, page_number))
                        except Exception:
                            pass
                    try:
                        text = await ocr_page(
                            fitz_page,
                            predictor,
                            max_parallel_pages=target_concurrency,
                            timeout=get_configured_page_timeout(),
                        )
                        meta = pop_last_page_ocr_meta(fitz_page)
                        detected_num = meta.detected_page_number if meta else None
                        ended_hyphen = (
                            meta.ended_with_hyphen
                            if meta
                            else text_ends_with_hyphen(text)
                        )
                        with workdir.save_lock:
                            existing = workdir._pages.get(page_number)
                            if existing and existing.status == "reviewed":
                                workdir.set_page(
                                    page_number,
                                    text=existing.text,
                                    is_toc=existing.is_toc,
                                    confidence=1.0,
                                    status="reviewed",
                                    detected_page_number=existing.detected_page_number
                                    or detected_num,
                                )
                            else:
                                is_toc = bool(
                                    existing and existing.is_toc
                                ) or is_toc_page(text)
                                workdir.set_page(
                                    page_number,
                                    text=text,
                                    is_toc=is_toc,
                                    confidence=1.0,
                                    status="ocrd",
                                    detected_page_number=detected_num,
                                    ended_with_hyphen=ended_hyphen,
                                )
                                fresh_pages.add(page_number)
                                if ended_hyphen:
                                    hyphen_pages.add(page_number)
                            workdir.save()
                    except (TimeoutError, asyncio.TimeoutError) as exc:
                        logger.warning(
                            "Page %s timed out during OCR: %s", page_number, exc
                        )
                        with workdir.save_lock:
                            existing = workdir._pages.get(page_number)
                            if existing and existing.status == "reviewed":
                                pass
                            else:
                                workdir.set_page(
                                    page_number,
                                    text=existing.text if existing else "",
                                    is_toc=existing.is_toc if existing else False,
                                    confidence=0.0,
                                    status="failed",
                                    error=str(exc) or "OCR timed out",
                                )
                                workdir.save()
                    except LowConfidenceOcrError as exc:
                        with workdir.save_lock:
                            existing = workdir._pages.get(page_number)
                            if existing and existing.status == "reviewed":
                                pass
                            else:
                                workdir.set_page(
                                    page_number,
                                    text=existing.text if existing else "",
                                    is_toc=existing.is_toc if existing else False,
                                    confidence=0.0,
                                    status="failed",
                                    error=str(exc),
                                )
                                workdir.save()
                    except Exception as exc:
                        with workdir.save_lock:
                            existing = workdir._pages.get(page_number)
                            if existing and existing.status == "reviewed":
                                pass
                            else:
                                workdir.set_page(
                                    page_number,
                                    text=existing.text if existing else "",
                                    is_toc=existing.is_toc if existing else False,
                                    confidence=0.0,
                                    status="failed",
                                    error=f"Unexpected OCR error: {exc}",
                                )
                                workdir.save()

            tasks = [process_one(p) for p in range(1, workdir.total_pages + 1)]
            await asyncio.gather(*tasks)
            if fresh_pages and hyphen_pages:
                with workdir.save_lock:
                    pages_list = workdir.all_pages()
                    if apply_cross_page_dehyphenation(
                        pages_list,
                        fresh_page_numbers=fresh_pages,
                        hyphen_ended_pages=hyphen_pages,
                    ):
                        workdir.save()
        if not _was_abandoned(state, workdir):
            has_next = bool(
                state.queue_manager and state.queue_manager.queued_session_ids
            )
            is_reviewing_other = (
                state.stage == "review"
                and getattr(state, "manual_review_session_id", None) is not None
                and state.manual_review_session_id != workdir.root.name
            )
            if not is_reviewing_other:
                # If more books are queued, keep stage as processing so the queue
                # advances directly to the next book without flashing review stage.
                if not has_next:
                    state.stage = "review"
    except Exception as exc:
        if not _was_abandoned(state, workdir):
            is_reviewing_other = (
                state.stage == "review"
                and getattr(state, "manual_review_session_id", None) is not None
                and state.manual_review_session_id != workdir.root.name
            )
            if not is_reviewing_other:
                state.stage = "error"
                state.error = str(exc)


def list_local_sessions(
    work_root: Path, queue_manager: Optional[BookQueueManager] = None
) -> list[dict]:
    sessions = []
    if not work_root.exists():
        return sessions
    for item in sorted(
        work_root.iterdir(),
        key=lambda p: p.stat().st_mtime if p.is_dir() else 0,
        reverse=True,
    ):
        if not item.is_dir():
            continue
        book_json = item / "book.json"
        if not book_json.exists():
            continue
        try:
            workdir = OcrWorkDir.load(item)
            pages = workdir.all_pages()
            total = workdir.total_pages or len(pages)
            done = sum(
                1 for p in pages if p.status in ("ocrd", "reviewed", "from_kitabim")
            )
            failed = sum(1 for p in pages if p.status == "failed")
            pending = total - done - failed

            title = item.name
            if workdir.original_filename:
                title = workdir.original_filename
            elif workdir.book_id:
                title = f"Kitabim كىتاب #{workdir.book_id}"
            elif (item / "book.pdf").exists():
                title = item.name

            mtime = item.stat().st_mtime
            queue_pos = (
                queue_manager.get_queue_position(item.name) if queue_manager else None
            )
            is_complete = (done + failed >= total) and total > 0
            q_status = workdir.queue_status
            if is_complete and q_status in ("queued", None, "idle"):
                q_status = "completed"

            sessions.append(
                {
                    "id": item.name,
                    "title": title,
                    "originalFilename": workdir.original_filename,
                    "bookId": workdir.book_id,
                    "totalPages": total,
                    "completedPages": done,
                    "failedPages": failed,
                    "pendingPages": pending,
                    "modifiedAt": mtime,
                    "isComplete": is_complete,
                    "uploaded": workdir.uploaded,
                    "uploadedAt": workdir.uploaded_at,
                    "queueStatus": q_status,
                    "queuePosition": queue_pos,
                }
            )
        except Exception:
            continue
    return sessions


_BACKGROUND_TASKS: set[asyncio.Task] = set()


def _start_background_task(coro) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


@dataclass
class BackfillManager:
    client: KitabimClient
    work_root: Path
    engine: str
    get_concurrency: Callable[[], int]
    is_queue_busy: Optional[Callable[[], bool]] = None
    on_idle: Optional[Callable[[], None]] = None
    max_server_backlog: int = 3
    poll_interval: float = 15.0
    ocr_version: str = OCR_ENGINE_VERSION

    auto_running: bool = False
    pause_requested: bool = False
    mode: str = "idle"
    active_book_id: Optional[str] = None
    active_book_title: Optional[str] = None
    active_book_author: Optional[str] = None
    active_book_upload_date: Optional[str] = None
    active_phase: Optional[str] = None
    active_total_pages: int = 0
    active_pages: dict[int, PageState] = field(default_factory=dict)
    active_user_edits: dict[int, dict[str, Any]] = field(default_factory=dict)
    latest_completed_page: Optional[int] = None
    last_completed_book: Optional[dict[str, Any]] = None
    session_completed_books: list[dict[str, Any]] = field(default_factory=list)
    _server_backfilled_cache: Optional[list[dict[str, Any]]] = None
    session_processed_count: int = 0
    pending_index_books: int = 0
    _baseline_server_backlog: Optional[int] = None
    error: Optional[str] = None
    seen_book_ids: set[str] = field(default_factory=set)
    failed_book_ids: set[str] = field(default_factory=set)
    _task: Optional[asyncio.Task] = None
    _wake_event: Optional[asyncio.Event] = None

    @property
    def audit_log_path(self) -> Path:
        return self.work_root / "backfill_audit.jsonl"

    def _collect_completed_books(self) -> list[dict[str, Any]]:
        completed_books: list[dict[str, Any]] = []
        seen_completed: set[str] = set()
        for item in (
            list(self.session_completed_books)
            + list(read_backfill_audit_log(self.audit_log_path, limit=500))
            + list(self._server_backfilled_cache or [])
        ):
            bid = str(item.get("book_id") or "")
            if bid and bid not in seen_completed:
                seen_completed.add(bid)
                completed_books.append(item)
        return completed_books

    def get_status(self) -> dict[str, Any]:
        active_book_payload: Optional[dict[str, Any]] = None
        active_id = self.active_book_id
        if active_id is not None:
            snapshot = dict(self.active_pages)
            ordered = [snapshot[p] for p in sorted(snapshot)]
            ocrd_count = sum(1 for p in ordered if p.status in ("ocrd", "reviewed"))
            skipped_count = sum(1 for p in ordered if p.status == "skipped")
            failed_count = sum(1 for p in ordered if p.status == "failed")
            processing_count = sum(1 for p in ordered if p.status == "processing")
            done_count = ocrd_count + skipped_count + failed_count
            active_book_payload = {
                "bookId": active_id,
                "title": self.active_book_title or active_id,
                "author": self.active_book_author or "",
                "uploadDate": self.active_book_upload_date,
                "phase": self.active_phase or "downloading",
                "totalPages": self.active_total_pages or len(ordered),
                "donePages": done_count,
                "ocrdPages": ocrd_count,
                "skippedPages": skipped_count,
                "failedPages": failed_count,
                "processingPages": processing_count,
                "latestCompletedPage": self.latest_completed_page,
                "pages": [
                    {
                        "pageNumber": p.page_number,
                        "status": p.status,
                        "text": p.text,
                        "isToc": p.is_toc,
                        "skipped": p.skipped,
                        "detectedPageNumber": p.detected_page_number,
                        "error": p.error,
                    }
                    for p in ordered
                ],
            }
        completed_books = self._collect_completed_books()

        return {
            "mode": self.mode,
            "autoRunning": self.auto_running,
            "pauseRequested": self.pause_requested,
            "isBusy": bool(active_id is not None or self.auto_running),
            "activeBook": active_book_payload,
            "lastCompletedBook": self.last_completed_book,
            "completedBooks": completed_books,
            "totalCompletedCount": len(completed_books),
            "sessionProcessedCount": self.session_processed_count,
            "pendingIndexBooks": self.pending_index_books,
            "maxServerBacklog": self.max_server_backlog,
            "failedBookIds": sorted(self.failed_book_ids),
            "error": self.error,
        }

    def fetch_candidates_and_history(self, limit: int = 500) -> dict[str, Any]:
        cand_resp = self.client.get_backfill_candidates(
            ocr_version=self.ocr_version, limit=limit
        )
        pending_backlog = int(
            cand_resp.get(
                "pending_index_books",
                cand_resp.get("pendingIndexBooks", 0),
            )
            or 0
        )
        # Note: Unlike the CLI (which uses raw `pending_backlog`), when GUI auto-backfill
        # starts with `session_processed_count == 0` against a server that already has
        # pre-existing stuck books (`pending_backlog >= max_server_backlog`), we capture
        # that initial count as `_baseline_server_backlog` so legacy stuck rows do not
        # permanently deadlock the GUI auto-runner before any book is processed.
        if self.auto_running and self._baseline_server_backlog is None:
            if (
                self.session_processed_count == 0
                and pending_backlog >= self.max_server_backlog
            ):
                self._baseline_server_backlog = pending_backlog
            else:
                self._baseline_server_backlog = 0
        elif (
            self._baseline_server_backlog is not None
            and pending_backlog < self._baseline_server_backlog
        ):
            self._baseline_server_backlog = pending_backlog
        effective_backlog = max(
            0, pending_backlog - (self._baseline_server_backlog or 0)
        )
        self.pending_index_books = effective_backlog
        raw_candidates = cand_resp.get("candidates") or []
        normalized: list[dict[str, Any]] = []
        for c in raw_candidates:
            cid = str(c.get("id") or "")
            if not cid or cid in self.seen_book_ids or cid in self.failed_book_ids:
                continue
            upload_date = c.get("uploadDate") or c.get("upload_date")
            total_pages = c.get("totalPages") or c.get("total_pages") or 0
            ocr_ver = c.get("ocrVersion") or c.get("ocr_version")
            normalized.append(
                {
                    "id": cid,
                    "title": c.get("title") or "",
                    "author": c.get("author") or "",
                    "volume": c.get("volume"),
                    "totalPages": int(total_pages),
                    "status": c.get("status") or "pending",
                    "ocrVersion": ocr_ver,
                    "uploadDate": upload_date,
                }
            )
        # Ensure oldest uploaded book is strictly first
        normalized.sort(key=lambda item: (item.get("uploadDate") or "", item["id"]))
        if self._server_backfilled_cache is None:
            server_backfilled: list[dict[str, Any]] = []
            try:
                books_resp = self.client.list_books(
                    page=1, page_size=50, sort_by="uploadDate", order=1
                )
                for b in (
                    books_resp.get("books") if isinstance(books_resp, dict) else []
                ) or []:
                    bid = str(b.get("id") or "")
                    b_ver = b.get("ocrVersion") or b.get("ocr_version")
                    up_date = str(b.get("uploadDate") or b.get("upload_date") or "")
                    if (
                        bid
                        and b_ver == self.ocr_version
                        and (not up_date or up_date < "2026-11-08")
                    ):
                        server_backfilled.append(
                            {
                                "book_id": bid,
                                "title": b.get("title") or "",
                                "author": b.get("author") or "",
                                "ocr_version": b_ver,
                                "total_pages": int(
                                    b.get("totalPages") or b.get("total_pages") or 0
                                ),
                                "ocrd_pages": int(
                                    b.get("totalPages") or b.get("total_pages") or 0
                                ),
                                "skipped_pages": 0,
                                "failed_pages": 0,
                                "upload_date": up_date,
                                "timestamp": None,
                            }
                        )
            except Exception:
                pass
            self._server_backfilled_cache = server_backfilled

        audit_history = self._collect_completed_books()
        return {
            "candidates": normalized,
            "pendingIndexBooks": self.pending_index_books,
            "maxServerBacklog": self.max_server_backlog,
            "auditHistory": audit_history,
        }

    async def _process_book(
        self,
        book_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        upload_date: Optional[str] = None,
    ) -> dict[str, Any]:
        self.active_book_id = book_id
        self.active_book_title = title or book_id
        self.active_book_author = author or ""
        self.active_book_upload_date = upload_date
        self.active_phase = "downloading"
        self.active_total_pages = 0
        self.active_pages.clear()
        self.active_user_edits.clear()
        self.latest_completed_page = None
        completed_cleanly = False

        def _on_progress(evt: dict[str, Any]) -> None:
            phase = evt.get("phase")
            if phase:
                self.active_phase = str(phase)
            if evt.get("title"):
                self.active_book_title = str(evt["title"])
            if evt.get("total_pages"):
                self.active_total_pages = int(evt["total_pages"])
            pno = evt.get("page_number")
            st = evt.get("status")
            if isinstance(pno, int) and st in ("ocrd", "skipped", "failed"):
                if st == "ocrd" or self.latest_completed_page is None:
                    self.latest_completed_page = pno

        try:
            async with acquire_surya_gpu_lock_async(self.work_root):
                entry = await backfill_single_book(
                    book_id,
                    self.client,
                    self.work_root,
                    title=title,
                    engine=self.engine,
                    concurrency=self.get_concurrency(),
                    audit_log_path=self.audit_log_path,
                    ocr_version=self.ocr_version,
                    on_progress=_on_progress,
                    pages_sink=self.active_pages,
                    user_edits=self.active_user_edits,
                    install_signal_handlers=False,
                )
            completed_cleanly = int(entry.get("failed_pages", 0) or 0) == 0
            self.seen_book_ids.add(book_id)
            self.failed_book_ids.discard(book_id)
            self.last_completed_book = entry
            self.session_completed_books.insert(0, entry)
            self.session_processed_count += 1
            return entry
        finally:
            self.active_book_id = None
            self.active_book_title = None
            self.active_book_author = None
            self.active_book_upload_date = None
            self.active_phase = None
            self.active_total_pages = 0
            self.active_pages.clear()
            self.active_user_edits.clear()
            self.latest_completed_page = None
            if completed_cleanly:
                shutil.rmtree(
                    self.work_root / f"backfill-{book_id}", ignore_errors=True
                )

    async def _auto_loop(self) -> None:
        try:
            with prevent_macos_sleep():
                while self.auto_running and not self.pause_requested:
                    data = await asyncio.to_thread(
                        self.fetch_candidates_and_history, 100
                    )
                    if not self.auto_running or self.pause_requested:
                        break
                    candidates = data.get("candidates") or []
                    if not candidates:
                        break

                    if self.pending_index_books >= self.max_server_backlog:
                        self.mode = "throttled"
                        if self._wake_event is None:
                            self._wake_event = asyncio.Event()
                        self._wake_event.clear()
                        try:
                            await asyncio.wait_for(
                                self._wake_event.wait(), timeout=self.poll_interval
                            )
                        except asyncio.TimeoutError:
                            pass
                        continue

                    target = candidates[0]
                    target_id = str(target["id"])
                    self.mode = "pausing" if self.pause_requested else "auto"
                    try:
                        await self._process_book(
                            target_id,
                            title=target.get("title"),
                            author=target.get("author"),
                            upload_date=target.get("uploadDate"),
                        )
                    except Exception as book_exc:
                        logger.warning(
                            "Auto backfill failed on book %s (recording failure and continuing): %s",
                            target_id,
                            book_exc,
                        )
                        self.failed_book_ids.add(target_id)
                        self.error = f"Book {target_id} failed: {book_exc}"
                        continue
        except Exception as exc:
            logger.exception("Auto backfill loop failed: %s", exc)
            self.error = str(exc)
        finally:
            self.auto_running = False
            self.pause_requested = False
            self.mode = "idle"
            if self.on_idle is not None:
                self.on_idle()

    async def _on_demand_then_maybe_auto(
        self,
        book_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        upload_date: Optional[str] = None,
    ) -> None:
        try:
            await self._process_book(
                book_id, title=title, author=author, upload_date=upload_date
            )
            if self.auto_running and not self.pause_requested:
                await self._auto_loop()
        except Exception as exc:
            logger.exception("On-demand backfill failed for book %s: %s", book_id, exc)
            self.failed_book_ids.add(book_id)
            self.error = str(exc)
        finally:
            if not self.auto_running:
                self.pause_requested = False
                self.mode = "idle"
                if self.on_idle is not None:
                    self.on_idle()

    def start_auto(self) -> dict[str, Any]:
        if self.is_queue_busy is not None and self.is_queue_busy():
            raise HTTPException(
                status_code=409,
                detail="Local OCR queue is currently busy; wait for it to finish before starting backfill",
            )
        self.error = None
        self.auto_running = True
        self.pause_requested = False
        if self._task is not None and not self._task.done():
            self.mode = "auto"
            if self._wake_event is not None:
                self._wake_event.set()
            return self.get_status()
        self.mode = "auto"
        self._wake_event = asyncio.Event()
        self._task = _start_background_task(self._auto_loop())
        return self.get_status()

    def pause_auto(self) -> dict[str, Any]:
        self.auto_running = False
        if self.active_book_id is not None:
            self.pause_requested = True
            self.mode = "pausing"
        else:
            self.pause_requested = False
            self.mode = "idle"
        if self._wake_event is not None:
            self._wake_event.set()
        return self.get_status()

    def start_on_demand(
        self,
        book_id: str,
        title: Optional[str] = None,
        author: Optional[str] = None,
        upload_date: Optional[str] = None,
    ) -> dict[str, Any]:
        if self.is_queue_busy is not None and self.is_queue_busy():
            raise HTTPException(
                status_code=409,
                detail="Local OCR queue is currently busy; wait for it to finish before starting backfill",
            )
        if self.auto_running:
            raise HTTPException(
                status_code=409,
                detail="Pause automatic backfill before running a book on-demand",
            )
        if self.active_book_id is not None or (
            self._task is not None and not self._task.done()
        ):
            raise HTTPException(
                status_code=409,
                detail="Another book is currently being processed",
            )
        self.error = None
        self.auto_running = False
        self.pause_requested = False
        self.mode = "on_demand"
        self._wake_event = asyncio.Event()
        self._task = _start_background_task(
            self._on_demand_then_maybe_auto(
                book_id, title=title, author=author, upload_date=upload_date
            )
        )
        return self.get_status()

    def get_active_page_image_bytes(self, page_number: int) -> bytes:
        book_id = self.active_book_id
        if not book_id:
            raise HTTPException(status_code=404, detail="No active backfill book")
        tmp_dir = self.work_root / f"backfill-{book_id}"
        pdf_path = tmp_dir / "book.pdf"
        if not pdf_path.exists():
            raise HTTPException(status_code=404, detail="Backfill PDF not ready yet")
        img_path = tmp_dir / "pages" / f"{page_number:04d}.png"
        if img_path.exists():
            return img_path.read_bytes()
        with fitz.open(pdf_path) as doc:
            if page_number < 1 or page_number > len(doc):
                raise HTTPException(status_code=404, detail="Page not found")
            png_bytes = render_page_png(doc, page_number)
        # Only cache to disk if the book is still active and its PDF still exists,
        # so a racing request at book completion never recreates an orphan folder.
        if self.active_book_id == book_id and pdf_path.exists():
            try:
                img_path.parent.mkdir(parents=True, exist_ok=True)
                img_path.write_bytes(png_bytes)
            except Exception:
                pass
        return png_bytes

    def list_active_pages(self) -> list[dict[str, Any]]:
        snapshot = dict(self.active_pages)
        ordered = [snapshot[p] for p in sorted(snapshot)]
        return [
            {
                "pageNumber": p.page_number,
                "text": p.text,
                "isToc": p.is_toc,
                "confidence": p.confidence,
                "status": p.status,
                "error": p.error,
            }
            for p in ordered
        ]

    def update_active_page(
        self, page_number: int, body: UpdatePageRequest
    ) -> dict[str, Any]:
        book_id = self.active_book_id
        snapshot = dict(self.active_pages)
        if not book_id or page_number not in snapshot:
            raise HTTPException(
                status_code=404, detail="Active backfill page not found"
            )
        if self.active_phase == "submitting":
            raise HTTPException(
                status_code=409,
                detail="Cannot edit page while book is submitting to server",
            )
        page = snapshot[page_number]
        if page.status in ("pending", "processing"):
            raise HTTPException(
                status_code=409,
                detail="Cannot edit a page while it is pending or processing",
            )
        edit_entry = dict(self.active_user_edits.get(page_number) or {})
        if body.text is not None:
            page.text = body.text
            page.status = "reviewed"
            edit_entry["text"] = body.text
        if body.isToc is not None:
            page.is_toc = bool(body.isToc)
            page.status = "reviewed"
            edit_entry["is_toc"] = bool(body.isToc)
        self.active_user_edits[page_number] = edit_entry

        ckpt_path = self.work_root / f"backfill-{book_id}" / "checkpoint.jsonl"
        if ckpt_path.parent.exists():
            try:
                _append_page_checkpoint(
                    ckpt_path,
                    {
                        "ocr_version": self.ocr_version,
                        "page_number": page.page_number,
                        "text": page.text,
                        "is_toc": page.is_toc,
                        "detected_page_number": page.detected_page_number,
                        "ended_with_hyphen": page.ended_with_hyphen,
                    },
                )
            except Exception:
                pass

        return {
            "pageNumber": page.page_number,
            "text": page.text,
            "isToc": page.is_toc,
            "status": page.status,
        }


class BackfillOnDemandRequest(BaseModel):
    title: Optional[str] = None
    author: Optional[str] = None
    uploadDate: Optional[str] = None


@dataclass
class AppState:
    client: KitabimClient
    work_root: Path
    stage: str = "landing"
    workdir: Optional[OcrWorkDir] = None
    error: Optional[str] = None
    engine: str = field(default_factory=get_configured_engine)
    concurrency: int = field(default_factory=get_configured_concurrency)
    queue_manager: Optional[BookQueueManager] = None
    abandoned_session_ids: set[str] = field(default_factory=set)
    manual_review_session_id: Optional[str] = None
    backfill_manager: Optional[BackfillManager] = None


def _require_landing_stage(state: AppState) -> None:
    if state.stage != "landing":
        raise HTTPException(
            status_code=409, detail="A book is already active; reset first"
        )


def _require_active_workdir(state: AppState) -> None:
    if state.workdir is None:
        if state.queue_manager and state.queue_manager.active_session_id:
            # Reuse the queue's own live OcrWorkDir instance when there is one,
            # rather than loading a second, independent copy from disk that
            # would silently diverge from (and could overwrite) the
            # in-progress job's own in-memory changes.
            live = state.queue_manager.active_workdir
            if live is not None:
                state.workdir = live
                return
            target_dir = state.work_root / state.queue_manager.active_session_id
            if target_dir.exists():
                try:
                    state.workdir = OcrWorkDir.load(target_dir)
                    return
                except Exception:
                    logger.warning(
                        "Failed to hydrate active workdir for session %s",
                        state.queue_manager.active_session_id,
                        exc_info=True,
                    )
        raise HTTPException(status_code=409, detail="No active book")


def create_landing_app(
    client: KitabimClient,
    work_root: Path,
    engine: Optional[str] = None,
    concurrency: Optional[int] = None,
) -> FastAPI:
    target_engine = (engine or get_configured_engine()).strip().lower()
    target_concurrency = resolve_concurrency(target_engine, concurrency)
    state = AppState(
        client=client,
        work_root=work_root,
        engine=target_engine,
        concurrency=target_concurrency,
    )

    async def ocr_runner(workdir: OcrWorkDir):
        is_reviewing_other = (
            state.stage == "review"
            and getattr(state, "manual_review_session_id", None) is not None
            and state.manual_review_session_id != workdir.root.name
        )
        if not is_reviewing_other:
            state.workdir = workdir
            state.stage = "processing"
            state.error = None
        await _run_ocr_background(workdir, state)

    def launch_bg(coro):
        return _start_background_task(coro)

    queue_manager = BookQueueManager(
        work_root=work_root, runner=ocr_runner, task_launcher=launch_bg
    )
    state.queue_manager = queue_manager

    def _is_queue_busy() -> bool:
        return bool(
            state.queue_manager
            and (
                state.queue_manager.active_session_id is not None
                or bool(state.queue_manager.queued_session_ids)
            )
        )

    def _on_backfill_idle() -> None:
        if state.workdir is None and state.stage == "processing":
            state.stage = "landing"

    state.backfill_manager = BackfillManager(
        client=client,
        work_root=work_root,
        engine=target_engine,
        get_concurrency=lambda: state.concurrency,
        is_queue_busy=_is_queue_busy,
        on_idle=_on_backfill_idle,
    )
    queue_manager.reset_interrupted_sessions()

    app = FastAPI()
    app.state.app_state = state

    @app.on_event("startup")
    async def on_startup():
        queue_manager.reset_interrupted_sessions()

    @app.get("/", response_class=HTMLResponse)
    def index(lang: str = "ug"):
        return get_app_html(lang, engine=state.engine)

    @app.get("/fonts/{filename}")
    def serve_font(filename: str):
        font_path = FONTS_DIR / filename
        if not font_path.is_file():
            raise HTTPException(status_code=404, detail="Font not found")
        return FileResponse(font_path, media_type="font/woff2")

    @app.get("/api/locales/{lang}")
    def get_locale(lang: str):
        return get_translations(lang)

    @app.get("/api/locales")
    def get_default_locale():
        return get_translations("ug")

    @app.get("/api/state")
    def get_state():
        active_id = (
            state.queue_manager.active_session_id if state.queue_manager else None
        )
        active_title = None
        if state.workdir:
            active_title = state.workdir.original_filename or state.workdir.root.name
        elif state.queue_manager and state.queue_manager.active_workdir:
            active_title = (
                state.queue_manager.active_workdir.original_filename
                or state.queue_manager.active_workdir.root.name
            )
        bm = state.backfill_manager
        is_backfill = bool(bm and (bm.active_book_id or bm.auto_running))
        if not active_id and bm and bm.active_book_id:
            active_id = f"backfill-{bm.active_book_id}"
            active_title = bm.active_book_title or bm.active_book_id
        return {
            "stage": state.stage,
            "error": state.error,
            "sessionId": state.workdir.root.name if state.workdir else active_id,
            "activeSessionId": active_id,
            "title": active_title,
            "queuedSessions": (
                state.queue_manager.queued_session_ids if state.queue_manager else []
            ),
            "manualReviewSessionId": getattr(state, "manual_review_session_id", None),
            "engine": state.engine,
            "concurrency": state.concurrency,
            "isBackfill": is_backfill,
            "backfillAutoRunning": bool(bm and bm.auto_running),
            "backfillMode": bm.mode if bm else "idle",
            "backfillPhase": bm.active_phase if bm else None,
        }

    @app.post("/api/concurrency")
    def set_concurrency(payload: dict):
        # Only affects jobs started after this call — a running job already
        # captured its own concurrency into a fixed asyncio.Semaphore.
        new_val = payload.get("concurrency")
        if new_val is not None:
            try:
                val = int(new_val)
            except (ValueError, TypeError):
                raise HTTPException(status_code=400, detail="Invalid concurrency value")
            state.concurrency = resolve_concurrency(state.engine, val)
        return {"status": "ok", "concurrency": state.concurrency}

    @app.get("/api/sessions")
    def get_sessions():
        return list_local_sessions(state.work_root, state.queue_manager)

    @app.post("/api/sessions/{session_id}/open")
    def open_session(session_id: str):
        session_dir = state.work_root / session_id
        if not session_dir.is_dir() or not (session_dir / "book.json").exists():
            raise HTTPException(status_code=404, detail="Session not found")

        if (
            state.queue_manager
            and state.queue_manager.active_session_id == session_id
            and state.queue_manager.active_workdir is not None
        ):
            workdir = state.queue_manager.active_workdir
        elif state.workdir is not None and state.workdir.root.name == session_id:
            workdir = state.workdir
        else:
            try:
                workdir = OcrWorkDir.load(session_dir)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Failed to load session: {exc}"
                )

        state.workdir = workdir
        state.manual_review_session_id = session_id
        state.stage = "review"
        state.error = None
        return {
            "stage": "review",
            "sessionId": workdir.root.name,
            "title": workdir.original_filename or workdir.root.name,
        }

    @app.post("/api/sessions/{session_id}/resume")
    async def resume_session(session_id: str):
        if (
            state.workdir
            and state.workdir.root.name == session_id
            and state.stage != "landing"
        ):
            return {"stage": state.stage, "sessionId": session_id}

        session_dir = state.work_root / session_id
        if not session_dir.is_dir() or not (session_dir / "book.json").exists():
            raise HTTPException(status_code=404, detail="Session not found")

        if (
            state.queue_manager
            and state.queue_manager.active_session_id == session_id
            and state.queue_manager.active_workdir is not None
        ):
            workdir = state.queue_manager.active_workdir
        else:
            try:
                workdir = OcrWorkDir.load(session_dir)
            except Exception as exc:
                raise HTTPException(
                    status_code=500, detail=f"Failed to load session: {exc}"
                )

        pages = workdir.all_pages()
        pending = [
            p
            for p in pages
            if p.status not in ("ocrd", "reviewed", "from_kitabim", "failed")
        ]
        if pending:
            if state.backfill_manager and (
                state.backfill_manager.active_book_id is not None
                or state.backfill_manager.auto_running
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Backfill is currently running; pause backfill first",
                )
            pos, is_active = await state.queue_manager.enqueue(workdir.root.name)
            is_reviewing_other = (
                state.stage == "review"
                and getattr(state, "manual_review_session_id", None) is not None
                and state.manual_review_session_id != session_id
            )
            if is_active and not is_reviewing_other:
                state.workdir = workdir
                state.stage = "processing"
                state.error = None
                state.manual_review_session_id = None
            return {
                "stage": "processing" if is_active else "queued",
                "sessionId": workdir.root.name,
                "queuePosition": pos,
                "isProcessing": is_active,
            }
        else:
            is_reviewing_other = (
                state.stage == "review"
                and getattr(state, "manual_review_session_id", None) is not None
                and state.manual_review_session_id != session_id
            )
            if not is_reviewing_other:
                state.workdir = workdir
                state.stage = "review"
                state.error = None
                state.manual_review_session_id = None
            return {
                "stage": "review",
                "sessionId": workdir.root.name,
                "queuePosition": None,
                "isProcessing": False,
            }

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        if state.queue_manager and state.queue_manager.active_session_id == session_id:
            raise HTTPException(
                status_code=409, detail="Cannot delete active processing session"
            )
        if state.queue_manager:
            state.queue_manager.cancel(session_id)
        session_dir = state.work_root / session_id
        if not session_dir.is_dir():
            raise HTTPException(status_code=404, detail="Session not found")
        if state.workdir and state.workdir.root.name == session_id:
            state.workdir = None
            state.stage = "landing"
        try:
            shutil.rmtree(session_dir)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to delete session: {exc}"
            )
        return {"status": "deleted", "id": session_id}

    @app.post("/api/sessions/{session_id}/toggle-uploaded")
    def toggle_session_uploaded(session_id: str):
        session_dir = state.work_root / session_id
        if not (session_dir / "book.json").exists():
            raise HTTPException(status_code=404, detail="Session not found")

        if (
            state.queue_manager
            and state.queue_manager.active_session_id == session_id
            and state.queue_manager.active_workdir is not None
        ):
            workdir = state.queue_manager.active_workdir
        elif state.workdir is not None and state.workdir.root.name == session_id:
            workdir = state.workdir
        else:
            workdir = OcrWorkDir.load(session_dir)

        with workdir.save_lock:
            workdir.uploaded = not workdir.uploaded
            workdir.uploaded_at = time.time() if workdir.uploaded else None
            if not workdir.uploaded:
                workdir.book_id = None
            workdir.save_metadata()

        return {
            "id": session_id,
            "uploaded": workdir.uploaded,
            "uploadedAt": workdir.uploaded_at,
        }

    @app.post("/api/reset")
    def reset():
        if (
            state.workdir is not None
            and state.queue_manager
            and state.queue_manager.active_session_id == state.workdir.root.name
        ):
            # Still processing in the background — don't let it resurrect the
            # global stage once it finishes; the session's own on-disk status
            # (and the sessions list) reflects its real outcome regardless.
            state.abandoned_session_ids.add(state.workdir.root.name)
            state.queue_manager.cancel(state.workdir.root.name)
        state.manual_review_session_id = None
        state.workdir = None
        state.stage = "landing"
        state.error = None
        return {"stage": "landing"}

    @app.get("/api/books")
    def list_books_route(
        q: str = "",
        page: int = 1,
        pageSize: int = 40,
        sortBy: str = "uploadDate",
        order: int = -1,
    ):
        return state.client.list_books(
            q=q,
            page=page,
            page_size=pageSize,
            sort_by=sortBy,
            order=order,
        )

    @app.post("/api/start/existing")
    async def start_existing(body: StartExistingRequest):
        if state.backfill_manager and (
            state.backfill_manager.active_book_id is not None
            or state.backfill_manager.auto_running
        ):
            raise HTTPException(
                status_code=409,
                detail="Backfill is currently running; pause backfill first",
            )
        state.manual_review_session_id = None
        try:
            workdir = _start_existing_book(body.bookId, state.client, state.work_root)
        except Exception as exc:
            state.stage = "error"
            state.error = str(exc)
            raise HTTPException(status_code=502, detail=str(exc))

        pages = workdir.all_pages()
        unfinished = [
            p for p in pages if p.status not in ("ocrd", "reviewed", "from_kitabim")
        ]
        if unfinished:
            pos, is_active = await state.queue_manager.enqueue(workdir.root.name)
            if is_active:
                state.workdir = workdir
                state.stage = "processing"
                state.error = None
            return {
                "stage": "processing" if is_active else "queued",
                "sessionId": workdir.root.name,
                "queuePosition": pos,
                "isProcessing": is_active,
            }
        else:
            state.workdir = workdir
            state.stage = "review"
            state.error = None
            return {"stage": "review"}

    @app.post("/api/start/upload")
    async def start_upload(file: UploadFile = File(...)):
        if state.backfill_manager and (
            state.backfill_manager.active_book_id is not None
            or state.backfill_manager.auto_running
        ):
            raise HTTPException(
                status_code=409,
                detail="Backfill is currently running; pause backfill first",
            )
        state.manual_review_session_id = None
        pdf_bytes = await file.read()
        try:
            workdir = await asyncio.to_thread(
                _create_upload_workdir, pdf_bytes, state.work_root, file.filename
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Not a valid PDF: {exc}")

        pos, is_active = await state.queue_manager.enqueue(workdir.root.name)
        if is_active:
            state.workdir = workdir
            state.stage = "processing"
            state.error = None
        return {
            "stage": "processing" if is_active else "queued",
            "sessionId": workdir.root.name,
            "queuePosition": pos,
            "isProcessing": is_active,
        }

    @app.get("/api/pages")
    def list_pages():
        if (
            state.workdir is None
            and state.backfill_manager
            and state.backfill_manager.active_book_id
        ):
            return state.backfill_manager.list_active_pages()
        _require_active_workdir(state)
        return list_pages_response(state.workdir)

    @app.get("/api/pages/{page_number}/image")
    def get_page_image(page_number: int):
        if (
            state.workdir is None
            and state.backfill_manager
            and state.backfill_manager.active_book_id
        ):
            return Response(
                content=state.backfill_manager.get_active_page_image_bytes(page_number),
                media_type="image/png",
                headers={
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                    "Expires": "0",
                },
            )
        _require_active_workdir(state)
        return Response(
            content=get_page_image_bytes(state.workdir, page_number),
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        _require_active_workdir(state)
        return await redo_pages_response(
            state.workdir,
            body.pageNumbers,
            concurrency=state.concurrency,
            engine=state.engine,
        )

    @app.post("/api/pages/{page_number}/update")
    def update_page(page_number: int, body: UpdatePageRequest):
        if (
            state.workdir is None
            and state.backfill_manager
            and state.backfill_manager.active_book_id
        ):
            return state.backfill_manager.update_active_page(page_number, body)
        _require_active_workdir(state)
        return update_page_response(state.workdir, page_number, body)

    @app.post("/api/push")
    def push():
        _require_active_workdir(state)
        if (
            state.queue_manager
            and state.queue_manager.active_session_id == state.workdir.root.name
        ):
            raise HTTPException(
                status_code=409,
                detail="Cannot push while book is actively processing in the queue",
            )
        return push_response(state.workdir, state.client)

    @app.get("/api/backfill/status")
    def get_backfill_status():
        return state.backfill_manager.get_status()

    @app.get("/api/backfill/candidates")
    def get_backfill_candidates_route(limit: int = 500):
        try:
            return state.backfill_manager.fetch_candidates_and_history(limit=limit)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=str(exc))

    @app.post("/api/backfill/start")
    async def start_backfill_auto():
        res = state.backfill_manager.start_auto()
        state.workdir = None
        state.manual_review_session_id = None
        state.stage = "processing"
        state.error = None
        return res

    @app.post("/api/backfill/pause")
    async def pause_backfill_auto():
        return state.backfill_manager.pause_auto()

    @app.post("/api/backfill/run/{book_id}")
    async def run_backfill_on_demand_route(
        book_id: str, body: Optional[BackfillOnDemandRequest] = None
    ):
        res = state.backfill_manager.start_on_demand(
            book_id,
            title=body.title if body else None,
            author=body.author if body else None,
            upload_date=body.uploadDate if body else None,
        )
        state.workdir = None
        state.manual_review_session_id = None
        state.stage = "processing"
        state.error = None
        return res

    @app.get("/api/backfill/pages/{page_number}/image")
    def get_backfill_page_image(page_number: int):
        return Response(
            content=state.backfill_manager.get_active_page_image_bytes(page_number),
            media_type="image/png",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.post("/api/backfill/pages/{page_number}/update")
    def update_backfill_page(page_number: int, body: UpdatePageRequest):
        return state.backfill_manager.update_active_page(page_number, body)

    return app


def _open_browser_when_ready(
    url: str, host: str = "127.0.0.1", port: int = 8765, timeout: float = 10.0
) -> None:
    def _poll_and_open():
        deadline = time.time() + timeout
        connected = False
        while time.time() < deadline:
            try:
                with socket.create_connection((host, port), timeout=0.2):
                    connected = True
                    break
            except (OSError, ConnectionRefusedError):
                time.sleep(0.1)
        if connected:
            time.sleep(0.15)
            webbrowser.open(url)

    threading.Thread(target=_poll_and_open, daemon=True).start()


def serve_app(
    client: KitabimClient,
    work_root: Path,
    port: int = 8765,
    open_browser: bool = True,
    engine: Optional[str] = None,
    concurrency: Optional[int] = None,
) -> None:
    app = create_landing_app(client, work_root, engine=engine, concurrency=concurrency)
    if open_browser:
        _open_browser_when_ready(
            f"http://127.0.0.1:{port}", host="127.0.0.1", port=port
        )
    uvicorn.run(app, host="127.0.0.1", port=port)
