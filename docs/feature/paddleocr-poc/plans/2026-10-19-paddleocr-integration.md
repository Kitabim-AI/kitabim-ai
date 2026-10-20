# PaddleOCR (PP-Structure) Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate PaddleOCR (PP-Structure) with Uyghur language model (`lang='ug'`) as the default OCR engine for `clients/kitabim-ocr`, while retaining Surya OCR as a configurable fallback engine.

**Architecture:** Abstract the OCR recognition pipeline in `clients/kitabim-ocr/engine/recognize.py` using an engine dispatcher and adapter pattern. `_process_page_paddleocr_sync` handles PP-Structure layout and line results (headings, body text, tables, headers, footers), calculates line-averaged confidence scores, and outputs structured Markdown. Shared pre-processing (bleed-through suppression, dot enhancement) and post-processing (Uyghur spell correction rules, runaway repetition filters) remain unified.

**Tech Stack:** Python 3.10+, PaddlePaddle, PaddleOCR >= 2.6.0 (PP-Structure), PyMuPDF (fitz), Pillow, BeautifulSoup4, pytest, pytest-asyncio.

## Global Constraints

- Scope is strictly confined to `clients/kitabim-ocr/` and docs in `docs/feature/paddleocr-poc/`.
- Default OCR engine is `paddleocr`. Secondary supported engine is `surya`.
- Pre-processing (`suppress_bleed_through`, `enhance_dots_and_contrast`) and post-processing (`clean_uyghur_text`, `is_degenerate_ocr_output`) must remain unified across both engines.
- All code and tests must run with the local virtual environment `./venv/bin/pytest`.
- Maintain full backward compatibility for existing Surya configurations.

---

### Task 1: Update Dependencies (`requirements.txt`)

**Files:**
- Modify: `clients/kitabim-ocr/requirements.txt`

**Interfaces:**
- Produces: Package dependencies including `paddlepaddle` and `paddleocr>=2.6.0` alongside `surya-ocr==0.22.1`.

- [ ] **Step 1: Update requirements.txt with PaddleOCR packages**

Update `clients/kitabim-ocr/requirements.txt` to include `paddlepaddle` and `paddleocr`:

```text
paddlepaddle
paddleocr>=2.6.0
surya-ocr==0.22.1
pymupdf
pillow
beautifulsoup4
python-dotenv
fastapi
python-multipart
uvicorn
httpx
pytest
pytest-asyncio
```

- [ ] **Step 2: Verify requirements.txt syntax and content**

Run: `grep -E "paddleocr|paddlepaddle|surya-ocr" clients/kitabim-ocr/requirements.txt`  
Expected output:
```text
paddlepaddle
paddleocr>=2.6.0
surya-ocr==0.22.1
```

- [ ] **Step 3: Commit dependency changes**

```bash
git add clients/kitabim-ocr/requirements.txt
git commit -m "deps(kitabim-ocr): add paddlepaddle and paddleocr to requirements.txt"
```

---

### Task 2: Update Engine Configuration (`engine/config.py`)

**Files:**
- Modify: `clients/kitabim-ocr/engine/config.py`
- Modify: `clients/kitabim-ocr/tests/engine/test_config.py`

**Interfaces:**
- Consumes: None
- Produces:
  - `DEFAULT_OCR_ENGINE = "paddleocr"`
  - `SUPPORTED_OCR_ENGINES = ("paddleocr", "surya")`
  - `OcrEngineName = Literal["paddleocr", "surya"]`
  - `get_configured_engine(default="paddleocr") -> str`
  - `resolve_concurrency(engine: str | None, requested: int | None = None) -> int` (clamping max concurrency to 4 when `engine == "surya"`)

- [ ] **Step 1: Write failing tests for PaddleOCR engine configuration**

In `clients/kitabim-ocr/tests/engine/test_config.py`, update existing tests that expect `"surya"` as default to expect `"paddleocr"`, and add test cases for `"paddleocr"` and `"surya"` coexistence:

