# PaddleOCR Uyghur Accuracy Spike & Engine Integration Design

**Date**: 2026-10-03  
**Branch**: `feature/paddle-ocr-spike`  
**Status**: Draft / Under Review  

---

## 1. Problem Statement & Motivation
Kitabim currently uses **Surya OCR** (via standard PyTorch/MPS on CPU/GPU or **Savitr OCR** on Apple Silicon MLX) within the standalone [`clients/kitabim-ocr`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr) desktop client to transcribe scanned Uyghur books.

While Surya performs well on layout detection, certain issues persist with complex fonts, faint printing, small diacritics, and specific Uyghur ligatures. Baidu's **PaddleOCR** provides dedicated multilingual recognition models supporting Uyghur (`lang='ug'`). 

The goal of this spike is to:
1. Integrate PaddleOCR into `clients/kitabim-ocr` as an experimental third engine option alongside `surya` and `savitr`.
2. Allow seamless switching between engines directly in the local Kitabim OCR Client Web UI (`http://127.0.0.1:8765`).
3. Enable page-by-page re-running ("Redo Page") with either engine to allow direct, qualitative side-by-side inspection of Uyghur text accuracy, character shaping, diacritics, and line reading order.

---

## 2. Architecture & Engine Integration

### 2.1 Engine Abstraction
The standalone OCR client abstractly routes recognition calls through [`clients/kitabim-ocr/engine/recognize.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/recognize.py). We introduce `paddle` as a first-class supported engine alongside `surya` and `savitr`.

* **Configuration**:
  * Expand `SUPPORTED_OCR_ENGINES = ("surya", "savitr", "paddle")` in [`engine/config.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/config.py).
  * Update `OcrEngineName = Literal["surya", "savitr", "paddle"]`.
  * Add `is_paddle_available()` helper checking for runtime import of `paddle` and `paddleocr`.
  * Set default concurrency limit for PaddleOCR (`DEFAULT_PADDLE_CONCURRENCY = 2`) to ensure stable memory footprint on local machines.

* **Dependencies**:
  * Add to [`clients/kitabim-ocr/requirements.txt`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/requirements.txt):
    * `paddlepaddle>=3.0.0` (with macOS arm64 wheel support for Apple Silicon)
    * `paddleocr>=2.9.0`
    * `python-bidi>=0.4.2`

### 2.2 Dedicated Engine Adapter: `engine/paddle_engine.py`
We create [`clients/kitabim-ocr/engine/paddle_engine.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/paddle_engine.py), which encapsulates:
1. **`PaddleEnginePredictor`**:
   * Thread-safe singleton predictor.
   * Initializes `PaddleOCR(use_angle_cls=True, lang='ug', use_gpu=False)`.
   * Accepts `PIL.Image.Image`, converts to `np.ndarray` (RGB).
   * Runs inference via `ocr(img_array, cls=True)`.

2. **Detection Normalization to Surya Block Format**:
   Surya produces structured blocks (`label`, `html`, `confidence`, `bbox`, `polygon`, `reading_order`). PaddleOCR returns bounding polygons and recognized text tuples:
   ```python
   # [ [ [[x1, y1], [x2, y2], [x3, y3], [x4, y4]], (text, confidence) ], ... ]
   ```
   The adapter normalizes these into block objects matching Surya's interface:
   * **Bbox Calculation**: Bounding rectangle `[min_x, min_y, max_x, max_y]`.
   * **Reading Order (Top-to-Bottom, Right-to-Left)**:
     * In scanned Uyghur pages, text reads right-to-left within lines and top-to-bottom across the page.
     * Line clustering: Group bounding boxes into vertical line bands using y-coordinate overlap thresholds based on box heights.
     * Within each band, sort boxes from **right to left** (descending x-coordinate).
     * Sort bands from **top to bottom** (ascending y-coordinate).
   * **HTML Generation**: Each detected text box is wrapped in standard `<p dir="rtl">text</p>` or grouped into paragraphs.

3. **Uyghur RTL & Unicode Shaping Normalization**:
   * Inspect output character direction: Ensure strings are in Unicode logical order (RTL sequence) rather than reversed visual order.
   * If PaddleOCR returns inverted visual text, reorder using `python-bidi` / Unicode bidi reordering into standard logical Uyghur text.
   * Feed normalized blocks into [`engine/recognize.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/recognize.py)'s downstream pipeline, which applies bleed-through suppression, [`clean_uyghur_text()`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/text_cleanup.py), and isolated page-number filtering.

