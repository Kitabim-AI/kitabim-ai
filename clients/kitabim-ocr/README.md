# Kitabim OCR Client

Standalone desktop tool: runs OCR locally on your own hardware (supporting both
standard Surya OCR and Apple Silicon MLX-optimized Savitr OCR — no Docker, full
GPU/CPU/Neural Engine access), lets you preview and redo pages before committing,
then pushes finished text to Kitabim over its public API. Kitabim's own OCR stage
(Gemini, in `services/worker`) is unaffected — this tool only ever talks to
Kitabim's HTTP API as an authenticated editor/admin user.

## Setup

    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt

### Apple Silicon Acceleration (Savitr OCR)

On Apple Silicon (M1/M2/M3/M4 Macs), you can use **Savitr**, an MLX-accelerated
Surya OCR engine (~3-4x faster inference using unified memory):

    pip install savitr

Because base Surya (`datalab-to/surya-ocr-2`) is published in PyTorch format, convert it once to 4-bit MLX format:

    python main.py setup-savitr

Or using `mlx_vlm` directly:

    python -m mlx_vlm convert --hf-path datalab-to/surya-ocr-2 --mlx-path ~/.cache/savitr/surya-mlx-4bit -q --q-bits 4

Then configure `KITABIM_OCR_ENGINE=savitr` in `.env` or pass `--engine savitr`.

## OCR Engine Selection

You can choose between two OCR engines:
- `surya` (default): Standard Surya OCR using PyTorch / MPS / CPU.
- `savitr`: Apple Silicon MLX-accelerated Surya OCR runtime.

Set the engine in `.env`:

    KITABIM_OCR_ENGINE=surya   # or savitr

Or pass it via the CLI:

    python main.py app --engine savitr

Optional custom Savitr model weights path:

    SAVITR_MODEL_PATH=models/surya-mlx-4bit

## Starting the app

Set the required variables, either in your shell:

    export KITABIM_BASE_URL=https://kitabim.ai/api    # Kitabim backend to talk to
    export KITABIM_WORK_DIR=~/kitabim-ocr-work        # where local OCR sessions are stored

or once, in a `.env` file next to `main.py` (copy `.env.example` to `.env`
and fill it in) so you don't have to re-export them every session — a
shell-exported value always wins if both are set. Neither variable is a
secret (the actual login token lives separately, in
`~/.config/kitabim-ocr-client/`), so `.env` is safe to use for this; it's
already gitignored.

    python main.py

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

    python main.py preview <workdir>                 # reopen a previous session directly
    python main.py push <workdir> --base-url https://kitabim.ai/api

See `docs/superpowers/specs/2026-08-30-surya-ocr-client-design.md` and
`docs/superpowers/specs/2026-08-30-surya-ocr-client-landing-page-design.md`
in the main kitabim-ai repo for the full design.
