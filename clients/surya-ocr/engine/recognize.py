"""Vendored/adapted from packages/backend-core/app/services/surya_service.py
(validated on the poc/easy-ocr-v2 branch of the main kitabim-ai repo, not
present on main). Two changes from the original: no app.core.config
dependency (two local constants instead), and no `correction_pairs`
parameter (that comes from a DB table this standalone client can't reach;
Kitabim's own auto_correct_scanner already applies the same corrections
post-ingestion regardless of OCR engine)."""

from __future__ import annotations

import asyncio
import io
import logging
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, List, Optional, Tuple
import re

import fitz
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image
from surya.recognition import RecognitionPredictor

from engine.text_cleanup import clean_uyghur_text, is_degenerate_ocr_output

if TYPE_CHECKING:
    from surya.recognition.schema import PageOCRResult

logger = logging.getLogger("surya_ocr_client.engine.recognize")

# Local equivalents of packages/backend-core's OCR_MAX_RETRIES /
# OCR_PAGE_ZOOM_FACTOR env-configured settings (defaults match main's).
OCR_MAX_RETRIES = 4
OCR_PAGE_ZOOM_FACTOR = 1.5

FOOTNOTE_LABELS = frozenset({"Footnote"})
DISCARD_LABELS = frozenset({"PageHeader", "PageFooter"})


class LowConfidenceOcrError(Exception):
    """Raised when the recognizer's mean confidence falls below the
    configured threshold on a non-blank page - triggers the varied-input
    retry, same handling path as an exception from the recognizer itself."""


_recognition_predictor: Optional["RecognitionPredictor"] = None
_recognition_predictor_lock = asyncio.Lock()
_executor: Optional[ThreadPoolExecutor] = None


async def get_recognition_predictor() -> "RecognitionPredictor":
    global _recognition_predictor
    if _recognition_predictor is not None:
        return _recognition_predictor
    async with _recognition_predictor_lock:
        if _recognition_predictor is None:
            loop = asyncio.get_running_loop()
            _recognition_predictor = await loop.run_in_executor(
                None, RecognitionPredictor
            )
    return _recognition_predictor


def recognize_page(
    predictor: "RecognitionPredictor", image: "Image.Image"
) -> "PageOCRResult":
    return predictor([image], full_page=True)[0]


def _get_executor(max_workers: int) -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(
            max_workers=max(1, max_workers), thread_name_prefix="surya_ocr"
        )
    return _executor


_BLANK_PAGE_VARIANCE_THRESHOLD = 25.0


def is_page_blank(pix: "fitz.Pixmap") -> bool:
    arr = np.frombuffer(pix.samples, dtype=np.uint8)
    if arr.size == 0:
        return True
    return float(np.var(arr)) < _BLANK_PAGE_VARIANCE_THRESHOLD


_HEADING_TAG_RE = re.compile(r"^<h([1-6])\b[^>]*>", re.IGNORECASE)
_DOT_LEADER_RE = re.compile(r"[.·•∙⋅․﹒｡\-—–_]{2,}|…{2,}")
_ROW_NUMBER_RE = re.compile(r"\d{1,4}")


def _html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _format_table_row(item_text: str) -> str:
    number_match = _ROW_NUMBER_RE.search(item_text)
    if not number_match:
        return item_text.strip()
    value = number_match.group()
    title = item_text[: number_match.start()] + " " + item_text[number_match.end() :]
    title = _DOT_LEADER_RE.sub(" ", title)
    title = " ".join(title.split())
    if not title:
        return item_text.strip()
    return f"| {title} | {value} |"


def _html_rows_to_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all(["tr", "li"])
    if not items:
        text = soup.get_text(separator=" ", strip=True)
        return _format_table_row(text) if text else ""
    rows = [
        _format_table_row(item_text)
        for item in items
        if (item_text := item.get_text(separator=" ", strip=True))
    ]
    return "\n".join(rows)


def _block_html_to_markdown(html: str) -> str:
    heading_match = _HEADING_TAG_RE.match(html.strip())
    if heading_match:
        level = min(int(heading_match.group(1)), 6)
        return f"{'#' * level} {_html_to_text(html)}"
    if "<li" in html or "<tr" in html:
        return _html_rows_to_markdown(html)
    return _html_to_text(html)


def _process_page_sync(
    image: "Image.Image",
    recognition_predictor: "RecognitionPredictor",
) -> Tuple[str, float]:
    result = recognize_page(recognition_predictor, image)

    blocks: List[str] = []
    footnotes: List[str] = []
    confidences: List[float] = []

    for block in sorted(result.blocks, key=lambda b: b.reading_order):
        if block.confidence is not None:
            confidences.append(block.confidence)

        if block.skipped or block.error or block.label in DISCARD_LABELS:
            continue

        html = (block.html or "").strip()
        if not html:
            continue

        text = _block_html_to_markdown(html)
        if not text.strip():
            continue

        if block.label in FOOTNOTE_LABELS:
            footnotes.append(text)
        else:
            blocks.append(text)

    blocks.extend(footnotes)
    markdown = "\n\n".join(blocks)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return markdown, mean_confidence


async def ocr_page_with_surya(
    page: "fitz.Page",
    recognition_predictor: "RecognitionPredictor",
    timeout: float | None = None,
    *,
    max_parallel_pages: int = 1,
    min_confidence: float = 0.3,
) -> str:
    executor = _get_executor(max_parallel_pages)
    loop = asyncio.get_running_loop()

    last_exc: Exception | None = None
    for attempt in range(OCR_MAX_RETRIES):
        zoom = OCR_PAGE_ZOOM_FACTOR + (attempt * 0.5)
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            if is_page_blank(pix):
                return ""

            image = Image.open(io.BytesIO(pix.tobytes("png")))

            process_fn = partial(_process_page_sync, image, recognition_predictor)
            coro = loop.run_in_executor(executor, process_fn)
            markdown, mean_confidence = await (
                asyncio.wait_for(coro, timeout=timeout) if timeout else coro
            )

            if not markdown.strip():
                raise LowConfidenceOcrError(
                    f"No text recognized on a non-blank page (attempt {attempt + 1})"
                )

            if mean_confidence < min_confidence:
                raise LowConfidenceOcrError(
                    f"Mean OCR confidence {mean_confidence:.2f} below "
                    f"threshold {min_confidence} (attempt {attempt + 1})"
                )

            cleaned = clean_uyghur_text(markdown)
            if is_degenerate_ocr_output(cleaned):
                raise LowConfidenceOcrError(
                    f"OCR output looks like a runaway repetition/reasoning-leak "
                    f"loop ({len(cleaned)} chars, attempt {attempt + 1})"
                )
            return cleaned

        except Exception as exc:
            last_exc = exc
            if attempt < OCR_MAX_RETRIES - 1:
                logger.warning(
                    "OCR attempt failed, retrying with adjusted render: attempt=%s error=%s",
                    attempt + 1,
                    exc,
                )
                continue
            raise
    raise last_exc  # pragma: no cover
