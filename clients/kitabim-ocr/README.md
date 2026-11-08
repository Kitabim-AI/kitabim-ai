# Kitabim OCR Client

## Overview
Standalone desktop client for running OCR locally on user hardware (supporting Surya OCR — no Docker, full GPU/CPU access). It provides a browser-based user interface to preview recognized pages, correct text, re-run OCR on low-confidence pages, and push completed documents to Kitabim over its public HTTP API.

Kitabim's server-side OCR pipeline in `services/worker` is completely unaffected; this client operates strictly as an authenticated client against Kitabim's public REST endpoints.

### Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configuration & Startup
Set the required environment variables in shell or `.env`:
```bash
export KITABIM_BASE_URL=https://kitabim.ai/api    # Kitabim backend endpoint
export KITABIM_WORK_DIR=~/kitabim-ocr-work        # Directory where local OCR sessions are stored
export KITABIM_OCR_CONCURRENCY=4                  # Parallel pages (default: 4, max: 4 for Surya)
```

Run the application:
```bash
python main.py
```
This starts a local server on `http://127.0.0.1:8765` and launches the default browser automatically.

### CLI Commands
- `python main.py app [--concurrency N]`: Open the interactive book-picker and OCR queue landing page.
- `python main.py preview <workdir>`: Reopen the review UI for an existing session directory.
- `python main.py push <workdir> --base-url <url>`: Push OCR results from a work directory to Kitabim headlessly.

## Interface
- `[main.py:cmd_app]`: Starts the unified web application and queue manager.
- `[main.py:cmd_preview]`: Reopens the preview server for a local work directory.
- `[main.py:cmd_push]`: Headlessly pushes a completed session to Kitabim API.
- `[main.py:build_parser]`: Configures CLI arguments and flags (`--engine`, `--concurrency`).
- `[main.py:main]`: Top-level CLI entry point.
- Subdirectories:
  - [engine](./engine/README.md): Core OCR pipeline, layout analysis, dictionary validation, queue manager, and workspace persistence.
  - [kitabim_client](./kitabim_client/README.md): Kitabim HTTP API client and OAuth2 authentication handlers.
  - [locales](./locales/README.md): Translation bundles and internationalization helpers.
  - [preview](./preview/README.md): FastAPI web application and preview servers for book review and page corrections.

## Invariants
- `[main.py:cmd_app]`: Requires `KITABIM_BASE_URL` and `KITABIM_WORK_DIR` environment variables or `.env` configuration.
- `[main.py:build_parser]`: Surya engine concurrency is clamped to a maximum of 4 parallel pages for stability.
- Interrupted OCR sessions resume from disk using local metadata without re-processing completed pages.

## Side Effects
- `[main.py:cmd_app]`: Binds a local HTTP server on `http://127.0.0.1:8765`, launches the default browser, and spawns background OCR worker tasks.
- `[main.py:cmd_push]`: Sends authenticated multipart HTTP POST requests to Kitabim API.
- Local disk writes: Stores cached models, rendered PNG page images, and session metadata (`book.json`, `pages.json`) in `KITABIM_WORK_DIR`.

## Verification
- Run: `pytest`
