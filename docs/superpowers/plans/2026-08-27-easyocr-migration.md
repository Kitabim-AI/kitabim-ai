# EasyOCR Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fully replace the Gemini Vision cloud OCR pipeline with self-hosted, CPU-capable EasyOCR for Uyghur book page transcription and structural markdown reconstruction, keeping scanned content strictly on-premise/offline.

**Architecture:** A new `easyocr_service.py` provides an offline OCR engine executing EasyOCR in a dedicated `ThreadPoolExecutor` using a singleton `Reader(['ug'], gpu=False)`. Geometric box clustering and formatting heuristics (`ocr_structure.py`) classify headers/footers, headings, poems, and TOC tables into clean Markdown, followed by regex-based dictionary auto-corrections (`ocr_corrections.py`). `ocr_job.py` dynamically routes pages based on the `ocr_engine` system configuration key.

**Tech Stack:** Python 3.13, PyMuPDF (`fitz`), EasyOCR, PyTorch (CPU-only), OpenCV / Pillow, SQLAlchemy, ARQ.

## Global Constraints

- **Compute Target:** CPU-only. Concurrency per worker process defaulted to 1 (`ocr_easyocr_max_parallel_pages`).
- **Offline Operation:** Model weights (`ug` recognition & CRAFT detection) must be baked into `Dockerfile.worker` during image build — no runtime downloads or external network calls.
- **Backward Compatibility & Preserved Flow:** Output Markdown conventions (`#`/`##` headings, `| text | page |` TOC rows, stripped header/footer furniture) must match existing reader and downstream ingestion expectations.
- **LLM Prompts Rule:** Gemini OCR prompt remains dormant and unchanged in English; no code in this migration creates non-English prompts.

---

### Task 1: Geometric Structure & Markdown Reconstruction Engine (`ocr_structure.py`)

**Files:**
- Create: `packages/backend-core/app/utils/ocr_structure.py`
- Test: `packages/backend-core/tests/app/utils/ocr_structure_test.py`

**Interfaces:**
- Consumes: EasyOCR detection tuples `[(bbox, text, confidence), ...]` where `bbox` is `[[x1,y1], [x2,y1], [x2,y2], [x1,y2]]` or 4-corner coordinates, and page dimensions `(page_width, page_height)`.
- Produces: `assemble_page_markdown(detections, page_width, page_height, header_footer_band_pct, heading_size_ratio) -> str`

- [ ] **Step 1: Write the failing test**