```python
def test_default_ocr_engine_is_paddleocr():
    from engine.config import DEFAULT_OCR_ENGINE, SUPPORTED_OCR_ENGINES, get_configured_engine
    assert DEFAULT_OCR_ENGINE == "paddleocr"
    assert "paddleocr" in SUPPORTED_OCR_ENGINES
    assert "surya" in SUPPORTED_OCR_ENGINES
    assert get_configured_engine() == "paddleocr"

def test_get_configured_engine_surya_override(monkeypatch):
    from engine.config import get_configured_engine
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "surya")
    assert get_configured_engine() == "surya"

def test_resolve_concurrency_for_paddleocr_and_surya():
    from engine.config import resolve_concurrency, MAX_SURYA_CONCURRENCY
    # Surya is clamped to MAX_SURYA_CONCURRENCY (4)
    assert resolve_concurrency("surya", requested=8) == MAX_SURYA_CONCURRENCY
    # PaddleOCR respects requested concurrency without Surya clamping
    assert resolve_concurrency("paddleocr", requested=8) == 8
```

- [ ] **Step 2: Run tests to verify failure**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/engine/test_config.py -k "test_default_ocr_engine"`  
Expected: FAIL (assertion error because `DEFAULT_OCR_ENGINE` is currently `"surya"`)

- [ ] **Step 3: Update `engine/config.py`**

Modify `clients/kitabim-ocr/engine/config.py`:
```python
DEFAULT_OCR_ENGINE = "paddleocr"
SUPPORTED_OCR_ENGINES = ("paddleocr", "surya")
OcrEngineName = Literal["paddleocr", "surya"]
DEFAULT_OCR_CONCURRENCY = 4
MAX_SURYA_CONCURRENCY = 4
```

Update `get_configured_engine`:
```python
def get_configured_engine(default: str = DEFAULT_OCR_ENGINE) -> str:
    """Read configured OCR engine name from environment variables.

    Checks KITABIM_OCR_ENGINE first, then OCR_ENGINE.
    Returns normalized lowercase engine name ('paddleocr' or 'surya').
    """
    engine = (
        (
            os.environ.get("KITABIM_OCR_ENGINE")
            or os.environ.get("OCR_ENGINE")
            or default
        )
        .strip()
        .lower()
    )

    if engine not in SUPPORTED_OCR_ENGINES:
        raise ValueError(
            f"Unsupported OCR engine '{engine}'. Supported engines: {', '.join(SUPPORTED_OCR_ENGINES)}"
        )
    return engine
```

Update `resolve_concurrency`:
```python
def resolve_concurrency(engine: str | None, requested: int | None = None) -> int:
    resolved_engine = (engine or get_configured_engine()).strip().lower()
    max_limit = MAX_SURYA_CONCURRENCY if resolved_engine == "surya" else None
    if requested is None:
        return get_configured_concurrency(max_limit=max_limit)
    val = max(1, requested)
    if max_limit is not None:
        val = min(val, max_limit)
    return val
```

Update existing tests in `clients/kitabim-ocr/tests/engine/test_config.py` that checked for `DEFAULT_OCR_ENGINE == "surya"`.

- [ ] **Step 4: Run config tests to verify they pass**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/engine/test_config.py`  
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit config changes**

```bash
git add clients/kitabim-ocr/engine/config.py clients/kitabim-ocr/tests/engine/test_config.py
git commit -m "feat(kitabim-ocr): configure paddleocr as default engine with surya fallback"
```

---

### Task 3: Implement PP-Structure Recognition Adapter & Dispatcher (`engine/recognize.py`)

**Files:**
- Modify: `clients/kitabim-ocr/engine/recognize.py`
- Modify: `clients/kitabim-ocr/tests/engine/test_recognize.py`

**Interfaces:**
- Consumes:
  - `get_configured_engine` from `engine.config`
  - `clean_uyghur_text`, `is_degenerate_ocr_output`, `is_isolated_page_number` from `engine.text_cleanup`
- Produces:
  - `get_recognition_predictor(engine: str | None = None) -> Any`: Returns `PPStructure` (for paddleocr) or `RecognitionPredictor` (for surya)
  - `_process_page_paddleocr_sync(image: Image.Image, predictor: Any) -> tuple[str, float]`: Converts PPStructure regions (`type`: `Text`, `Title`, `Table`, `Header`, `Footer`) to markdown & mean confidence.
  - `_process_page_sync(image: Image.Image, predictor: Any, engine: str = "paddleocr") -> tuple[str, float]`: Dispatches to `_process_page_paddleocr_sync` or Surya page processing.
  - `ocr_page(..., engine: str | None = None)`: Orchestrator passing `engine` through to predictor and sync processing.

- [ ] **Step 1: Write failing tests for PP-Structure recognition adapter in `tests/engine/test_recognize.py`**