---

## 3. UI Engine Switcher & Interactive Redo

### 3.1 Backend State & Endpoints
In [`clients/kitabim-ocr/preview/app_server.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/preview/app_server.py):
* Add endpoint `POST /api/settings/engine` taking JSON `{"engine": "paddle" | "surya" | "savitr"}`.
  * Validates availability and updates `state.engine`.
  * Dynamically reconfigures concurrency via `resolve_concurrency(state.engine)`.
* In `POST /api/redo/<page_num>`:
  * Accepts an optional `engine` parameter in the payload (or uses current `state.engine`).
  * Re-runs OCR for that page with the selected engine.
  * Writes updated text and records `engine: "paddle"` in the page's metadata (`page.json`).
  * Returns updated page text and status for immediate UI update.

### 3.2 Frontend UI Updates
* **Header Engine Switcher**:
  * Replace the static `<span>__OCR_ENGINE_LABEL__</span>` in [`preview/app_server.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/preview/app_server.py) with an interactive `<select id="engineSelector">` containing:
    * `Surya OCR` (`surya`)
    * `Savitr OCR (MLX)` (`savitr` - enabled on Apple Silicon)
    * `PaddleOCR (Uyghur)` (`paddle`)
  * Changing the dropdown sends `POST /api/settings/engine` and triggers a toast confirming engine switch.
* **Redo Page with Engine**:
  * When viewing a page in the Review UI, clicking "Redo" will re-run recognition using the currently selected engine, allowing instant comparison between the previous output and the new engine output.

### 3.3 CLI Commands
* Update [`clients/kitabim-ocr/main.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/main.py):
  * Add `--engine paddle` support to the CLI arguments.
  * Add a helper subcommand `python main.py setup-paddle` to test the environment and download initial PaddleOCR Uyghur weights.

---

## 4. Error Handling & Edge Cases
* **Missing Dependencies**: If `paddle` or `paddleocr` is not installed and the user selects the engine, raise a clear error with exact install instructions: `pip install paddlepaddle paddleocr`.
* **Empty Detections**: If PaddleOCR returns no bounding boxes on blank, noisy, or illustration pages, gracefully yield an empty block list without crashing.
* **Memory & Concurrency Management**: PaddleOCR uses thread-local execution; concurrency will be limited to 2 workers to avoid high CPU or RAM consumption.
* **Non-Arabic Fallback**: If mixed Uyghur and Latin/Chinese text appears on book covers, maintain proper directionality without corrupting numbers or Latin tokens.

---

## 5. Testing & Verification Plan

### 5.1 Unit Tests
* `tests/engine/test_paddle_engine.py`:
  * Mock `PaddleOCR` instance to verify that bounding box sorting correctly groups horizontal lines and orders RTL boxes from right to left.
  * Test Unicode normalization and unshaped vs. shaped character handling.
  * Test handling of empty detection results and multi-line paragraphs.
* `tests/engine/test_config.py`:
  * Test `get_configured_engine()` accepting `paddle`.
  * Test `resolve_concurrency("paddle")`.
* `tests/preview/test_app_server.py`:
  * Test `POST /api/settings/engine` switching engine to `paddle`.
  * Test `POST /api/redo/<page_num>` using `paddle` engine.

### 5.2 Manual Qualitative Verification
1. Activate virtual environment in `clients/kitabim-ocr/.venv` and install `paddlepaddle` and `paddleocr`.
2. Run OCR on sample pages from `clients/kitabim-ocr/fixtures/test_book.pdf` using Surya:
   ```bash
   python main.py app --engine surya
   ```
3. Switch engine to `paddle` in the UI header and click **Redo** on representative pages:
   * Standard prose text
   * Poetry / verse text
   * Dense small font footnotes
4. Inspect the quality of Uyghur text:
   * Presence of diacritic dots (e.g. `ژ`, `چ`, `پ`, `ڭ`, `گ`).
   * Vowel ligatures (e.g. `ئۆ`, `ئۈ`, `ئا`).
   * Word splitting / spacing consistency.
   * Right-to-left line order coherence.
