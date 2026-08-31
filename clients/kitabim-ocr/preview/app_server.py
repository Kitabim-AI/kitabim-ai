from __future__ import annotations

import asyncio
import shutil
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import fitz
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel

from engine.recognize import (
    LowConfidenceOcrError,
    get_recognition_predictor,
    ocr_page,
)
from engine.workdir import OcrWorkDir
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
      overflow-x: auto;
      border-radius: 16px;
      border: 1px solid rgba(3, 105, 161, 0.12);
      background: white;
    }
    table.books-table {
      width: 100%;
      border-collapse: collapse;
      text-align: right;
    }
    table.books-table thead {
      background: rgba(3, 105, 161, 0.05);
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
    .matrix-tile.failed { background: #fee2e2; color: #b91c1c; border-color: #fca5a5; }
    .matrix-tile.clickable {
      cursor: pointer;
    }
    .matrix-tile.clickable:hover {
      transform: translateY(-2px);
      box-shadow: 0 4px 10px rgba(0, 0, 0, 0.08);
      border-color: #10b981;
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
        <div class="step-item" id="step2Indicator">2. OCR نازارەت</div>
        <div>&larr;</div>
        <div class="step-item" id="step3Indicator">3. تەكشۈرۈش &amp; تەھرىرلەش</div>
      </div>

      <div class="header-badges">
        <div class="status-pill">
          <span class="status-dot active"></span>
          <span>Surya OCR</span>
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
                <th>كىتاب / ھۆججەت</th>
                <th>بەت سانى ۋە تەرەققىياتى</th>
                <th>ھالىتى</th>
                <th>ئۆزگەرتىلگەن ۋاقتى</th>
                <th style="text-align: left;">مەشغۇلات</th>
              </tr>
            </thead>
            <tbody id="sessionsTableBody">
              <tr>
                <td colspan="5" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                  <div style="display: inline-flex; align-items: center; gap: 0.5rem; justify-content: center;">
                    <span style="width: 18px; height: 18px; border: 2px solid rgba(3, 105, 161, 0.2); border-top-color: var(--primary); border-radius: 50%; display: inline-block; animation: spin 0.8s linear infinite;"></span>
                    <span>يەرلىك خىزمەتلەر تەكشۈرۈلۈۋاتىدۇ...</span>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- TAB 1: KITABIM CLOUD BOOKS TABLE -->
      <div id="tabLibraryContent" class="glass-panel" style="padding: 1.5rem; display: none;">
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
          <div class="count-pill" id="bookCountBadge">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
            <span id="totalBooksCount">0</span> كىتاب تېپىلدى
          </div>
        </div>

        <div class="table-container">
          <table class="books-table">
            <thead>
              <tr>
                <th>كىتاب نامى</th>
                <th>توم / بەت سانى</th>
                <th>ئاپتور</th>
                <th>OCR ھالىتى</th>
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
        </div>
        <div class="toolbar-group" style="font-size: 0.88rem; color: var(--slate-600); font-weight: 500;">
          <span class="status-dot active"></span>
          <span id="processingBackgroundBadge">ئارقا سەھنىدە ئىشلەۋاتىدۇ</span>
        </div>
      </div>

      <div class="glass-panel monitor-card">
        <div class="progress-header">
          <div>
            <h2 style="font-size: 1.4rem; font-weight: 800; color: var(--slate-900); margin-bottom: 0.25rem;">
              ھۆججەت بىر تەرەپ قىلىنىۋاتىدۇ...
            </h2>
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

    function showSection(name) {
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
    }

    let bookSearchQuery = '';
    let bookCurrentPage = 1;
    const BOOK_PAGE_SIZE = 40;
    let bookIsLoading = false;
    let bookHasMore = true;
    let totalBooksCount = 0;
    let booksObserver = null;

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
        const url = `/api/books?q=${encodeURIComponent(bookSearchQuery)}&page=${pageToFetch}&pageSize=${BOOK_PAGE_SIZE}&sortBy=uploadDate&order=-1`;
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

        tr.innerHTML = `
          <td>
            <div class="book-title-cell">
              <div class="book-avatar">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1-2.5-2.5Z"/></svg>
              </div>
              <div>
                <div class="book-main-title">${escapeHtml(b.title || '—')}</div>
                <div class="book-sub-info">${b.totalPages || 0} ${t('library.pages_suffix')}</div>
              </div>
            </div>
          </td>
          <td>${b.volume !== null && b.volume !== undefined ? b.volume + '-' + t('library.vol_prefix') : '—'}</td>
          <td>${escapeHtml(b.author || t('library.author_unknown'))}</td>
          <td>
            <span class="milestone-badge ${milestoneClass}">${milestoneText}</span>
          </td>
          <td style="text-align: left;">
            <button class="btn btn-primary btn-sm" id="btn-start-${b.id}">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
              ${t('library.btn_download_correct')}
            </button>
          </td>
        `;
        tr.querySelector(`#btn-start-${b.id}`).onclick = () => startExisting(b.id);
        tbody.appendChild(tr);
      }
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
      startBtn.innerHTML = '<span style="display:inline-block; animation: spin 1s infinite linear;">⚙️</span> باشلىنىۋاتىدۇ...';

      try {
        const res = await fetch('/api/start/upload', {method: 'POST', body: formData});
        if (!res.ok) {
          showLandingError(await res.text());
          startBtn.disabled = false;
          startBtn.textContent = 'OCR نى باشلاش';
          return;
        }
        showSection('processing');
        pollProgress();
      } catch (err) {
        showLandingError(err.message);
        startBtn.disabled = false;
        startBtn.textContent = t('upload.btn_start');
      }
    });

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

    async function pollProgress() {
      if (!sections.processing.classList.contains('active')) {
        return;
      }
      try {
        const res = await fetch('/api/pages');
        if (res.ok) {
          const pages = await res.json();
          const total = pages.length;
          const done = pages.filter(p => p.status === 'ocrd' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed').length;
          document.getElementById('progressLabel').textContent = t('sessions.pages_completed_stat', {done: done, total: total});
          document.getElementById('progressFill').style.width = total ? ((done / total) * 100) + '%' : '0%';
          renderPageMatrix(pages);
        }

        const stateRes = await fetch('/api/state');
        const state = await stateRes.json();
        if (!sections.processing.classList.contains('active')) {
          return;
        }
        if (state.stage === 'review') {
          showSection('review');
          loadPages();
          return;
        }
        if (state.stage === 'error') {
          showSection('landing');
          showLandingError(state.error || t('errors.processing_failed'));
          return;
        }
        setTimeout(pollProgress, 1000);
      } catch (err) {
        if (sections.processing.classList.contains('active')) {
          setTimeout(pollProgress, 2000);
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
      } else {
        badge.className = 'milestone-badge milestone-ready';
        badge.textContent = page.status === 'from_kitabim' ? t('review.status_from_kitabim_badge') : t('review.status_ocrd_badge');
      }
      document.getElementById('previewModalImage').src = `/api/pages/${page.pageNumber}/image?v=${currentSessionVersion}`;
      
      const textArea = document.getElementById('previewModalText');
      if (document.activeElement !== textArea) {
        textArea.value = page.text || (page.error ? `${t('errors.generic', {error: page.error})}` : '');
      }

      const completedPages = currentProcessingPages.filter(p => p.status === 'ocrd' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed');
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
      try {
        await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: [pageNum]}),
        });
        currentSessionVersion = Date.now();
        const res = await fetch('/api/pages');
        if (res.ok) {
          const pages = await res.json();
          currentProcessingPages = pages;
          renderPageMatrix(pages);
          const page = pages.find(p => p.pageNumber === pageNum);
          if (page) {
            updateLivePreviewContent(page);
          }
        }
      } catch (e) {
        console.error('Failed to redo page from preview', pageNum, e);
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
      const completedPages = currentProcessingPages.filter(p => p.status === 'ocrd' || p.status === 'from_kitabim' || p.status === 'reviewed' || p.status === 'failed');
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
              <button class="btn btn-secondary btn-sm" onclick="redoSinglePage(${p.pageNumber})">
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
      currentSessionVersion = Date.now();
      await fetch('/api/pages/redo', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pageNumbers: [pageNum]}),
      });
      loadPages();
    }

    async function redoSelected() {
      const pages = selectedPageNumbers();
      if (!pages.length) return;
      currentSessionVersion = Date.now();
      const btn = document.getElementById('redoSelectedBtn');
      btn.disabled = true;
      btn.textContent = t('review.redo_in_progress');
      try {
        await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        await loadPages();
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
      try {
        await fetch('/api/pages/redo', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({pageNumbers: pages}),
        });
        await loadPages();
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

        if (!sessions || sessions.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="5" style="text-align: center; padding: 3rem; color: var(--slate-400);">
                ${t('sessions.empty')}
              </td>
            </tr>
          `;
          return sessions;
        }

        tbody.innerHTML = sessions.map(s => {
          const pct = s.totalPages > 0 ? Math.round((s.completedPages / s.totalPages) * 100) : 0;
          const statusBadge = s.isComplete 
            ? `<span class="tag-badge success">${t('sessions.status_completed', {count: s.completedPages})}</span>` 
            : `<span class="tag-badge pending">${t('sessions.status_processing', {done: s.completedPages, total: s.totalPages, pct: pct})}</span>`;
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
              <td style="font-size: 0.82rem; color: var(--slate-500);">${escapeHtml(dateStr)}</td>
              <td>
                <div style="display: flex; align-items: center; gap: 0.4rem;">
                  ${s.isComplete ? `
                  <button class="btn btn-primary" onclick="resumeSession('${escapeHtml(s.id)}')" style="padding: 0.35rem 0.85rem; font-size: 0.85rem;">
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
        tbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding: 2rem; color: var(--accent-rose);">${t('errors.generic', {error: escapeHtml(err.message)})}</td></tr>`;
      }
    }

    async function resumeSession(sessionId) {
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/resume`, {method: 'POST'});
        if (!res.ok) {
          const err = await res.json();
          throw new Error(err.detail || 'Resume failed');
        }
        const body = await res.json();
        if (body.stage === 'processing') {
          showSection('processing');
          pollProgress();
        } else if (body.stage === 'review') {
          showSection('review');
          loadPages();
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

    function applyStaticI18n() {
      const tabSessionsLabel = document.getElementById('tabSessionsLabel');
      if (tabSessionsLabel) tabSessionsLabel.textContent = t('tabs.sessions');
      const tabLibraryLabel = document.getElementById('tabLibraryLabel');
      if (tabLibraryLabel) tabLibraryLabel.textContent = t('tabs.library');
      const tabUploadLabel = document.getElementById('tabUploadLabel');
      if (tabUploadLabel) tabUploadLabel.textContent = t('tabs.upload');
      const processingBackLabel = document.getElementById('processingBackLabel');
      if (processingBackLabel) processingBackLabel.textContent = t('processing.btn_back_home');
      const processingBackgroundBadge = document.getElementById('processingBackgroundBadge');
      if (processingBackgroundBadge) processingBackgroundBadge.textContent = t('processing.running_in_background');
    }

    async function init() {
      applyStaticI18n();
      const res = await fetch('/api/state');
      const state = await res.json();
      if (state.stage === 'processing') {
        showSection('processing');
        pollProgress();
      } else if (state.stage === 'review') {
        showSection('review');
        loadPages();
      } else {
        showSection('landing');
        const sessions = await loadLocalSessions();
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


def get_app_html(lang: str = "ug") -> str:
    i18n_json = get_translations_json(lang)
    return _APP_HTML.replace("__I18N_JSON__", i18n_json)


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
        workdir.image_path(page_number).write_bytes(render_page_png(doc, page_number))
        workdir.set_page(
            page_number, text="", is_toc=False, confidence=0.0, status="pending"
        )
    workdir.save()
    return workdir


DEFAULT_OCR_CONCURRENCY = 4


async def _run_ocr_background(
    workdir: OcrWorkDir, state: "AppState", concurrency: int = DEFAULT_OCR_CONCURRENCY
) -> None:
    try:
        doc = fitz.open(workdir.source_pdf)
        predictor = await get_recognition_predictor()
        sem = asyncio.Semaphore(max(1, concurrency))
        save_lock = asyncio.Lock()

        async def process_one(page_number: int):
            current_page = workdir._pages.get(page_number)
            if current_page and current_page.status in (
                "ocrd",
                "reviewed",
                "from_kitabim",
            ):
                return

            async with sem:
                async with save_lock:
                    workdir.set_page(
                        page_number,
                        text="",
                        is_toc=False,
                        confidence=0.0,
                        status="processing",
                    )
                    workdir.save()

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
                    async with save_lock:
                        workdir.set_page(
                            page_number,
                            text="",
                            is_toc=False,
                            confidence=0.0,
                            status="failed",
                            error=str(exc),
                        )
                        workdir.save()
                except Exception as exc:
                    async with save_lock:
                        workdir.set_page(
                            page_number,
                            text="",
                            is_toc=False,
                            confidence=0.0,
                            status="failed",
                            error=f"Unexpected OCR error: {exc}",
                        )
                        workdir.save()

        tasks = [process_one(p) for p in range(1, workdir.total_pages + 1)]
        await asyncio.gather(*tasks)
        state.stage = "review"
    except Exception as exc:
        state.stage = "error"
        state.error = str(exc)


def list_local_sessions(work_root: Path) -> list[dict]:
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
                    "isComplete": (done + failed >= total) and total > 0,
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
    def index(lang: str = "ug"):
        return get_app_html(lang)

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
        return {
            "stage": state.stage,
            "error": state.error,
            "sessionId": state.workdir.root.name if state.workdir else None,
        }

    @app.get("/api/sessions")
    def get_sessions():
        return list_local_sessions(state.work_root)

    @app.post("/api/sessions/{session_id}/resume")
    async def resume_session(session_id: str):
        if state.workdir and state.workdir.root.name == session_id:
            return {"stage": state.stage}

        if state.stage == "processing":
            raise HTTPException(
                status_code=409, detail="A book is currently processing; please wait"
            )

        session_dir = state.work_root / session_id
        if not session_dir.is_dir() or not (session_dir / "book.json").exists():
            raise HTTPException(status_code=404, detail="Session not found")
        try:
            workdir = OcrWorkDir.load(session_dir)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"Failed to load session: {exc}"
            )

        state.workdir = workdir
        state.error = None

        pages = workdir.all_pages()
        unfinished = [
            p for p in pages if p.status not in ("ocrd", "reviewed", "from_kitabim")
        ]
        if unfinished:
            state.stage = "processing"
            _start_background_task(_run_ocr_background(workdir, state))
        else:
            state.stage = "review"

        return {"stage": state.stage}

    @app.delete("/api/sessions/{session_id}")
    def delete_session(session_id: str):
        if (
            state.workdir
            and state.workdir.root.name == session_id
            and state.stage == "processing"
        ):
            raise HTTPException(
                status_code=409, detail="Cannot delete active processing session"
            )
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

    @app.post("/api/reset")
    def reset():
        if state.stage == "processing":
            raise HTTPException(status_code=409, detail="Cannot reset while processing")
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
                _create_upload_workdir, pdf_bytes, state.work_root, file.filename
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
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @app.post("/api/pages/redo")
    async def redo_pages(body: RedoRequest):
        _require_active_workdir(state)
        return await redo_pages_response(state.workdir, body.pageNumbers)

    @app.post("/api/pages/{page_number}/update")
    def update_page(page_number: int, body: UpdatePageRequest):
        _require_active_workdir(state)
        return update_page_response(state.workdir, page_number, body)

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