Add tests that mock PP-Structure predictor output and verify:
1. `_process_page_paddleocr_sync` converts `Title` into `# Title`
2. `_process_page_paddleocr_sync` converts `Table` with HTML into markdown table rows
3. `_process_page_paddleocr_sync` drops `Header` blocks
4. `_process_page_paddleocr_sync` filters isolated numeric `Footer` blocks
5. `_process_page_paddleocr_sync` calculates accurate mean confidence across lines
6. `get_recognition_predictor("paddleocr")` instantiates `PPStructure` and caches it

Test code to add:
```python
def test_process_page_paddleocr_sync_formats_markdown_and_confidence():
    from unittest.mock import MagicMock
    from PIL import Image
    from engine.recognize import _process_page_paddleocr_sync

    mock_predictor = MagicMock()
    mock_predictor.return_value = [
        {
            "type": "Header",
            "bbox": [10, 10, 200, 30],
            "res": [([[10, 10, 200, 10, 200, 30, 10, 30]], ("Header Title", 0.95))],
        },
        {
            "type": "Title",
            "bbox": [50, 40, 300, 70],
            "res": [([[50, 40, 300, 40, 300, 70, 50, 70]], ("باب بىرىنچى", 0.98))],
        },
        {
            "type": "Text",
            "bbox": [50, 80, 400, 150],
            "res": [
                ([[50, 80, 400, 80, 400, 110, 50, 110]], ("بۇ بىرىنچى جۈملە.", 0.92)),
                ([[50, 115, 400, 115, 400, 145, 50, 145]], ("بۇ ئىككىنچى جۈملە.", 0.96)),
            ],
        },
        {
            "type": "Table",
            "bbox": [50, 160, 400, 250],
            "res": {
                "html": "<html><body><table><tr><td>تېما</td><td>12</td></tr></table></body></html>"
            },
        },
        {
            "type": "Footer",
            "bbox": [180, 280, 220, 295],
            "res": [([[180, 280, 220, 280, 220, 295, 180, 295]], ("42", 0.99))],
        },
    ]

    img = Image.new("RGB", (500, 300), color="white")
    markdown, confidence = _process_page_paddleocr_sync(img, mock_predictor)

    assert "# باب بىرىنچى" in markdown
    assert "بۇ بىرىنچى جۈملە." in markdown
    assert "بۇ ئىككىنچى جۈملە." in markdown
    assert "| تېما | 12 |" in markdown
    assert "Header Title" not in markdown
    assert "42" not in markdown  # isolated page footer filtered
    assert 0.90 <= confidence <= 0.99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/engine/test_recognize.py -k "test_process_page_paddleocr_sync"`  
Expected: FAIL with `ImportError: cannot import name '_process_page_paddleocr_sync'`

- [ ] **Step 3: Implement `_process_page_paddleocr_sync` and update predictor dispatcher in `engine/recognize.py`**

In `clients/kitabim-ocr/engine/recognize.py`:
1. Add `_paddle_predictor = None`.
2. Update `get_recognition_predictor(engine: str | None = None)`:
   - If target engine is `"paddleocr"`:
     ```python
     if target_engine == "paddleocr":
         if _paddle_predictor is not None:
             return _paddle_predictor
         async with _predictor_lock:
             if _paddle_predictor is None:
                 from paddleocr import PPStructure
                 loop = asyncio.get_running_loop()
                 _paddle_predictor = await loop.run_in_executor(
                     None,
                     partial(
                         PPStructure,
                         show_log=False,
                         image_orientation=True,
                         lang="ug",
                         layout=True,
                         table=True,
                         ocr=True,
                         use_gpu=False,
                     ),
                 )
         return _paddle_predictor
     ```
   - If target engine is `"surya"`: instantiate `RecognitionPredictor`.
   - Otherwise raise `ValueError`.

3. Implement `_process_page_paddleocr_sync`:
   - Convert PIL Image to BGR numpy array (`np.array(image.convert("RGB"))[:, :, ::-1]`).
   - Call `regions = predictor(img_arr)`.
   - Sort regions top-to-bottom by bounding box y0 coordinate.
   - For each region:
     - Discard if `type == "Header"` or if vertical marginalia (`_is_vertical_marginalia_block`).
     - If `type == "Footer"`: extract text; if isolated page number, discard.
     - If `type == "Title"`: extract line texts, format as `# {title_text}`.
     - If `type == "Table"`: if `res` has `'html'`, format via `_mixed_list_html_to_markdown` / `_format_table_row`.
     - If `type in ("Text", "List")`: extract lines `(polygon, (text, conf))`, join lines, collect `conf` into `confidences`.
   - Compute `mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0`.
   - Return `("\n\n".join(blocks), mean_confidence)`.

