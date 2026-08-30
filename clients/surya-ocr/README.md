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
