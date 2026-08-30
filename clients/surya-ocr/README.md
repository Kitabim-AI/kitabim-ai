# Surya OCR Client

Standalone desktop tool: runs Surya OCR locally on your own hardware (no
Docker, full GPU/CPU access), lets you preview and redo pages before
committing, then pushes finished text to Kitabim over its public API.
Kitabim's own OCR stage (Gemini, in `services/worker`) is unaffected —
this tool only ever talks to Kitabim's HTTP API as an authenticated
editor/admin user.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

## Starting the app

    export KITABIM_BASE_URL=https://api.kitabim.ai   # Kitabim backend to talk to
    export KITABIM_WORK_DIR=~/surya-ocr-work          # where local OCR sessions are stored

    python cli.py app

This starts a local server on `http://127.0.0.1:8765` and opens it in
your default browser automatically. The landing page lets you search for
and pick an existing Kitabim book to correct, or upload a new local PDF
to OCR from scratch — progress and the review UI (redo pages, push to
Kitabim) both happen in the same browser tab, so no further commands are
needed once it's running. `KITABIM_WORK_DIR` is where each book's local
OCR session (images, extracted text, review state) is stored between
runs, so interrupted sessions resume instead of restarting.

The first action that needs Kitabim access (a book search or a push)
triggers a one-time browser-based login — no separate login command or
API key required. Leave the app running in its terminal; press `Ctrl+C`
to stop it.

## Other commands

    python cli.py preview <workdir>                 # reopen a previous session directly
    python cli.py push <workdir> --base-url https://api.kitabim.ai

See `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` and
`docs/superpowers/specs/2026-08-30-surya-ocr-client-landing-page-design.md`
in the main kitabim-ai repo for the full design.
