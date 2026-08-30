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

    python cli.py ocr /path/to/book.pdf          # OCR + open local preview
    python cli.py preview <workdir>               # reopen a previous session
    python cli.py push <workdir> --base-url https://api.kitabim.ai
    python cli.py correct <book_id> --base-url https://api.kitabim.ai

See `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` in the
main kitabim-ai repo for the full design.
