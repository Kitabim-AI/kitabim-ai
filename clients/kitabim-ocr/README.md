# Kitabim OCR Client

A standalone desktop tool for running high-accuracy OCR locally on your own hardware using **Chandra OCR** (`datalab-to/chandra-ocr-2`).

The client provides an interactive browser-based review and correction interface with side-by-side page comparison, Table of Contents (TOC) tagging, sequential batch queueing, and one-click synchronization with the Kitabim API.

> [!NOTE]
> This tool runs entirely on your host machine without Docker containerization to give the OCR engine direct, unconstrained access to Apple Silicon (Metal Performance Shaders / MPS), Nvidia GPUs (CUDA), or multi-core CPUs. Kitabim's server-side background OCR pipeline remains independent.

---

## Features

- **Chandra OCR Engine**: Powered by `datalab-to/chandra-ocr-2` for state-of-the-art layout parsing, HTML/Markdown structural extraction, and high-accuracy text recognition.
- **Dual Inference Backends**:
  - `hf` (default): Hugging Face Transformers with PyTorch MPS (Apple Silicon), CUDA, or CPU.
  - `vllm`: Fast vLLM inference engine for local vLLM server setups.
- **Interactive Review UI**:
  - Side-by-side original page image vs recognized text editor.
  - Real-time page status indicators (`pending`, `processing`, `ocrd`, `reviewed`, `failed`).
  - Table of Contents (`is_toc`) designation for book outline generation.
  - Per-page re-OCR action for manual retries or prompt tweaks.
  - Multi-language UI support: Uyghur (Arabic script), Uyghur Latin (ULY), English, and Chinese.
- **Sequential Background Queue**:
  - Automatically processes multi-book workloads sequentially without exhausting GPU or unified system memory.
  - Resilient local work directories (`book.json`, cached page renders) that survive application restarts.
- **Kitabim API Integration**:
  - Search and download books directly from your Kitabim library.
  - Push newly OCR'd books or individual page corrections back to Kitabim over its authenticated REST API.

---

## Hardware Requirements

- **Apple Silicon (macOS)**: M1 / M2 / M3 / M4 with 16GB+ unified memory recommended.
- **Linux / Windows with Nvidia GPU**: CUDA-compatible GPU with 12GB+ VRAM recommended.
- **CPU Only**: Multi-core x86_64 / ARM64 processor (slower inference, suitable for testing).

---

## Installation

1. Navigate to the client directory:
   ```bash
   cd clients/kitabim-ocr
   ```

2. Create and activate a Python virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

---

## Pre-downloading Model Weights (Optional)

By default, weights are downloaded automatically on first run. You can pre-download and verify the Chandra OCR model weights ahead of time:

```bash
# PyTorch / Hugging Face backend (default)
python main.py setup-chandra

# Or for vLLM backend:
python main.py setup-chandra --method vllm
```

---

## Configuration

Configuration is managed via environment variables or a local `.env` file in `clients/kitabim-ocr/`. Copy the example template to get started:

```bash
cp .env.example .env
```

### Environment Variables

| Variable | Default | Description |
| :--- | :--- | :--- |
| `KITABIM_BASE_URL` | `https://kitabim.ai/api` | Kitabim API endpoint to synchronize with. |
| `KITABIM_WORK_DIR` | `~/kitabim-ocr-work` | Path where local book sessions and image caches are saved. |
| `KITABIM_OCR_ENGINE` | `chandra` | Active OCR engine (`chandra`). |
| `KITABIM_CHANDRA_METHOD` | `hf` | Inference backend: `hf` (PyTorch Transformers) or `vllm`. |
| `KITABIM_CHANDRA_MODEL_CHECKPOINT` | `datalab-to/chandra-ocr-2` | Hugging Face model checkpoint repository name or local path. |
| `KITABIM_CHANDRA_PROMPT_TYPE` | `ocr_layout` | Prompt mode: `ocr_layout` (tables, layout blocks) or `ocr` (pure text). |
| `KITABIM_CHANDRA_PROMPT_GUIDANCE` | *(Uyghur script instructions)* | Language guidance injected into prompt (set to `none` to disable). |
| `KITABIM_CHANDRA_REPETITION_PENALTY` | `1.05` | Repetition penalty to prevent VLM token looping. |
| `KITABIM_OCR_CONCURRENCY` | `1` | Concurrent pages processed per book (clamped 1–4 to prevent OOM). |
| `KITABIM_OCR_PAGE_TIMEOUT` | `300.0` | Timeout in seconds per page (set to `0` to disable). |
| `KITABIM_OCR_MAX_RETRIES` | `2` | Number of automatic retries on transient page failures. |

---

## Starting the Application

Once your `.env` is configured, start the interactive web application:

```bash
python main.py
```

This starts the local FastAPI server at `http://127.0.0.1:8765` and automatically opens it in your default web browser.

### Using the Web UI

1. **Start New Book**: Upload a local PDF or search for an existing book in your Kitabim library.
2. **Monitor Progress**: Watch pages process through the sequential background queue.
3. **Review & Edit**: Compare the extracted text side-by-side with high-resolution page images, flag Table of Contents pages, or re-run OCR on specific pages.
4. **Push to Kitabim**: Click **Push to Kitabim** to synchronize the reviewed text and structure directly to the platform.

---

## Command-Line Usage

The CLI supports direct actions for automation and headless environments:

### 1. Launch Web Application
```bash
python main.py app [--engine chandra] [--concurrency 1]
```

### 2. Open an Existing Session in Preview UI
```bash
python main.py preview ~/kitabim-ocr-work/my-book-session/ --base-url https://kitabim.ai/api
```

### 3. Push a Completed Session Headlessly
```bash
python main.py push ~/kitabim-ocr-work/my-book-session/ --base-url https://kitabim.ai/api
```

### 4. Verify & Setup Chandra Model
```bash
python main.py setup-chandra [--method hf|vllm] [--model-checkpoint datalab-to/chandra-ocr-2]
```

---

## Development & Testing

Run the test suite using `pytest`:

```bash
# Run all tests
pytest tests/

# Run engine tests only
pytest tests/engine/

# Run web preview app tests
pytest tests/preview/
```
