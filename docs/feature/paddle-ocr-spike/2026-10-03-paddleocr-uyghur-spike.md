# PaddleOCR Uyghur Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Baidu's PaddleOCR (`lang='ug'`) as an experimental third OCR engine alongside Surya and Savitr in `clients/kitabim-ocr`, provide an in-UI engine switcher and page redo workflow, and enable qualitative comparison of Uyghur text accuracy against Surya.

**Architecture:** Add `paddle` engine support to `engine/config.py`, create a dedicated `PaddleEnginePredictor` adapter in `engine/paddle_engine.py` that normalizes Paddle bounding boxes into RTL reading order bands and blocks compatible with Kitabim's downstream cleanup, wire the predictor into `engine/recognize.py`, expose engine selection and page redo endpoints in `preview/app_server.py`, and add the UI dropdown selector in the web client header.

**Tech Stack:** Python 3.13, FastAPI, Uvicorn, PaddleOCR, PaddlePaddle, PyMuPDF, Pillow, Beautiful Soup 4, pytest, pytest-asyncio.

## Global Constraints

- Standalone tool: all code changes are confined to `clients/kitabim-ocr/` and repository documentation. Do not modify Docker Compose or deployment scripts.
- Concurrency for PaddleOCR is capped at `DEFAULT_PADDLE_CONCURRENCY = 2` to prevent memory contention on local hardware.
- Python 3.13 virtual environment compatibility (`clients/kitabim-ocr/.venv`).
- Follow TDD: write failing test, verify failure, implement minimal code, verify pass, commit.
- Preserve existing behavior and 100% test pass rate for `surya` and `savitr` engines.

---

### Task 1: Engine Configuration & Concurrency for PaddleOCR

**Files:**
- Modify: `clients/kitabim-ocr/engine/config.py`
- Modify: `clients/kitabim-ocr/tests/engine/test_config.py`

**Interfaces:**
- Consumes: `os.environ`
- Produces:
  - `SUPPORTED_OCR_ENGINES = ("surya", "savitr", "paddle")`
  - `OcrEngineName = Literal["surya", "savitr", "paddle"]`
  - `DEFAULT_PADDLE_CONCURRENCY: int = 2`
  - `MAX_PADDLE_CONCURRENCY: int = 2`
  - `is_paddle_available() -> bool`
  - `resolve_concurrency(engine: str | None, requested: int | None = None) -> int` (updated to handle "paddle")

- [ ] **Step 1: Write the failing tests in `tests/engine/test_config.py`**

Add tests checking that `"paddle"` is a supported engine, `is_paddle_available()` works, and `resolve_concurrency("paddle")` caps at 2.

```python
def test_is_paddle_available(monkeypatch):
    from engine.config import is_paddle_available

    # Should return bool without raising
    res = is_paddle_available()
    assert isinstance(res, bool)


def test_get_configured_engine_paddle(monkeypatch):
    from engine.config import get_configured_engine

    monkeypatch.setenv("KITABIM_OCR_ENGINE", "paddle")
    assert get_configured_engine() == "paddle"


def test_resolve_concurrency_paddle():
    from engine.config import resolve_concurrency

    # Defaults to 2 and clamps to MAX_PADDLE_CONCURRENCY (2)
    assert resolve_concurrency("paddle") == 2
    assert resolve_concurrency("paddle", 4) == 2
    assert resolve_concurrency("paddle", 1) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_config.py -k "paddle" -v`  
Expected: FAIL with `ImportError: cannot import name 'is_paddle_available'` or `ValueError: Unsupported OCR engine 'paddle'`.

- [ ] **Step 3: Update `engine/config.py`**

