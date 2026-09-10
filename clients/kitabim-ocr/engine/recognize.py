"""Vendored/adapted from packages/backend-core/app/services/surya_service.py
(validated on the poc/easy-ocr-v2 branch of the main kitabim-ai repo, not
present on main). Two changes from the original: no app.core.config
dependency (two local constants instead), and no `correction_pairs`
parameter (that comes from a DB table this standalone client can't reach;
Kitabim's own auto_correct_scanner already applies the same corrections
post-ingestion regardless of OCR engine).

Extended to support both standard Surya OCR and Apple Silicon MLX-optimized
Savitr OCR via a configurable engine switch."""

from __future__ import annotations

import asyncio
import io
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import fitz
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image

from engine.config import (
    DEFAULT_OCR_CONCURRENCY,
    DEFAULT_OCR_MAX_RETRIES,
    MAX_SURYA_CONCURRENCY,
    apply_surya_token_limits,
    get_configured_concurrency,
    get_configured_engine,
    get_configured_max_retries,
    get_configured_page_timeout,
    get_savitr_model_path,
    is_apple_silicon,
    is_bleed_through_suppression_enabled,
)
from engine.savitr_engine import SavitrPredictor
from engine.text_cleanup import (
    clean_uyghur_text,
    is_block_repetition_loop,
    is_degenerate_ocr_output,
    is_hallucinated_arabic_block,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("kitabim_ocr_client.engine.recognize")

# Apply sane ceiling for Surya token generation if not overridden in env
apply_surya_token_limits()

# Local equivalents of packages/backend-core's OCR_MAX_RETRIES /
# OCR_PAGE_ZOOM_FACTOR env-configured settings (poc/easy-ocr-v2 only -
# these don't exist on main). 2.5 matches the zoom bump that shipped
# alongside the EasyOCR->Surya recognition swap there (mean confidence
# ~0.75-0.78 -> ~0.97-0.98 on the same real pages, model+zoom verified
# together).
OCR_MAX_RETRIES = get_configured_max_retries(DEFAULT_OCR_MAX_RETRIES)
OCR_PAGE_ZOOM_FACTOR = 2.5

FOOTNOTE_LABELS = frozenset({"Footnote"})
DISCARD_LABELS = frozenset({"PageHeader", "PageFooter"})


class LowConfidenceOcrError(Exception):
    """Raised when the recognizer's mean confidence falls below the
    configured threshold on a non-blank page - triggers the varied-input
    retry, same handling path as an exception from the recognizer itself."""


_surya_predictor: Any = None
_savitr_predictor: Any = None
_predictor_lock = asyncio.Lock()
_executor: Optional[ThreadPoolExecutor] = None
_savitr_executor: Optional[ThreadPoolExecutor] = None


def _get_savitr_executor() -> ThreadPoolExecutor:
    global _savitr_executor
    if _savitr_executor is None:
        _savitr_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="savitr_mlx"
        )
    return _savitr_executor


async def get_recognition_predictor(engine: str | None = None) -> Any:
    """Return the initialized OCR predictor for the requested or configured engine.

    Supported engines: 'surya' (default) and 'savitr' (MLX on Apple Silicon).
    """
    global _surya_predictor, _savitr_predictor

    target_engine = (engine or get_configured_engine()).strip().lower()

    if target_engine == "savitr":
        if _savitr_predictor is not None:
            return _savitr_predictor
        async with _predictor_lock:
            if _savitr_predictor is None:
                if not is_apple_silicon():
                    raise RuntimeError(
                        "Savitr OCR is optimized for Apple Silicon (macOS arm64). "
                        "Please use engine 'surya' on this machine."
                    )
                from engine.savitr_engine import SavitrPredictor

                model_path = get_savitr_model_path()
                loop = asyncio.get_running_loop()
                savitr_exec = _get_savitr_executor()
                _savitr_predictor = await loop.run_in_executor(
                    savitr_exec, partial(SavitrPredictor, model_path=model_path)
                )
        return _savitr_predictor

    if target_engine == "surya":
        if _surya_predictor is not None:
            return _surya_predictor
        async with _predictor_lock:
            if _surya_predictor is None:
                from surya.recognition import RecognitionPredictor

                loop = asyncio.get_running_loop()
                _surya_predictor = await loop.run_in_executor(
                    None, RecognitionPredictor
                )
        return _surya_predictor

    raise ValueError(
        f"Unknown OCR engine '{target_engine}'. Expected 'surya' or 'savitr'."
    )


