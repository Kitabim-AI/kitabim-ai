# PaddleOCR (PP-Structure) Integration Design

**Date:** 2026-10-19  
**Branch:** `feature/paddleocr-poc`  
**Status:** Approved  
**Author:** Antigravity / Kitabim Team  

---

## 1. Objective

Replace Surya OCR with **PaddleOCR (PP-Structure)** as the primary, default OCR engine for the standalone `kitabim-ocr` desktop client while retaining Surya OCR as a configurable secondary fallback engine.

The document processing pipeline must support Uyghur language recognition (`lang='ug'`), document layout structure analysis (headings, body paragraphs, tables, headers, footers), confidence scoring, and seamless export into Kitabim's markdown format.

---

## 2. Scope & Constraints

- **Scope:** Confined to `clients/kitabim-ocr/` (engine configuration, predictor loading, page recognition, text formatting, CLI interface, locales, tests, and documentation).
- **Backend Compatibility:** The backend API and database schemas remain unaffected. The book ingestion source identifier sent by the client remains compatible.
- **Hardware & Environment:** Must execute natively on Apple Silicon (macOS `arm64`) as well as Linux/Windows CPUs/GPUs.
- **Engine Coexistence:** 
  - `paddleocr` is the default engine (`DEFAULT_OCR_ENGINE = "paddleocr"`).
  - `surya` remains supported via `--engine surya` or `KITABIM_OCR_ENGINE=surya`.

---

## 3. Architecture & Components

### 3.1. Engine Configuration (`engine/config.py`)

- **Engine Constants:**
  ```python
  DEFAULT_OCR_ENGINE = "paddleocr"
  SUPPORTED_OCR_ENGINES = ("paddleocr", "surya")
  OcrEngineName = Literal["paddleocr", "surya"]
  ```
- **Concurrency & Resource Limits:**
  - `DEFAULT_OCR_CONCURRENCY = 4`
  - Max concurrency for Surya clamped to `MAX_SURYA_CONCURRENCY = 4`.
  - PaddleOCR concurrency is configurable via `KITABIM_OCR_CONCURRENCY` / `OCR_CONCURRENCY` and `--concurrency`.

### 3.2. Predictor Initialization (`engine/recognize.py`)

- Maintain cached singletons for both engines (`_paddle_predictor`, `_surya_predictor`).
- Lazily instantiate `PPStructure` under an async lock:
  ```python
  from paddleocr import PPStructure

  _paddle_predictor = PPStructure(
      show_log=False,
      image_orientation=True,
      lang="ug",
      layout=True,
      table=True,
      ocr=True,
      use_gpu=False,
  )
  ```
- Model initialization is offloaded to the thread pool executor to prevent blocking the async event loop during weights loading or downloading.

### 3.3. PP-Structure Layout & Result Processing

PP-Structure yields a list of detected regions formatted as dictionaries:
`{'type': '<category>', 'bbox': [x1, y1, x2, y2], 'res': <content>}`

#### Region Handling Rules:
1. **`Header`**: Dropped (running page/chapter headers).
2. **`Footer`**: Inspected for isolated page numbers. If isolated digits, dropped; if containing meaningful text (signatures, notes), retained.
3. **`Title`**: Formatted as Markdown headings (`# <title text>`).
4. **`Table`**: 
   - When HTML structure is available in `res['html']`, converted to Markdown table syntax using `_html_rows_to_markdown()`.
   - Preserves table boundaries and columnar relationships.
5. **`Text` / `List`**:
   - Lines inside `res` are sorted in vertical reading order.
   - Text lines joined as paragraphs.
   - Single-line verse structures in poetic stanzas preserved.
6. **`Figure`**: Ignored (non-textual graphical content).
7. **Marginalia**: `_is_vertical_marginalia_block()` applied to eliminate vertical marginal text along outer page margins.

#### Confidence Calculation:
- Each recognized text line in PP-Structure provides a recognition confidence score in `[0.0, 1.0]`.
- The page's `mean_confidence` is computed as the arithmetic mean of all line confidences.
- Evaluated against `min_confidence` (default `0.3`) triggering retry if sub-threshold.

### 3.4. Shared Pre- and Post-Processing Pipeline

The unified `ocr_page()` orchestrator applies consistent processing regardless of chosen engine:
1. **Rendering:** Adaptive zoom scaling (`get_adaptive_page_zoom`) with retry increments.
2. **Pre-processing:**
   - Bleed-through / show-through suppression (`suppress_bleed_through`).
   - Unsharp mask dot and contrast enhancement (`enhance_dots_and_contrast`).
3. **Post-processing:**
   - Uyghur text normalization, character cleanup, and punctuation spacing (`clean_uyghur_text`).
   - Repetition loop and hallucination detection (`is_degenerate_ocr_output`).

---

## 4. Dependencies

In `clients/kitabim-ocr/requirements.txt`:
- Add `paddlepaddle`
- Add `paddleocr>=2.6.0`
- Retain `surya-ocr==0.22.1`

---

## 5. Verification & Testing Plan

1. **Config Tests (`tests/engine/test_config.py`)**:
   - Verify `get_configured_engine()` defaults to `"paddleocr"`.
   - Verify supported engines validate `"paddleocr"` and `"surya"`.
   - Verify invalid engine names raise `ValueError`.

2. **Predictor & Recognition Tests (`tests/engine/test_recognize.py`)**:
   - Mock PP-Structure outputs containing `Title`, `Text`, `Table`, `Header`, and `Footer`.
   - Test markdown heading conversion for `Title`.
   - Test markdown table generation for `Table`.
   - Test `Header` discarding and `Footer` page number filtering.
   - Verify confidence score computation.
   - Verify fallback to Surya when `engine="surya"`.

3. **CLI & Server Tests (`tests/test_main.py`, `tests/preview/test_app_server.py`)**:
   - Verify CLI arguments accept `--engine paddleocr` and `--engine surya`.