```python
# packages/backend-core/tests/app/utils/ocr_structure_test.py
import pytest
from app.utils.ocr_structure import (
    cluster_lines,
    order_line_rtl,
    filter_header_footer,
    detect_headings,
    format_toc_lines,
    assemble_page_markdown,
)


def test_order_line_rtl():
    # Boxes across the same line from left to right (x=10, x=50, x=100)
    # Uyghur is RTL, so text should be sorted descending by X (x=100 first, then 50, then 10)
    b1 = ([[10, 100], [30, 100], [30, 120], [10, 120]], "بىر", 0.9)
    b2 = ([[50, 100], [80, 100], [80, 120], [50, 120]], "ئىككى", 0.95)
    b3 = ([[100, 100], [140, 100], [140, 120], [100, 120]], "ئۈچ", 0.92)

    ordered = order_line_rtl([b1, b2, b3])
    texts = [item[1] for item in ordered]
    assert texts == ["ئۈچ", "ئىككى", "بىر"]


def test_filter_header_footer():
    page_height = 1000.0
    band_pct = 0.08  # 80px from top and bottom
    # Top header at y=40
    header_box = ([[50, 30], [200, 30], [200, 50], [50, 50]], "Header Title", 0.9)
    # Body line at y=500
    body_box = ([[50, 490], [400, 490], [400, 510], [50, 510]], "Body Content", 0.95)
    # Footer line at y=960
    footer_box = ([[200, 950], [250, 950], [250, 970], [200, 970]], "12", 0.9)

    filtered = filter_header_footer([header_box, body_box, footer_box], page_height, band_pct)
    assert len(filtered) == 1
    assert filtered[0][1] == "Body Content"


def test_detect_headings():
    # Normal body lines height ~20px
    line1 = [([[50, 100], [500, 100], [500, 120], [50, 120]], "بىرىنچى ئابزاس مەزمۇنى", 0.9)]
    line2 = [([[50, 130], [500, 130], [500, 150], [50, 150]], "ئىككىنچى ئابزاس مەزمۇنى", 0.9)]
    # Big heading line height ~35px
    heading_line = [([[100, 50], [300, 50], [300, 90], [100, 90]], "كىرىش سۆز", 0.95)]

    lines = [heading_line, line1, line2]
    res = detect_headings(lines, heading_size_ratio=1.3)
    assert res[0].startswith("# ")
    assert "كىرىش سۆز" in res[0]
    assert not res[1].startswith("#")


def test_assemble_page_markdown_integration():
    page_width = 600.0
    page_height = 800.0
    # Header at y=30 (should be excluded)
    header = ([[50, 20], [200, 20], [200, 40], [50, 40]], "كىتاب نامى", 0.99)
    # Heading at y=100 (height 40px)
    heading = ([[150, 80], [450, 80], [450, 120], [150, 120]], "1-باپ", 0.95)
    # Body text at y=160
    body = ([[50, 150], [550, 150], [550, 170], [50, 170]], "بۇ بىر سىناق جۈملە.", 0.9)
    # Footer at y=760 (should be excluded)
    footer = ([[280, 750], [320, 750], [320, 770], [280, 770]], "15", 0.9)

    detections = [header, heading, body, footer]
    md = assemble_page_markdown(detections, page_width, page_height)
    assert "كىتاب نامى" not in md
    assert "15" not in md
    assert "# 1-باپ" in md
    assert "بۇ بىر سىناق جۈملە." in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/utils/ocr_structure_test.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.ocr_structure'"

- [ ] **Step 3: Implement `ocr_structure.py`**

```python
# packages/backend-core/app/utils/ocr_structure.py
from __future__ import annotations

import statistics
from typing import List, Tuple, Any
from app.utils.text import clean_uyghur_text, is_toc_page

DetectionBox = Tuple[List[List[float]], str, float]


def _get_box_geometry(bbox: List[List[float]]) -> tuple[float, float, float, float, float, float]:
    """Returns (min_x, max_x, min_y, max_y, center_x, center_y)."""
    xs = [p[0] for p in bbox]
    ys = [p[1] for p in bbox]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    return min_x, max_x, min_y, max_y, (min_x + max_x) / 2.0, (min_y + max_y) / 2.0


def filter_header_footer(
    detections: List[DetectionBox], page_height: float, band_pct: float = 0.08
) -> List[DetectionBox]:
    """Exclude detections falling inside top or bottom margin bands."""
    if page_height <= 0:
        return detections
    top_threshold = page_height * band_pct
    bottom_threshold = page_height * (1.0 - band_pct)

    filtered = []
    for item in detections:
        bbox, text, conf = item
        _, _, _, _, _, cy = _get_box_geometry(bbox)
        if top_threshold <= cy <= bottom_threshold:
            filtered.append(item)
    return filtered


def cluster_lines(
    detections: List[DetectionBox], line_tol_ratio: float = 0.6
) -> List[List[DetectionBox]]:
    """Group detection boxes into horizontal lines based on overlapping vertical coordinates."""
    if not detections:
        return []

    # Sort boxes primarily by vertical center
    sorted_boxes = sorted(detections, key=lambda it: _get_box_geometry(it[0])[5])

    lines: List[List[DetectionBox]] = []
    current_line: List[DetectionBox] = []
    current_line_y = 0.0
    current_line_h = 0.0

    for item in sorted_boxes:
        bbox, text, conf = item
        _, _, min_y, max_y, _, cy = _get_box_geometry(bbox)
        h = max_y - min_y

        if not current_line:
            current_line.append(item)
            current_line_y = cy
            current_line_h = h
            continue

        tolerance = max(current_line_h, h) * line_tol_ratio
        if abs(cy - current_line_y) <= tolerance:
            current_line.append(item)
            current_line_y = sum(_get_box_geometry(b[0])[5] for b in current_line) / len(current_line)
            current_line_h = max(current_line_h, h)
        else:
            lines.append(current_line)
            current_line = [item]
            current_line_y = cy
            current_line_h = h

    if current_line:
        lines.append(current_line)

    return lines