4. Update `ocr_page` to accept `engine: str | None = None` (defaulting to configured engine) and pass engine through to `_process_page_sync`.

- [ ] **Step 4: Run recognition tests to verify they pass**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/engine/test_recognize.py`  
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit recognition engine changes**

```bash
git add clients/kitabim-ocr/engine/recognize.py clients/kitabim-ocr/tests/engine/test_recognize.py
git commit -m "feat(kitabim-ocr): add PP-Structure recognition adapter and engine dispatching"
```

---

### Task 4: CLI and Server Updates (`main.py`, `preview/app_server.py`)

**Files:**
- Modify: `clients/kitabim-ocr/main.py`
- Modify: `clients/kitabim-ocr/preview/app_server.py`
- Modify: `clients/kitabim-ocr/tests/test_main.py`
- Modify: `clients/kitabim-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- CLI `--engine` accepts choices `["paddleocr", "surya"]` with default resolving to `paddleocr`.
- App server initializes predictor with configured or CLI-specified engine.

- [ ] **Step 1: Write failing tests for CLI `--engine` choices in `tests/test_main.py`**

Add tests verifying `--engine paddleocr` and `--engine surya` are accepted by argument parser:
```python
def test_parser_accepts_paddleocr_engine():
    from main import build_parser
    parser = build_parser()
    args = parser.parse_args(["app", "--engine", "paddleocr"])
    assert args.engine == "paddleocr"

def test_parser_accepts_surya_engine():
    from main import build_parser
    parser = build_parser()
    args = parser.parse_args(["app", "--engine", "surya"])
    assert args.engine == "surya"
```

- [ ] **Step 2: Run tests to verify failure**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/test_main.py -k "test_parser_accepts_paddleocr"`  
Expected: FAIL (invalid choice: 'paddleocr')

- [ ] **Step 3: Update `main.py` and `preview/app_server.py`**

In `clients/kitabim-ocr/main.py`:
- Update `choices=["paddleocr", "surya"]` in `build_parser()` and `app_parser`.
- Update help strings from `"Surya"` to `"PaddleOCR (default) or Surya"`.

In `clients/kitabim-ocr/preview/app_server.py`:
- Update default engine resolution and logging to reference `paddleocr`.

- [ ] **Step 4: Run CLI and server test suites to verify passing**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/test_main.py clients/kitabim-ocr/tests/preview/test_app_server.py`  
Expected: PASS

- [ ] **Step 5: Commit CLI and server changes**

```bash
git add clients/kitabim-ocr/main.py clients/kitabim-ocr/preview/app_server.py clients/kitabim-ocr/tests/test_main.py clients/kitabim-ocr/tests/preview/test_app_server.py
git commit -m "feat(kitabim-ocr): update CLI and preview server to support paddleocr engine"
```

---

### Task 5: Documentation & Locale Updates

**Files:**
- Modify: `clients/kitabim-ocr/README.md`
- Modify: `clients/kitabim-ocr/locales/en.json`
- Modify: `clients/kitabim-ocr/locales/ug.json`
- Modify: `clients/kitabim-ocr/tests/test_i18n.py`

**Interfaces:**
- User-facing descriptions and locale strings reflect PaddleOCR as primary and Surya as secondary.

- [ ] **Step 1: Check existing locale strings and tests**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/test_i18n.py`  
Expected: PASS

- [ ] **Step 2: Update `clients/kitabim-ocr/README.md`**

Update README description and concurrency sections:
- Explain that PaddleOCR (PP-Structure) is the default local OCR engine.
- Note that Surya OCR remains available via `--engine surya` or `KITABIM_OCR_ENGINE=surya`.
- Document pip installation requirements for PaddlePaddle and PaddleOCR.

- [ ] **Step 3: Update `clients/kitabim-ocr/locales/en.json` and `ug.json`**

Update any strings referencing Surya OCR engine to refer to PaddleOCR/multi-engine.

- [ ] **Step 4: Run full test suite across all `clients/kitabim-ocr/tests`**

Run: `./venv/bin/pytest clients/kitabim-ocr/tests/`  
Expected: PASS (all 243+ tests passing)

- [ ] **Step 5: Commit docs and locale changes**

```bash
git add clients/kitabim-ocr/README.md clients/kitabim-ocr/locales/en.json clients/kitabim-ocr/locales/ug.json
git commit -m "docs(kitabim-ocr): update documentation and locales for paddleocr default engine"
```