Modify [`clients/kitabim-ocr/engine/config.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/config.py):
1. Update engine constants:
   ```python
   DEFAULT_OCR_ENGINE = "surya"
   SUPPORTED_OCR_ENGINES = ("surya", "savitr", "paddle")
   OcrEngineName = Literal["surya", "savitr", "paddle"]
   DEFAULT_PADDLE_CONCURRENCY = 2
   MAX_PADDLE_CONCURRENCY = 2
   ```
2. Add `is_paddle_available()`:
   ```python
   def is_paddle_available() -> bool:
       """Return True if paddle and paddleocr dependencies can be imported."""
       try:
           import paddle  # noqa: F401
           import paddleocr  # noqa: F401

           return True
       except ImportError:
           return False
   ```
3. Update `resolve_concurrency`:
   ```python
   def resolve_concurrency(engine: str | None, requested: int | None = None) -> int:
       target_engine = (engine or get_configured_engine()).strip().lower()
       if target_engine == "savitr":
           return 1
       if target_engine == "paddle":
           max_limit = MAX_PADDLE_CONCURRENCY
           default_val = DEFAULT_PADDLE_CONCURRENCY
           if requested is not None:
               return min(max(1, requested), max_limit)
           return get_configured_concurrency(default=default_val, max_limit=max_limit)
       # surya default
       max_limit = MAX_SURYA_CONCURRENCY
       if requested is not None:
           return min(max(1, requested), max_limit)
       return get_configured_concurrency(default=DEFAULT_OCR_CONCURRENCY, max_limit=max_limit)
   ```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_config.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/config.py clients/kitabim-ocr/tests/engine/test_config.py
git commit -m "feat(ocr-client): add paddle engine configuration and concurrency resolution"
```

---

### Task 2: Paddle Engine Adapter (`engine/paddle_engine.py`)

**Files:**
- Create: `clients/kitabim-ocr/engine/paddle_engine.py`
- Create: `clients/kitabim-ocr/tests/engine/test_paddle_engine.py`

**Interfaces:**
- Consumes: `PIL.Image.Image`, `paddleocr.PaddleOCR`
- Produces:
  - `class PaddleEnginePredictor`
  - `def cluster_lines_into_reading_order(boxes_with_text: list[dict[str, Any]]) -> list[dict[str, Any]]`
  - `def normalize_uyghur_text_direction(text: str) -> str`
  - `class PaddleRecognitionResult`: contains `.blocks` with `.reading_order`, `.confidence`, `.html`, `.label`, `.bbox`

- [ ] **Step 1: Write the failing tests in `tests/engine/test_paddle_engine.py`**

Test line clustering in RTL reading order (top-to-bottom, right-to-left within line band), Uyghur text normalization, and block generation.

```python
from __future__ import annotations

import pytest
from engine.paddle_engine import (
    cluster_lines_into_reading_order,
    normalize_uyghur_text_direction,
    PaddleEnginePredictor,
)


def test_normalize_uyghur_text_direction_standard():
    # Regular logical Uyghur text
    text = "ئۇيغۇر كىتابلىرى"
    normalized = normalize_uyghur_text_direction(text)
    assert normalized == text


def test_cluster_lines_into_reading_order_sorts_rtl_and_ttb():
    # Two lines: line 1 at y~100 (two words right and left), line 2 at y~200
    items = [
        {"bbox": [50, 100, 150, 130], "text": "سۆز2", "confidence": 0.95},  # left word
        {"bbox": [200, 100, 300, 130], "text": "سۆز1", "confidence": 0.98}, # right word (starts first in RTL)
        {"bbox": [100, 200, 250, 230], "text": "ئىككىنچى قۇر", "confidence": 0.92}, # second line
    ]
    sorted_items = cluster_lines_into_reading_order(items)
    # Line 1 right word should come before Line 1 left word
    assert sorted_items[0]["text"] == "سۆز1"
    assert sorted_items[1]["text"] == "سۆز2"
    assert sorted_items[2]["text"] == "ئىككىنچى قۇر"


def test_paddle_predictor_mock_inference():
    class DummyPaddle:
        def ocr(self, img_arr, cls=True):
            return [[
                [[[10, 10], [100, 10], [100, 40], [10, 40]], ("سەھىپە بېشى", 0.96)],
                [[[10, 60], [200, 60], [200, 90], [10, 90]], ("بىرىنچى ئابزاس", 0.91)],
            ]]

    predictor = PaddleEnginePredictor(ocr_instance=DummyPaddle())
    from PIL import Image
    dummy_img = Image.new("RGB", (300, 300), color="white")
    result = predictor.recognize_image(dummy_img)

    assert len(result.blocks) == 2
    assert result.blocks[0].label == "Text"
    assert "سەھىپە بېشى" in result.blocks[0].html
    assert result.blocks[0].reading_order == 0
    assert result.blocks[1].reading_order == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_paddle_engine.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'engine.paddle_engine'`.

- [ ] **Step 3: Implement `engine/paddle_engine.py`**

Write `clients/kitabim-ocr/engine/paddle_engine.py`:
- `normalize_uyghur_text_direction(text: str) -> str`: handles standard Unicode logical flow.
- `cluster_lines_into_reading_order(items: list[dict[str, Any]]) -> list[dict[str, Any]]`: sorts vertical bands by `min_y`, then within each band sorts boxes right-to-left (descending `max_x`).
- `PaddleBlock`: lightweight class with attributes `label="Text"`, `html="<p>...</p>"`, `confidence`, `reading_order`, `bbox`, `skipped=False`, `error=False`.
- `PaddleRecognitionResult`: container with `.blocks`.
- `PaddleEnginePredictor`: accepts optional `ocr_instance` (for mocking) or lazy-loads `PaddleOCR(use_angle_cls=True, lang='ug', use_gpu=False)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_paddle_engine.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/paddle_engine.py clients/kitabim-ocr/tests/engine/test_paddle_engine.py
git commit -m "feat(ocr-client): implement paddle engine adapter and RTL reading order normalization"
```

---

### Task 3: Integration into `engine/recognize.py`

**Files:**
- Modify: `clients/kitabim-ocr/engine/recognize.py`
- Modify: `clients/kitabim-ocr/tests/engine/test_recognize.py`

**Interfaces:**
- Consumes: `engine.paddle_engine.PaddleEnginePredictor`
- Produces:
  - `get_recognition_predictor(engine: str | None = None)` supporting `engine="paddle"`
  - `recognize_page(predictor: Any, image: Image.Image)` supporting `PaddleEnginePredictor`

- [ ] **Step 1: Write the failing tests in `tests/engine/test_recognize.py`**

Add test in `tests/engine/test_recognize.py` verifying `get_recognition_predictor(engine="paddle")` instantiates `PaddleEnginePredictor` and `recognize_page()` delegates to it.

```python
@pytest.mark.asyncio
async def test_get_recognition_predictor_paddle_constructs_and_caches():
    with patch("engine.paddle_engine.PaddleEnginePredictor") as mock_cls:
        instance = MagicMock()
        mock_cls.return_value = instance

        # Reset cached predictor if any
        import engine.recognize as rec
        rec._paddle_predictor = None

        p1 = await rec.get_recognition_predictor(engine="paddle")
        p2 = await rec.get_recognition_predictor(engine="paddle")

        assert p1 is instance
        assert p2 is instance
        assert mock_cls.call_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_recognize.py -k "paddle" -v`  
Expected: FAIL with `ValueError: Unknown OCR engine 'paddle'`.

- [ ] **Step 3: Update `engine/recognize.py`**

Modify [`clients/kitabim-ocr/engine/recognize.py`](file:///Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/engine/recognize.py):
1. Import `PaddleEnginePredictor` from `engine.paddle_engine`.
2. Add global `_paddle_predictor: Any = None`.
3. In `get_recognition_predictor()`:
   ```python
   if target_engine == "paddle":
       if _paddle_predictor is not None:
           return _paddle_predictor
       async with _predictor_lock:
           if _paddle_predictor is None:
               loop = asyncio.get_running_loop()
               _paddle_predictor = await loop.run_in_executor(
                   None, PaddleEnginePredictor
               )
       return _paddle_predictor
   ```
4. In `recognize_page(predictor, image)`:
   ```python
   if isinstance(predictor, SavitrPredictor):
       return predictor.recognize_image(image)
   if isinstance(predictor, PaddleEnginePredictor):
       return predictor.recognize_image(image)
   return predictor([image], full_page=True)[0]
   ```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/engine/test_recognize.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/engine/recognize.py clients/kitabim-ocr/tests/engine/test_recognize.py
git commit -m "feat(ocr-client): wire paddle engine predictor into recognition pipeline"
```

---

### Task 4: UI Engine Switcher & Dynamic Redo Endpoints in `preview/app_server.py`

**Files:**
- Modify: `clients/kitabim-ocr/preview/app_server.py`
- Modify: `clients/kitabim-ocr/tests/preview/test_app_server.py`

**Interfaces:**
- Consumes: `engine.config.SUPPORTED_OCR_ENGINES`, `engine.recognize.get_recognition_predictor`
- Produces:
  - `POST /api/settings/engine`: changes active engine in `state.engine`
  - `POST /api/redo/{page_num}`: accepts optional `engine` in request body
  - HTML UI `<select id="engineSelector">` in navigation bar

- [ ] **Step 1: Write the failing tests in `tests/preview/test_app_server.py`**

Test switching engine via `/api/settings/engine` and redoing a page with an engine override.

```python
def test_switch_engine_endpoint(client):
    resp = client.post("/api/settings/engine", json={"engine": "paddle"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["engine"] == "paddle"


def test_switch_engine_invalid(client):
    resp = client.post("/api/settings/engine", json={"engine": "invalid_engine"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/preview/test_app_server.py -k "switch_engine" -v`  
Expected: FAIL with 404 Not Found.

- [ ] **Step 3: Update `preview/app_server.py`**

1. Add engine label helper:
   ```python
   def get_engine_display_name(engine_name: str) -> str:
       if engine_name == "savitr":
           return "Savitr OCR (MLX)"
       if engine_name == "paddle":
           return "PaddleOCR (Uyghur)"
       return "Surya OCR"
   ```
2. In `get_app_html()`, replace static `<span>__OCR_ENGINE_LABEL__</span>` with an interactive `<select id="engineSelector">`:
   - Options: `surya`, `savitr` (disabled if not Apple Silicon), `paddle`.
   - Wire JavaScript `change` event on `#engineSelector` to `fetch('/api/settings/engine', {method: 'POST', body: JSON.stringify({engine: this.value})})`.
3. Add `POST /api/settings/engine`:
   - Validates `engine in SUPPORTED_OCR_ENGINES`.
   - Updates `state.engine = req.engine` and `state.concurrency = resolve_concurrency(state.engine)`.
4. Update `POST /api/redo/{page_num}`:
   - Accept optional `engine: str = None` in `RedoPageRequest` body.
   - If provided, use `target_engine = body.engine or state.engine`.
   - Fetch `predictor = await get_recognition_predictor(target_engine)`.
   - Record `engine: target_engine` in `page.json`.

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest tests/preview/test_app_server.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add clients/kitabim-ocr/preview/app_server.py clients/kitabim-ocr/tests/preview/test_app_server.py
git commit -m "feat(ocr-client): add engine switcher UI and dynamic redo endpoint"
```

---

### Task 5: CLI Options, Setup Command & Documentation

**Files:**
- Modify: `clients/kitabim-ocr/main.py`
- Modify: `clients/kitabim-ocr/requirements.txt`
- Modify: `clients/kitabim-ocr/README.md`

**Interfaces:**
- CLI: `python main.py app --engine paddle`
- CLI: `python main.py setup-paddle`

- [ ] **Step 1: Update `clients/kitabim-ocr/main.py`**

1. Update `--engine` argument choices in argument parsers to include `"paddle"`:
   `choices=["surya", "savitr", "paddle"]`.
2. Add subcommand `setup-paddle`:
   ```python
   def setup_paddle_cmd():
       """Download and initialize PaddleOCR Uyghur recognition models."""
       print("Checking PaddleOCR installation...")
       from engine.paddle_engine import PaddleEnginePredictor
       p = PaddleEnginePredictor()
       print("PaddleOCR Uyghur engine initialized successfully!")
   ```

- [ ] **Step 2: Update `requirements.txt` and `README.md`**

1. Add `paddlepaddle>=3.0.0`, `paddleocr>=2.9.0`, and `python-bidi>=0.4.2` to `requirements.txt`.
2. Document PaddleOCR usage, setup, and engine switching in `README.md`.

- [ ] **Step 3: Run full test suite**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pytest`  
Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add clients/kitabim-ocr/main.py clients/kitabim-ocr/requirements.txt clients/kitabim-ocr/README.md
git commit -m "feat(ocr-client): add cli paddle engine support and setup command"
```

---

### Task 6: End-to-End Spike Verification on Fixture Book

**Files:**
- Test execution and qualitative comparison on `clients/kitabim-ocr/fixtures/test_book.pdf`

- [ ] **Step 1: Install Paddle dependencies into virtual environment**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/pip install paddlepaddle paddleocr python-bidi`

- [ ] **Step 2: Initialize PaddleOCR weights**

Run: `/Users/Omarjan/Projects/kitabim-ai/clients/kitabim-ocr/.venv/bin/python clients/kitabim-ocr/main.py setup-paddle`

- [ ] **Step 3: Run comparative OCR test on fixture page**

Execute a test script to compare Surya and PaddleOCR output on Page 1 of `clients/kitabim-ocr/fixtures/test_book.pdf`, noting:
- Character recognition accuracy on Uyghur vowels and diacritics
- RTL line ordering and paragraph structure
- Processing time per page

- [ ] **Step 4: Document spike findings**

Add a summary section to `docs/superpowers/specs/2026-10-03-paddleocr-uyghur-spike-design.md` detailing qualitative accuracy findings, observations, and recommendations for production adoption.

- [ ] **Step 5: Final commit**

```bash
git add docs/
git commit -m "docs: document PaddleOCR vs Surya Uyghur spike findings"
```