def recognize_page(predictor: Any, image: "Image.Image") -> Any:
    if isinstance(predictor, SavitrPredictor):
        return predictor.recognize_image(image)
    return predictor([image], full_page=True)[0]


DEFAULT_MAX_PARALLEL_PAGES = DEFAULT_OCR_CONCURRENCY
MAX_SURYA_PARALLEL_PAGES = MAX_SURYA_CONCURRENCY


def _get_executor(max_workers: int | None = None) -> ThreadPoolExecutor:
    global _executor
    workers = (
        max_workers
        if max_workers is not None
        else get_configured_concurrency(max_limit=MAX_SURYA_PARALLEL_PAGES)
    )
    target_workers = min(max(1, workers), MAX_SURYA_PARALLEL_PAGES)
    if _executor is None or getattr(_executor, "_max_workers", 0) != target_workers:
        if _executor is not None:
            _executor.shutdown(wait=False)
        _executor = ThreadPoolExecutor(
            max_workers=target_workers, thread_name_prefix="ocr"
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


_BLOCK_TAGS = frozenset(
    {
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "p",
        "table",
        "ul",
        "ol",
        "div",
        "blockquote",
        "aside",
        "section",
        "article",
        "header",
        "footer",
    }
)


def _process_savitr_html(html: str) -> str:
    html = html.strip()
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")

    blocks: List[str] = []

    def _extract_blocks(node: Any) -> None:
        if isinstance(node, str):
            text = node.strip()
            if text:
                blocks.append(text)
            return

        tag_name = getattr(node, "name", None)
        if not tag_name:
            return

        if tag_name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag_name[1])
            text = node.get_text(separator=" ", strip=True)
            if text:
                blocks.append(f"{'#' * level} {text}")
            return

        if tag_name in ("table", "ul", "ol"):
            text = _block_html_to_markdown(str(node))
            if text.strip():
                blocks.append(text.strip())
            return

        has_block_child = any(
            hasattr(child, "name") and child.name in _BLOCK_TAGS
            for child in getattr(node, "children", [])
        )
        if has_block_child:
            for child in node.children:
                _extract_blocks(child)
        else:
            text = node.get_text(separator=" ", strip=True)
            if text:
                blocks.append(text)

    root = soup.body if soup.body else soup
    for child in root.children:
        _extract_blocks(child)

    if not blocks:
        return _html_to_text(html)
    return "\n\n".join(blocks)


def suppress_bleed_through(img: "Image.Image") -> "Image.Image":
    """Normalize paper background and suppress faint reverse-side bleed-through/show-through.

    In scanned physical book pages, printed text on the verso side shines through as
    faint, low-contrast markings near the paper background level. Real printed ink
    strokes are significantly darker (< 120-140 luminance).
    By mapping intensities in the faint bleed-through range to clean white (255)
    and stretching ink contrast, ghost text is eliminated before OCR recognition.
    """
    if img.mode not in ("L", "RGB", "RGBA"):
        img = img.convert("RGB")

    arr = np.array(img)
    if arr.size == 0:
        return img

    if arr.ndim == 3:
        gray = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
    else:
        gray = arr.astype(np.float32)

    bg_val = float(np.percentile(gray, 90))
    if bg_val < 140.0:
        return img

    white_point = max(175.0, min(235.0, bg_val - 38.0))
    black_point = 40.0

    scale = 255.0 / (white_point - black_point)
    if arr.ndim == 3 and arr.shape[2] == 4:
        rgb = arr[:, :, :3].astype(np.float32)
        adjusted_rgb = np.clip((rgb - black_point) * scale, 0, 255).astype(np.uint8)
        adjusted = np.dstack((adjusted_rgb, arr[:, :, 3]))
    else:
        adjusted = np.clip(
            (arr.astype(np.float32) - black_point) * scale, 0, 255
        ).astype(np.uint8)

    return Image.fromarray(adjusted)


