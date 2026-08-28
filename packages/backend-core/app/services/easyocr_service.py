from __future__ import annotations

import asyncio
import io
import logging
import warnings
from concurrent.futures import ThreadPoolExecutor
from typing import List, Tuple, Optional
import pymupdf as fitz
import numpy as np
from PIL import Image, ImageEnhance

# Suppress PyTorch internal quantization and dataloader pin_memory notices on CPU
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch")
logging.getLogger("easyocr").setLevel(logging.ERROR)

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

    zoom_factors = [
        settings.ocr_page_zoom_factor,
        settings.ocr_page_zoom_factor * 1.25,
    ]
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
            readtext_future = loop.run_in_executor(
                _EXECUTOR, _sync_readtext, reader, img_bytes
            )
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

            # Check confidence
            confidences = [item[2] for item in detections if len(item) > 2]
            mean_conf = sum(confidences) / len(confidences) if confidences else 0.0

            if mean_conf < min_confidence and not _is_blank_image(img_bytes):
                raise LowConfidenceOcrError(
                    f"EasyOCR mean confidence {mean_conf:.2f} < {min_confidence}"
                )

            # Reconstruct layout using actual rendered pixmap pixel dimensions
            page_width = float(pix.width)
            page_height = float(pix.height)
            markdown = assemble_page_markdown(
                detections,
                page_width=page_width,
                page_height=page_height,
                header_footer_band_pct=header_footer_band_pct,
                heading_size_ratio=heading_size_ratio,
            )

            # Apply autocorrect
            if correction_pairs:
                markdown = apply_auto_corrections(markdown, correction_pairs)

            return markdown

        except Exception as exc:
            last_error = exc
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5)
                continue
            raise last_error

    if last_error:
        raise last_error
    return ""
