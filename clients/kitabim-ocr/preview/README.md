# Kitabim OCR Preview & Web UI

## Overview
Web application and preview server providing a local browser-based GUI for managing OCR sessions, reviewing recognized pages, redacting or editing text, re-running OCR on low-confidence pages, and pushing completed documents to Kitabim.

## Interface
- `[app_server.py:AppState]`: Dataclass holding global session, client, and queue state for the landing web application.
- `[app_server.py:create_landing_app]`: Constructs the unified FastAPI landing and review web application.
- `[app_server.py:serve_app]`: Starts the Uvicorn web server and opens the browser to the application landing page.
- `[app_server.py:list_local_sessions]`: Discovers and enumerates existing OCR session directories and metadata.
- `[app_server.py:get_app_html]`: Returns HTML template populated with localized translation bundles.
- `[server.py:create_app]`: Constructs FastAPI application for reviewing and correcting a single session.
- `[server.py:serve]`: Starts the single-session review server on localhost.
- `[server.py:RedoRequest]`: Request payload schema for re-processing selected pages.
- `[server.py:UpdatePageRequest]`: Request payload schema for updating page text and TOC flags.
- `[server.py:list_pages_response]`: Serializes page list and review metadata.
- `[server.py:render_page_png]`: Renders PDF page to PNG and caches to disk.
- `[server.py:get_page_image_bytes]`: Returns page image PNG bytes from cache or on-demand rendering.
- `[server.py:update_page_response]`: Applies user edits to a page and persists changes.
- `[server.py:redo_pages_response]`: Executes async re-OCR on requested page numbers.
- `[server.py:push_response]`: Triggers API upload of the current session to Kitabim.

## Invariants
- `[app_server.py:create_landing_app]`: Background OCR tasks run sequentially through `[../engine/queue.py:BookQueueManager]` to avoid overloading hardware.
- `[server.py:create_app]`: All page updates and redo operations lock against `[../engine/workdir.py:OcrWorkDir.save_lock]`.

## Side Effects
- `[app_server.py:serve_app]`, `[server.py:serve]`: Binds TCP socket on `127.0.0.1:8765` and launches default web browser.
- `[server.py:render_page_png]`: Writes rendered PNG files under `pages/` in the book work directory.
- `[server.py:update_page_response]`: Overwrites `book.json` and `pages.json` metadata on disk.
- `[server.py:push_response]`: Transmits HTTP requests pushing book data to remote Kitabim API.

## Verification
- Run: `pytest clients/kitabim-ocr/tests`