def _is_phantom_bleed_through_block(
    block: Any,
    image_gray: np.ndarray,
) -> bool:
    """Return True if the block contains no real dark ink strokes (faint ghost/paper)."""
    polygon = getattr(block, "polygon", None)
    if not polygon or len(polygon) < 3:
        return False
    try:
        xs = [p[0] for p in polygon]
        ys = [p[1] for p in polygon]
        h, w = image_gray.shape[:2]
        x0 = max(0, min(w - 1, int(min(xs))))
        x1 = max(0, min(w, int(max(xs))))
        y0 = max(0, min(h - 1, int(min(ys))))
        y1 = max(0, min(h, int(max(ys))))

        if x1 <= x0 or y1 <= y0:
            return False

        crop = image_gray[y0:y1, x0:x1]
        if crop.size < 50:
            return False

        p5 = float(np.percentile(crop, 5))
        # Real ink has dark pixels (typically < 120, well below 155).
        # Bleed-through or blank regions without real ink have p5 > 155.
        if p5 > 155.0:
            return True
    except Exception:
        pass
    return False


def _process_page_sync(
    image: "Image.Image",
    recognition_predictor: Any,
) -> Tuple[str, float]:
    if isinstance(recognition_predictor, SavitrPredictor):
        html_or_text, mean_confidence = recognition_predictor.recognize_image(image)
        markdown = _process_savitr_html(html_or_text)
        return markdown, mean_confidence

    result = recognize_page(recognition_predictor, image)

    blocks: List[str] = []
    footnotes: List[str] = []
    confidences: List[float] = []
    gray_arr = np.array(image.convert("L"))

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

        # Filter phantom bleed-through text blocks with no dark ink
        if block.label not in FOOTNOTE_LABELS and getattr(block, "label", "") == "Text":
            if _is_phantom_bleed_through_block(block, gray_arr):
                logger.info(
                    "Discarding phantom bleed-through block %s (no dark ink)",
                    getattr(block, "reading_order", 0),
                )
                continue

        # Filter runaway repetition loops or hallucinated Arabic in block text
        if is_block_repetition_loop(text):
            logger.info(
                "Discarding degenerate repetition loop block %s",
                getattr(block, "reading_order", 0),
            )
            continue

        if is_hallucinated_arabic_block(text):
            logger.info(
                "Discarding hallucinated Arabic block %s",
                getattr(block, "reading_order", 0),
            )
            continue

        if block.label in FOOTNOTE_LABELS:
            footnotes.append(text)
        else:
            blocks.append(text)

    blocks.extend(footnotes)
    markdown = "\n\n".join(blocks)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return markdown, mean_confidence


async def ocr_page(
    page: "fitz.Page",
    recognition_predictor: Any,
    timeout: float | None = None,
    *,
    max_parallel_pages: int = DEFAULT_MAX_PARALLEL_PAGES,
    min_confidence: float = 0.3,
    max_retries: int | None = None,
) -> str:
    if isinstance(recognition_predictor, SavitrPredictor):
        executor = _get_savitr_executor()
    else:
        workers = min(max(1, max_parallel_pages), MAX_SURYA_PARALLEL_PAGES)
        executor = _get_executor(workers)
    loop = asyncio.get_running_loop()

    effective_timeout = (
        timeout if timeout is not None else get_configured_page_timeout()
    )
    total_attempts = max(1, max_retries) if max_retries is not None else OCR_MAX_RETRIES

    last_exc: Exception | None = None
    for attempt in range(total_attempts):
        zoom = OCR_PAGE_ZOOM_FACTOR + (attempt * 0.5)
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            if is_page_blank(pix):
                return ""

            image = Image.open(io.BytesIO(pix.tobytes("png")))
            if is_bleed_through_suppression_enabled():
                image = suppress_bleed_through(image)

            process_fn = partial(_process_page_sync, image, recognition_predictor)
            coro = loop.run_in_executor(executor, process_fn)
            try:
                markdown, mean_confidence = await (
                    asyncio.wait_for(coro, timeout=effective_timeout)
                    if effective_timeout
                    else coro
                )
            except (TimeoutError, asyncio.TimeoutError) as err:
                logger.warning(
                    "OCR attempt timed out after %ss (attempt %s/%s)",
                    effective_timeout,
                    attempt + 1,
                    total_attempts,
                )
                raise TimeoutError(
                    f"OCR timed out after {effective_timeout:.0f}s (attempt {attempt + 1})"
                ) from err

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
            if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
                raise
            if attempt < total_attempts - 1:
                logger.warning(
                    "OCR attempt failed, retrying with adjusted render: attempt=%s/%s error=%s",
                    attempt + 1,
                    total_attempts,
                    exc,
                )
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("OCR failed with no attempts")  # pragma: no cover