def order_line_rtl(line_boxes: List[DetectionBox]) -> List[DetectionBox]:
    """Sort items within a line right-to-left (x descending)."""
    return sorted(line_boxes, key=lambda it: _get_box_geometry(it[0])[4], reverse=True)


def detect_headings(
    lines: List[List[DetectionBox]],
    heading_size_ratio: float = 1.3,
    page_width: float = 0.0,
) -> List[str]:
    """
    Format lines into text strings, detecting headings by comparing line height to median.
    """
    if not lines:
        return []

    line_heights = []
    formatted_lines_raw = []

    for line in lines:
        rtl_ordered = order_line_rtl(line)
        line_text = " ".join(item[1].strip() for item in rtl_ordered if item[1].strip())
        if not line_text:
            continue
        h = sum((_get_box_geometry(b[0])[3] - _get_box_geometry(b[0])[2]) for b in line) / len(line)
        line_heights.append(h)
        formatted_lines_raw.append((line_text, h, line))

    if not line_heights:
        return []

    median_height = statistics.median(line_heights)

    result_lines = []
    for line_text, h, line_boxes in formatted_lines_raw:
        if median_height > 0 and (h / median_height) >= heading_size_ratio:
            if (h / median_height) >= (heading_size_ratio * 1.3):
                result_lines.append(f"# {line_text}")
            else:
                result_lines.append(f"## {line_text}")
        else:
            result_lines.append(line_text)

    return result_lines


def format_toc_lines(lines: List[str]) -> List[str]:
    """Convert lines with dot leaders / trailing page numbers into '| title | page |' markdown table rows."""
    import re
    dot_pattern = re.compile(r"(\.{3,}|_{3,}|-{3,}|·{3,})")
    formatted = []
    for line in lines:
        if dot_pattern.search(line):
            m = re.search(r"^(.*?)(?:[\.·\-_]{3,}|\s{3,})(\d+)\s*$", line)
            if m:
                title, page_num = m.group(1).strip(), m.group(2).strip()
                formatted.append(f"| {title} | {page_num} |")
                continue
        formatted.append(line)
    return formatted


def assemble_page_markdown(
    detections: List[DetectionBox],
    page_width: float,
    page_height: float,
    header_footer_band_pct: float = 0.08,
    heading_size_ratio: float = 1.3,
) -> str:
    """Assembles EasyOCR detections into clean, structured Markdown."""
    if not detections:
        return ""

    body_detections = filter_header_footer(detections, page_height, header_footer_band_pct)
    if not body_detections:
        return ""

    lines = cluster_lines(body_detections)
    detected_lines = detect_headings(lines, heading_size_ratio, page_width)

    raw_text = "\n".join(detected_lines)
    if is_toc_page(raw_text):
        detected_lines = format_toc_lines(detected_lines)
        raw_text = "\n".join(detected_lines)

    return clean_uyghur_text(raw_text)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/utils/ocr_structure_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/utils/ocr_structure.py packages/backend-core/tests/app/utils/ocr_structure_test.py
git commit -m "feat(ocr): add geometric structure reconstruction and markdown formatting for EasyOCR"
```

---

### Task 2: Rule-Based Auto-Correction Engine (`ocr_corrections.py`)

**Files:**
- Create: `packages/backend-core/app/utils/ocr_corrections.py`
- Test: `packages/backend-core/tests/app/utils/ocr_corrections_test.py`

**Interfaces:**
- Consumes: `raw_text: str`, `pairs: list[tuple[str, str]]`
- Produces: `apply_auto_corrections(text: str, pairs: list[tuple[str, str]]) -> str`

- [ ] **Step 1: Write the failing test**

```python
# packages/backend-core/tests/app/utils/ocr_corrections_test.py
import pytest
from app.utils.ocr_corrections import apply_auto_corrections


def test_apply_auto_corrections_basic():
    # Word substitution
    pairs = [
        ("مۇئەللىم", "مۇئەللىم"),  # identity
        ("كىتاپ", "كىتاب"),
        ("مەكتەپكە", "مەكتەپكە"),
    ]
    text = "بۇ كىتاپ ناھايىتى ياخشى كىتاپ ئىكەن."
    corrected = apply_auto_corrections(text, pairs)
    assert corrected == "بۇ كىتاب ناھايىتى ياخشى كىتاب ئىكەن."


def test_apply_auto_corrections_word_boundary():
    pairs = [("ئان", "ئانا")]
    # Should not replace substring inside "ئانىلار"
    text = "ئان كەلدى ئانىلار بىلەن."
    corrected = apply_auto_corrections(text, pairs)
    assert corrected == "ئانا كەلدى ئانىلار بىلەن."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/utils/ocr_corrections_test.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.utils.ocr_corrections'"

- [ ] **Step 3: Implement `ocr_corrections.py`**

```python
# packages/backend-core/app/utils/ocr_corrections.py
from __future__ import annotations

import re
from typing import List, Tuple


def apply_auto_corrections(text: str, pairs: List[Tuple[str, str]]) -> str:
    """
    Apply word-level auto-correction pairs to transcribed Uyghur text.
    Uses regex boundaries that respect Uyghur Arabic script characters.
    """
    if not text or not pairs:
        return text

    valid_pairs = [(wrong.strip(), correct.strip()) for wrong, correct in pairs if wrong.strip() and wrong.strip() != correct.strip()]
    if not valid_pairs:
        return text

    valid_pairs.sort(key=lambda p: len(p[0]), reverse=True)

    result = text
    for wrong, correct in valid_pairs:
        pattern = re.compile(rf"(?<![\u0600-\u06FF\w]){re.escape(wrong)}(?![\u0600-\u06FF\w])")
        result = pattern.sub(correct, result)

    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/utils/ocr_corrections_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/utils/ocr_corrections.py packages/backend-core/tests/app/utils/ocr_corrections_test.py
git commit -m "feat(ocr): add regex-based word autocorrection for EasyOCR output"
```

---

### Task 3: EasyOCR Service Implementation (`easyocr_service.py`)

**Files:**
- Create: `packages/backend-core/app/services/easyocr_service.py`
- Test: `packages/backend-core/tests/app/services/easyocr_service_test.py`

**Interfaces:**
- Consumes: `page: fitz.Page`, `timeout: float | None`, `correction_pairs: list[tuple[str, str]] | None`, configuration options.
- Produces: `ocr_page_with_easyocr(page: fitz.Page, timeout: float | None = None, ...) -> str`

- [ ] **Step 1: Write the failing test**

```python
# packages/backend-core/tests/app/services/easyocr_service_test.py
import pytest
from unittest.mock import MagicMock, patch
import fitz
from app.services.easyocr_service import ocr_page_with_easyocr, LowConfidenceOcrError


@pytest.mark.asyncio
async def test_ocr_page_with_easyocr_success():
    mock_fitz_page = MagicMock(spec=fitz.Page)
    mock_fitz_page.rect.width = 600
    mock_fitz_page.rect.height = 800
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_image_bytes"
    mock_pix.samples = b"\x00\x10\x20\x30" * 100
    mock_fitz_page.get_pixmap.return_value = mock_pix

    fake_detection = [
        ([[50, 100], [200, 100], [200, 130], [50, 130]], "سەھىپە مەزمۇنى", 0.95)
    ]

    with patch("app.services.easyocr_service.get_easyocr_reader") as mock_get_reader:
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = fake_detection
        mock_get_reader.return_value = mock_reader

        result = await ocr_page_with_easyocr(mock_fitz_page)
        assert "سەھىپە مەزمۇنى" in result


@pytest.mark.asyncio
async def test_ocr_page_with_easyocr_low_confidence():
    mock_fitz_page = MagicMock(spec=fitz.Page)
    mock_fitz_page.rect.width = 600
    mock_fitz_page.rect.height = 800
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"fake_image_bytes"
    mock_pix.samples = bytes(range(256)) * 10
    mock_fitz_page.get_pixmap.return_value = mock_pix

    low_conf_detection = [
        ([[50, 100], [200, 100], [200, 130], [50, 130]], "غۇۋا تېكىست", 0.1)
    ]

    with patch("app.services.easyocr_service.get_easyocr_reader") as mock_get_reader:
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = low_conf_detection
        mock_get_reader.return_value = mock_reader

        with pytest.raises(LowConfidenceOcrError):
            await ocr_page_with_easyocr(mock_fitz_page, min_confidence=0.5)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/services/easyocr_service_test.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.services.easyocr_service'"

- [ ] **Step 3: Implement `easyocr_service.py`**

```python
# packages/backend-core/app/services/easyocr_service.py
from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional
import fitz
import numpy as np
from PIL import Image, ImageEnhance

from app.core.config import settings
from app.utils.ocr_structure import assemble_page_markdown
from app.utils.ocr_corrections import apply_auto_corrections

logger = logging.getLogger("app.services.easyocr_service")

_READER_SINGLETON = None
_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="easyocr_worker")


class LowConfidenceOcrError(Exception):
    """Raised when EasyOCR detections have mean confidence below threshold on a non-blank page."""
    pass


def get_easyocr_reader():
    global _READER_SINGLETON
    if _READER_SINGLETON is None:
        import easyocr
        logger.info("Initializing singleton EasyOCR Reader(['ug'], gpu=False)...")
        _READER_SINGLETON = easyocr.Reader(["ug"], gpu=False)
    return _READER_SINGLETON


def _is_blank_image(image_bytes: bytes, variance_threshold: float = 10.0) -> bool:
    """Checks if image has very low pixel variance (blank/solid page)."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        arr = np.array(img)
        return float(np.var(arr)) < variance_threshold
    except Exception:
        return False


def _preprocess_image(image_bytes: bytes, contrast_factor: float = 1.0) -> bytes:
    """Applies contrast/brightness enhancement if requested on retry."""
    if contrast_factor == 1.0:
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        enhancer = ImageEnhance.Contrast(img)
        enhanced = enhancer.enhance(contrast_factor)
        buf = io.BytesIO()
        enhanced.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return image_bytes


def _sync_readtext(reader, img_bytes: bytes) -> list:
    return reader.readtext(img_bytes)


async def ocr_page_with_easyocr(
    page: fitz.Page,
    timeout: Optional[float] = None,
    min_confidence: float = 0.3,
    header_footer_band_pct: float = 0.08,
    heading_size_ratio: float = 1.3,
    correction_pairs: Optional[List[Tuple[str, str]]] = None,
    max_retries: int = 2,
) -> str:
    """
    Renders a PyMuPDF page, runs EasyOCR in a worker thread, reconstructs structure,
    and applies auto-corrections.
    """
    reader = get_easyocr_reader()
    loop = asyncio.get_running_loop()

    zoom_factors = [settings.ocr_page_zoom_factor, settings.ocr_page_zoom_factor * 1.25]
    contrast_factors = [1.0, 1.5]

    last_error = None

    for attempt in range(max_retries):
        zoom = zoom_factors[min(attempt, len(zoom_factors) - 1)]
        contrast = contrast_factors[min(attempt, len(contrast_factors) - 1)]

        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        img_bytes = pix.tobytes("png")

        if contrast != 1.0:
            img_bytes = _preprocess_image(img_bytes, contrast)

        try:
            readtext_future = loop.run_in_executor(_EXECUTOR, _sync_readtext, reader, img_bytes)
            if timeout:
                detections = await asyncio.wait_for(readtext_future, timeout=timeout)
            else:
                detections = await readtext_future

            if not detections:
                if _is_blank_image(img_bytes):
                    return ""
                if attempt < max_retries - 1:
                    continue
                return ""

            confidences = [item[2] for item in detections if len(item) > 2]
            mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

            if mean_conf < min_confidence and not _is_blank_image(img_bytes):
                raise LowConfidenceOcrError(f"EasyOCR mean confidence {mean_conf:.2f} < {min_confidence}")

            page_width = float(page.rect.width)
            page_height = float(page.rect.height)
            markdown = assemble_page_markdown(
                detections,
                page_width=page_width,
                page_height=page_height,
                header_footer_band_pct=header_footer_band_pct,
                heading_size_ratio=heading_size_ratio,
            )

            if correction_pairs:
                markdown = apply_auto_corrections(markdown, correction_pairs)

            return markdown

        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            raise last_error
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/services/easyocr_service_test.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/easyocr_service.py packages/backend-core/tests/app/services/easyocr_service_test.py
git commit -m "feat(ocr): add EasyOCR engine service with executor offload and confidence checks"
```

---

### Task 4: System Configs & Database Seeds

**Files:**
- Modify: `packages/backend-core/app/db/seeds.py`

**Interfaces:**
- Produces: New system configuration seeds for `ocr_engine`, `ocr_easyocr_max_parallel_pages`, `ocr_easyocr_header_footer_band_pct`, `ocr_easyocr_heading_size_ratio`, `ocr_easyocr_min_confidence`.

- [ ] **Step 1: Add seed configurations in `packages/backend-core/app/db/seeds.py`**

```python
# In packages/backend-core/app/db/seeds.py under DEFAULT_CONFIGS:
        {
            "key": "ocr_engine",
            "value": "easyocr",
            "description": "Active OCR engine ('easyocr' or 'gemini')",
            "data_type": "string",
            "group_name": "ocr",
        },
        {
            "key": "ocr_easyocr_max_parallel_pages",
            "value": "1",
            "description": "Max parallel pages processed per worker process using EasyOCR",
            "data_type": "integer",
            "group_name": "ocr",
        },
        {
            "key": "ocr_easyocr_header_footer_band_pct",
            "value": "0.08",
            "description": "Top/bottom margin ratio for header and footer exclusion in EasyOCR",
            "data_type": "float",
            "group_name": "ocr",
        },
        {
            "key": "ocr_easyocr_heading_size_ratio",
            "value": "1.3",
            "description": "Bbox height multiplier threshold to detect headings in EasyOCR",
            "data_type": "float",
            "group_name": "ocr",
        },
        {
            "key": "ocr_easyocr_min_confidence",
            "value": "0.3",
            "description": "Minimum mean confidence threshold for EasyOCR pages before retry",
            "data_type": "float",
            "group_name": "ocr",
        },
```

- [ ] **Step 2: Commit**

```bash
git add packages/backend-core/app/db/seeds.py
git commit -m "feat(config): add system config seeds for EasyOCR engine and layout thresholds"
```

---

### Task 5: Worker Job Integration & Routing (`ocr_job.py`)

**Files:**
- Modify: `services/worker/jobs/ocr_job.py`
- Modify: `services/worker/tests/jobs/ocr_job_test.py`

**Interfaces:**
- Consumes: `SystemConfigsRepository` values for `ocr_engine`, `ocr_easyocr_*`, `AutoCorrectRulesRepository`
- Dispatches: `ocr_page_with_easyocr` or `ocr_page_with_gemini`

- [ ] **Step 1: Write test cases for EasyOCR and Gemini routing**

Add test cases in `services/worker/tests/jobs/ocr_job_test.py`:
- `test_ocr_job_easyocr_engine_success`
- `test_ocr_job_gemini_fallback`

- [ ] **Step 2: Update `services/worker/jobs/ocr_job.py`**

Modify `ocr_job.py` configuration reading:
```python
            ocr_engine = (await config_repo.get_value("ocr_engine", "easyocr")).lower()
            ocr_max_retry_count_str = await config_repo.get_value("ocr_max_retry_count", "3")
            ocr_max_retry_count = int(ocr_max_retry_count_str)

            if ocr_engine == "easyocr":
                max_parallel_pages = int(await config_repo.get_value("ocr_easyocr_max_parallel_pages", "1"))
                easyocr_hf_band = float(await config_repo.get_value("ocr_easyocr_header_footer_band_pct", "0.08"))
                easyocr_heading_ratio = float(await config_repo.get_value("ocr_easyocr_heading_size_ratio", "1.3"))
                easyocr_min_conf = float(await config_repo.get_value("ocr_easyocr_min_confidence", "0.3"))
                easyocr_timeout_str = await config_repo.get_value("ocr_easyocr_timeout")
                easyocr_timeout = float(easyocr_timeout_str) if easyocr_timeout_str else None
                batch_ocr_enabled = False
            else:
                gemini_ocr_model = await config_repo.get_value("ocr_gemini_model")
                if not gemini_ocr_model:
                    raise RuntimeError("system_config 'ocr_gemini_model' is not set")
                max_parallel_pages = int(await config_repo.get_value("ocr_max_parallel_pages", "4"))
                gemini_ocr_timeout_str = await config_repo.get_value("ocr_gemini_timeout")
                gemini_ocr_timeout = float(gemini_ocr_timeout_str) if gemini_ocr_timeout_str else None
                batch_ocr_enabled_str = await config_repo.get_value("ocr_batch_enabled", "false")
                batch_ocr_enabled = batch_ocr_enabled_str.lower() in ("true", "1", "yes")
                batch_ocr_batch_size = int(await config_repo.get_value("ocr_batch_size_per_job", "50"))
```

In `process_page(page: Page)`:
```python
                    fitz_page = doc.load_page(page.page_number - 1)
                    if ocr_engine == "easyocr":
                        async with db_session.async_session_factory() as session:
                            correction_pairs = await AutoCorrectRulesRepository(session).get_active_pairs()
                        text = await ocr_page_with_easyocr(
                            fitz_page,
                            timeout=easyocr_timeout,
                            min_confidence=easyocr_min_conf,
                            header_footer_band_pct=easyocr_hf_band,
                            heading_size_ratio=easyocr_heading_ratio,
                            correction_pairs=correction_pairs,
                        )
                    else:
                        text = await ocr_page_with_gemini(
                            fitz_page, gemini_ocr_model, timeout=gemini_ocr_timeout
                        )
```

- [ ] **Step 3: Run worker tests to verify**

Run: `pytest services/worker/tests/jobs/ocr_job_test.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add services/worker/jobs/ocr_job.py services/worker/tests/jobs/ocr_job_test.py
git commit -m "feat(worker): route ocr_job through EasyOCR service with DB-driven configuration"
```

---

### Task 6: Dockerfile & Worker Packaging for Offline Deployment

**Files:**
- Modify: `services/worker/requirements.worker.txt`
- Modify: `Dockerfile.worker`

**Interfaces:**
- Ensures `easyocr` and PyTorch CPU are installed, and model weights are downloaded during container build for 100% offline runtime execution.

- [ ] **Step 1: Update `services/worker/requirements.worker.txt`**

```text
# Worker-specific dependencies
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.6.0+cpu
torchvision==0.21.0+cpu
easyocr==1.7.2
```

- [ ] **Step 2: Update `Dockerfile.worker` to bake model weights**

In `Dockerfile.worker` Builder stage or Stage 2, run model pre-caching:
```dockerfile
# Pre-download EasyOCR Uyghur model weights so worker runs completely offline
RUN python -c "import easyocr; easyocr.Reader(['ug'], gpu=False)"
```

- [ ] **Step 3: Commit**

```bash
git add services/worker/requirements.worker.txt Dockerfile.worker
git commit -m "chore(docker): package easyocr and pre-cache model weights in worker image"
```

---

## Verification Plan

### Automated Tests
1. Run backend-core unit tests:
   ```bash
   pytest packages/backend-core/tests/app/utils/ocr_structure_test.py packages/backend-core/tests/app/utils/ocr_corrections_test.py packages/backend-core/tests/app/services/easyocr_service_test.py -v
   ```
2. Run worker job unit tests:
   ```bash
   pytest services/worker/tests/jobs/ocr_job_test.py -v
   ```

### Manual Verification
1. Rebuild and restart local worker container:
   ```bash
   ./deploy/local/rebuild-and-restart.sh worker
   ```
2. Upload a test PDF book and monitor worker OCR logs:
   ```bash
   docker compose -f deploy/local/docker-compose.yml logs -f worker
   ```
3. Inspect `pages.text` and verify Markdown structure, heading tags (`#`), and TOC navigation in the reader UI at `http://localhost:30080`.
