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
import re
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from typing import Any

import fitz
import numpy as np
from bs4 import BeautifulSoup
from PIL import Image, ImageFilter

from engine.config import (
    DEFAULT_OCR_CONCURRENCY,
    DEFAULT_OCR_MAX_RETRIES,
    DEFAULT_OCR_PAGE_ZOOM_FACTOR,
    MAX_SURYA_CONCURRENCY,
    apply_surya_token_limits,
    get_configured_concurrency,
    get_configured_engine,
    get_configured_max_retries,
    get_configured_page_timeout,
    get_configured_zoom_factor,
    is_bleed_through_suppression_enabled,
    is_dot_enhancement_enabled,
)
from engine.text_cleanup import (
    add_word_spans,
    clean_uyghur_text,
    has_repeated_word_span,
    is_block_repetition_loop,
    is_degenerate_ocr_output,
    is_hallucinated_arabic_block,
    is_isolated_page_number,
)

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
OCR_PAGE_ZOOM_FACTOR = get_configured_zoom_factor(DEFAULT_OCR_PAGE_ZOOM_FACTOR)

FOOTNOTE_LABELS = frozenset({"Footnote"})
DISCARD_LABELS = frozenset({"PageHeader"})
_PHANTOM_CHECK_LABELS = frozenset({"Text", "PageFooter"})
_ROW_FORMAT_LABELS = frozenset({"TableOfContents", "Table"})
# A neighbour of a looping block is only swapped for its block-mode re-read
# when that re-read recovers this much more text (i.e. the full-page pass
# truncated it, typically because the looping block swallowed its content).
_REOCR_NEIGHBOUR_MIN_GROWTH = 1.2


class LowConfidenceOcrError(Exception):
    """Raised when the recognizer's mean confidence falls below the
    configured threshold on a non-blank page - triggers the varied-input
    retry, same handling path as an exception from the recognizer itself."""


def enhance_dots_and_contrast(image: Image.Image) -> Image.Image:
    """Enhance fine dot clarity and text contrast for Arabic/Uyghur script.

    Uses an unsharp mask filter to sharpen small diacritical dots (e.g. peh/beh,
    feh/qaf) without introducing heavy thresholding artifacts or noise amplification.
    """
    if image.mode != "RGB":
        image = image.convert("RGB")
    return image.filter(ImageFilter.UnsharpMask(radius=1.5, percent=150, threshold=3))


def get_adaptive_page_zoom(
    page: fitz.Page,
    base_zoom: float = DEFAULT_OCR_PAGE_ZOOM_FACTOR,
    min_target_width_px: float = 1500.0,
) -> float:
    """Calculate adaptive rendering zoom based on PDF page dimensions.

    Smaller books (e.g. pocketbooks < 500pt / ~147mm wide) suffer from blurry
    dots at standard 2.0-2.5x zooms because pixel density is too low for Surya
    to reliably distinguish 1 dot from 3 dots. This adapts the zoom so the page
    width reaches at least `min_target_width_px`, clamped to [2.0, 4.0].
    """
    try:
        rect = page.rect
        width = float(rect.width)
        if width > 0 and width < 500.0:
            target_zoom = min_target_width_px / width
            return max(base_zoom, min(4.0, target_zoom))
    except Exception:
        pass
    return base_zoom


_surya_predictor: Any = None
_paddle_predictor: Any = None
_predictor_lock = asyncio.Lock()
_executor: ThreadPoolExecutor | None = None


async def get_recognition_predictor(engine: str | None = None) -> Any:
    """Return the initialized OCR predictor for the requested or configured engine.

    Supported engines: 'paddleocr' (default), 'surya'.
    """
    global _surya_predictor, _paddle_predictor

    target_engine = (engine or get_configured_engine()).strip().lower()

    if target_engine == "paddleocr":
        if _paddle_predictor is not None:
            return _paddle_predictor
        async with _predictor_lock:
            if _paddle_predictor is None:
                loop = asyncio.get_running_loop()
                try:
                    from paddleocr import PPStructure

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
                except (ImportError, Exception):
                    try:
                        from paddleocr import PPStructureV3

                        _paddle_predictor = await loop.run_in_executor(
                            None,
                            partial(PPStructureV3, lang="ug"),
                        )
                    except Exception:
                        from paddleocr import PaddleOCR

                        _paddle_predictor = await loop.run_in_executor(
                            None,
                            partial(PaddleOCR, lang="ug"),
                        )
        return _paddle_predictor

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
        f"Unknown OCR engine '{target_engine}'. Expected one of: 'paddleocr', 'surya'."
    )


def recognize_page(predictor: Any, image: Image.Image) -> Any:
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


def is_page_blank(pix: fitz.Pixmap) -> bool:
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


def _list_html_to_lines(html: str) -> str:
    """Render list items / table rows one per line, text kept as printed."""
    soup = BeautifulSoup(html, "html.parser")
    items = soup.find_all(["tr", "li"])
    if not items:
        return soup.get_text(separator=" ", strip=True)
    return "\n".join(
        item_text
        for item in items
        if (item_text := item.get_text(separator=" ", strip=True))
    )


def _mixed_list_html_to_markdown(html: str, format_rows: bool) -> str:
    """Render a block containing lists/tables, keeping any paragraphs around them.

    Surya can return a whole page as one ListGroup block (prose paragraphs
    followed by a numbered list), so each top-level element is rendered in
    order instead of extracting only the list items.
    """
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    for node in soup.children:
        if isinstance(node, str):
            text = node.strip()
        elif node.name in ("ol", "ul", "table") or node.find(["li", "tr"]):
            text = (
                _html_rows_to_markdown(str(node))
                if format_rows
                else _list_html_to_lines(str(node))
            )
        else:
            for br in node.find_all("br"):
                br.replace_with("\n")
            text = "\n".join(
                line.strip() for line in node.get_text().split("\n") if line.strip()
            )
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _block_html_to_markdown(html: str, label: str | None = None) -> str:
    heading_match = _HEADING_TAG_RE.match(html.strip())
    if heading_match:
        level = min(int(heading_match.group(1)), 6)
        return f"{'#' * level} {_html_to_text(html)}"
    if "<li" in html or "<tr" in html:
        # TOC-style "| title | page |" rows only for TOC/table blocks; plain
        # lists keep their items as printed.
        format_rows = label is None or label in _ROW_FORMAT_LABELS
        return _mixed_list_html_to_markdown(html, format_rows)

    soup = BeautifulSoup(html, "html.parser")
    p_tags = soup.find_all("p")
    if len(p_tags) > 1:
        paras = []
        for p in p_tags:
            for br in p.find_all("br"):
                br.replace_with("\n")
            p_lines = [
                line.strip() for line in p.get_text().split("\n") if line.strip()
            ]
            if p_lines:
                paras.append("\n".join(p_lines))
        if paras:
            return "\n\n".join(paras)

    for br in soup.find_all("br"):
        br.replace_with("\n")
    raw_text = soup.get_text()
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    if not lines:
        return ""
    if len(lines) == 1:
        return lines[0]

    return "\n".join(lines)


def suppress_bleed_through(img: Image.Image) -> Image.Image:
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
    # For clean white / digital pages where background is already nearly pure white (>= 248.0),
    # there is no bleed-through to suppress, and aggressive white_point clipping can erode thin
    # anti-aliased font strokes (such as digits '6' and '0').
    if bg_val >= 248.0:
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


# A block is phantom bleed-through when its darkest strokes reach less than
# this fraction of the page's typical ink contrast against the paper.
_PHANTOM_RELATIVE_CONTRAST = 0.45
# Blocks whose darkest strokes are within this many luminance levels of the
# paper are treated as blank regardless of the page's ink level.
_PHANTOM_MIN_CONTRAST = 25.0


def _block_ink_contrast(
    block: Any, image_gray: np.ndarray, paper_level: float
) -> float | None:
    """Return paper_level minus the block's lowest-percentile luminance (how dark its
    darkest strokes are against the paper), or None if the block has no usable crop."""
    box = _get_block_bbox(block)
    if not box:
        return None
    try:
        bx0, bx1, by0, by1 = box
        h, w = image_gray.shape[:2]
        x0 = max(0, min(w - 1, int(bx0)))
        x1 = max(0, min(w, int(bx1)))
        y0 = max(0, min(h - 1, int(by0)))
        y1 = max(0, min(h, int(by1)))

        if x1 <= x0 or y1 <= y0:
            return None

        crop = image_gray[y0:y1, x0:x1]
        if crop.size < 50:
            return None

        # In sparse text blocks (e.g. 1-2 lines inside a large bounding box),
        # ink pixels may make up less than 2% of the crop area. A fixed 5th percentile
        # lands on the blank paper background, falsely classifying real text as bleed-through.
        # Use an adaptive percentile that scales down with crop size to sample actual stroke pixels.
        percentile_level = min(1.0, max(0.2, 50.0 / crop.size))
        return paper_level - float(np.percentile(crop, percentile_level))
    except Exception:
        return None


def _page_paper_level(image_gray: np.ndarray) -> float:
    return float(np.percentile(image_gray, 90))


def _page_ink_contrast_reference(
    blocks: list[Any], image_gray: np.ndarray, paper_level: float
) -> float:
    """Typical ink contrast on this page: the median block contrast, so a light
    (faded) print run is judged against its own ink, not against dark print."""
    contrasts = [
        c
        for b in blocks
        if (c := _block_ink_contrast(b, image_gray, paper_level)) is not None
    ]
    if contrasts:
        return float(np.median(contrasts))
    return paper_level - float(np.percentile(image_gray, 0.5))


def _is_phantom_bleed_through_block(
    block: Any,
    image_gray: np.ndarray,
    ink_contrast_reference: float | None = None,
) -> bool:
    """Return True if the block's ink is far fainter than the page's real ink.

    Thresholds adapt to the page: a heavily printed page drops faint show-through
    from the verso, while a lightly printed page keeps its (uniformly light) text.
    """
    paper_level = _page_paper_level(image_gray)
    contrast = _block_ink_contrast(block, image_gray, paper_level)
    if contrast is None:
        return False
    if ink_contrast_reference is None:
        ink_contrast_reference = paper_level - float(np.percentile(image_gray, 0.5))
    threshold = max(
        _PHANTOM_MIN_CONTRAST, _PHANTOM_RELATIVE_CONTRAST * ink_contrast_reference
    )
    return contrast < threshold


def _get_block_bbox(block: Any) -> tuple[float, float, float, float] | None:
    """Return (x0, x1, y0, y1) bounding box for block polygon or bbox attribute/dict entry."""
    if isinstance(block, dict):
        bbox = block.get("bbox")
        if bbox and len(bbox) >= 4:
            try:
                return float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3])
            except Exception:
                pass
        return None
    polygon = getattr(block, "polygon", None)
    if polygon and len(polygon) >= 2:
        try:
            xs = [p[0] for p in polygon]
            ys = [p[1] for p in polygon]
            return float(min(xs)), float(max(xs)), float(min(ys)), float(max(ys))
        except Exception:
            pass
    bbox = getattr(block, "bbox", None)
    if bbox and len(bbox) >= 4:
        try:
            return float(bbox[0]), float(bbox[2]), float(bbox[1]), float(bbox[3])
        except Exception:
            pass
    return None


def _is_vertical_marginalia_block(block: Any, img_w: float, img_h: float) -> bool:
    """Return True if block is a vertical marginalia / running side header.

    In published books, running headers (book or chapter titles, e.g. 'قۇتادغۇ بىلىك')
    are often printed vertically along the outer side margins. Because Uyghur is a
    horizontal script, text in the outer margin with a tall, narrow aspect ratio
    (height >= 1.8 * width) represents running side marginalia, not body text.
    When read horizontally by standard OCR, it produces garbled fragments or
    hallucinated headers/echoes placed at the bottom of the page.
    """
    box = _get_block_bbox(block)
    if not box or img_w <= 0 or img_h <= 0:
        return False
    x0, x1, y0, y1 = box
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return False

    if h < 1.8 * w:
        return False

    is_left_margin = (x1 / img_w) <= 0.18
    is_right_margin = (x0 / img_w) >= 0.82
    return is_left_margin or is_right_margin


def _is_single_line_verse_block(block: Any) -> bool:
    """Return True if block contains exactly one physical print line, making it
    a grouping candidate for a vertically-adjacent block (whether the group
    then turns out to be a poem stanza or a print-wrapped prose fragment).

    Only excludes blocks that are structurally NOT a single physical line:
    multi-line/list/table HTML, or a block whose text is long enough that it
    must already be a whole paragraph recognized without internal <br> (e.g.
    Surya's own reflowed output), rather than a single printed line - see
    test_process_page_sync_preserves_prose_paragraphs_as_separate_blocks.
    A grouped run of single-line blocks is always joined one-line-per-line
    (never reflowed into flowing prose) regardless of whether it turns out
    to be a poem stanza or consecutive print-wrapped prose lines - so this
    only needs to gate whether blocks are even candidates for grouping,
    not what kind of content they'll turn out to be.
    """
    html = (getattr(block, "html", "") or "").strip()
    if not html:
        return False
    if "<br" in html or "<li" in html or "<tr" in html or "<table" in html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    if len(soup.find_all("p")) > 1:
        return False
    raw = soup.get_text().strip()
    lines = [line.strip() for line in raw.split("\n") if line.strip()]
    if len(lines) != 1:
        return False

    # Verse lines (and ordinary print lines) in Uyghur books are typically
    # under 85 characters; a "single line" well past that is almost always a
    # whole paragraph Surya already reflowed internally, not one print line.
    return len(lines[0]) <= 85


def _reocr_looping_blocks(
    predictor: Any, image: Image.Image, blocks: list[Any]
) -> list[Any]:
    """Re-recognize a page in Surya block mode when a full-page block loops.

    Surya's full-page pass decodes the whole page in one autoregressive run;
    on a block whose last printed sentence runs on to the next page it can
    re-emit that line and then drift into the following block's text (e.g. a
    footnote), which then comes back truncated. It can also lose visual
    grounding at the page bottom and echo a verse or sentence already recognized
    earlier on the page into the last block or a phantom footer block.

    Surya's own fallback only fires on page-length repetition loops, so it
    never sees these shorter loops. Block mode OCRs each region's crop on its
    own and can't bleed between blocks or access text from other regions, so we
    re-read the page's existing block boxes that way and take the re-read for
    every looping block, plus any block whose re-read recovered clearly more
    text. If an echoed block was a phantom box with no real ink, block mode
    re-OCR returns empty/error and its text is dropped.
    """
    seen_page_spans: set[tuple[str, ...]] = set()
    looping: set[int] = set()

    for b in sorted(blocks, key=lambda x: getattr(x, "reading_order", 0)):
        if b.skipped or b.error or not b.html:
            continue
        text = _html_to_text(b.html)
        if not text.strip():
            continue
        if has_repeated_word_span(text, min_words=8, seen_spans=seen_page_spans):
            looping.add(id(b))
        else:
            add_word_spans(text, seen_page_spans, min_words=8)

    if not looping:
        return blocks

    from surya.layout.schema import LayoutBox, LayoutResult

    redo_targets: list[Any] = []
    layout_boxes: list[LayoutBox] = []
    for b in blocks:
        box = _get_block_bbox(b)
        if b.skipped or b.error or not b.html or box is None:
            continue
        x0, x1, y0, y1 = box
        redo_targets.append(b)
        layout_boxes.append(
            LayoutBox(
                polygon=[x0, y0, x1, y1],
                label=b.label,
                raw_label=b.label,
                position=b.reading_order,
                count=max(400, 2 * len(b.html)),
            )
        )
    if not layout_boxes:
        return blocks

    logger.info(
        "Re-OCRing page in block mode: %s looping block(s) in full-page output",
        len(looping),
    )
    w, h = image.size
    layout = LayoutResult(bboxes=layout_boxes, image_bbox=[0, 0, float(w), float(h)])
    redone = predictor([image], [layout], full_page=False)[0].blocks

    replacements: dict[int, Any] = {}
    for old, new in zip(redo_targets, redone):
        if id(old) in looping:
            # If the looping block was re-read and produced non-empty text, use it;
            # if it produced an error or empty text (e.g. phantom margin box),
            # clear its text so the hallucination is dropped.
            new_text = (
                _html_to_text(getattr(new, "html", "") or "")
                if not getattr(new, "error", False)
                else ""
            )
            if new_text.strip():
                replacements[id(old)] = new
            else:
                try:
                    new.html = ""
                except Exception:
                    pass
                try:
                    old.html = ""
                except Exception:
                    pass
                replacements[id(old)] = new
        elif not getattr(new, "error", False) and getattr(new, "html", None):
            if len(_html_to_text(new.html)) >= (
                _REOCR_NEIGHBOUR_MIN_GROWTH * len(_html_to_text(old.html))
            ):
                replacements[id(old)] = new
    return [replacements.get(id(b), b) for b in blocks]


def _format_paddleocr_regions(image: Image.Image, regions: Any) -> tuple[str, float]:
    """Parse PP-Structure regions and format into Markdown blocks and mean confidence."""
    if not regions or not isinstance(regions, list):
        return "", 0.0

    first_item = (
        regions[0] if isinstance(regions, (list, tuple)) and len(regions) > 0 else None
    )

    # Handle PPStructureV3 (LayoutParsingResultV2 or dict with parsing_res_list / overall_ocr_res)
    has_parsing = (
        isinstance(first_item, dict)
        and ("parsing_res_list" in first_item or "overall_ocr_res" in first_item)
    ) or (
        first_item is not None
        and (
            hasattr(first_item, "parsing_res_list")
            or hasattr(first_item, "overall_ocr_res")
        )
    )

    if has_parsing:
        img_w, img_h = image.size
        pp_blocks: list[str] = []
        pp_footnotes: list[str] = []
        pp_confidences: list[float] = []

        overall_ocr = (
            first_item.get("overall_ocr_res")
            if isinstance(first_item, dict)
            else getattr(first_item, "overall_ocr_res", None)
        )
        if overall_ocr:
            rec_scores = (
                overall_ocr.get("rec_scores", [])
                if isinstance(overall_ocr, dict)
                else getattr(overall_ocr, "rec_scores", [])
            )
            for s in rec_scores:
                try:
                    pp_confidences.append(float(s))
                except (ValueError, TypeError):
                    pass

        parsing_list = (
            first_item.get("parsing_res_list")
            if isinstance(first_item, dict)
            else getattr(first_item, "parsing_res_list", None)
        )

        if parsing_list:
            for item in parsing_list:
                label = getattr(item, "label", None) or (
                    item.get("label") if isinstance(item, dict) else ""
                )
                label = str(label).lower()
                bbox = getattr(item, "bbox", None) or (
                    item.get("bbox") if isinstance(item, dict) else [0, 0, 0, 0]
                )
                content = getattr(item, "content", None) or (
                    item.get("content") if isinstance(item, dict) else ""
                )
                content = str(content).strip() if content else ""

                if not content:
                    continue

                if label in ("header", "figure"):
                    continue

                block_dict = {"bbox": bbox}
                if _is_vertical_marginalia_block(
                    block_dict, float(img_w), float(img_h)
                ):
                    continue

                if label == "footer":
                    if is_isolated_page_number(content):
                        continue
                    pp_footnotes.append(content)
                    continue

                if label in ("title", "doc_title", "paragraph_title", "section_title"):
                    if not is_block_repetition_loop(
                        content
                    ) and not is_hallucinated_arabic_block(content):
                        pp_blocks.append(f"# {content}")
                    continue

                if label == "table":
                    if "<table" in content.lower():
                        table_md = _block_html_to_markdown(content, label="Table")
                    else:
                        table_md = content
                    if table_md.strip():
                        pp_blocks.append(table_md.strip())
                    continue

                if not is_block_repetition_loop(
                    content
                ) and not is_hallucinated_arabic_block(content):
                    pp_blocks.append(content)

            pp_blocks.extend(pp_footnotes)
            markdown = "\n\n".join(pp_blocks)
            mean_conf = (
                sum(pp_confidences) / len(pp_confidences) if pp_confidences else 0.0
            )
            return markdown, mean_conf

        elif overall_ocr:
            rec_texts = (
                overall_ocr.get("rec_texts", [])
                if isinstance(overall_ocr, dict)
                else getattr(overall_ocr, "rec_texts", [])
            )
            if rec_texts:
                markdown = "\n\n".join(t.strip() for t in rec_texts if t.strip())
                mean_conf = (
                    sum(pp_confidences) / len(pp_confidences) if pp_confidences else 0.0
                )
                return markdown, mean_conf

    img_w, img_h = image.size
    blocks: list[str] = []
    footnotes: list[str] = []
    confidences: list[float] = []

    for region in regions:
        if not isinstance(region, dict):
            continue

        region_type = region.get("type", "Text")
        if region_type in ("Header", "Figure"):
            continue

        if _is_vertical_marginalia_block(region, float(img_w), float(img_h)):
            continue

        res = region.get("res")
        if not res:
            continue

        if region_type == "Footer":
            footer_lines: list[str] = []
            if isinstance(res, list):
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        txt_score = item[1]
                        if isinstance(txt_score, (list, tuple)) and len(txt_score) >= 2:
                            t, s = str(txt_score[0]).strip(), float(txt_score[1])
                            if t:
                                footer_lines.append(t)
                                confidences.append(s)
            elif isinstance(res, str):
                footer_lines.append(res.strip())
            footer_text = " ".join(footer_lines).strip()
            if not footer_text or is_isolated_page_number(footer_text):
                continue
            footnotes.append(footer_text)
            continue

        if region_type == "Title":
            title_lines: list[str] = []
            if isinstance(res, list):
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        txt_score = item[1]
                        if isinstance(txt_score, (list, tuple)) and len(txt_score) >= 2:
                            t, s = str(txt_score[0]).strip(), float(txt_score[1])
                            if t:
                                title_lines.append(t)
                                confidences.append(s)
            elif isinstance(res, str):
                title_lines.append(res.strip())
            title_text = " ".join(title_lines).strip()
            if (
                title_text
                and not is_block_repetition_loop(title_text)
                and not is_hallucinated_arabic_block(title_text)
            ):
                blocks.append(f"# {title_text}")
            continue

        if region_type == "Table":
            table_md = ""
            if isinstance(res, dict) and "html" in res:
                table_md = _block_html_to_markdown(res["html"], label="Table")
            elif isinstance(res, list):
                row_lines = []
                for item in res:
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        txt_score = item[1]
                        if isinstance(txt_score, (list, tuple)) and len(txt_score) >= 2:
                            row_lines.append(str(txt_score[0]).strip())
                if row_lines:
                    table_md = "\n".join(row_lines)
            if table_md.strip():
                blocks.append(table_md.strip())
            continue

        # Text, List, etc.
        lines: list[str] = []
        if isinstance(res, list):
            for item in res:
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    txt_score = item[1]
                    if isinstance(txt_score, (list, tuple)) and len(txt_score) >= 2:
                        t, s = str(txt_score[0]).strip(), float(txt_score[1])
                        if t:
                            lines.append(t)
                            confidences.append(s)
                elif isinstance(item, dict):
                    t = str(item.get("text", "")).strip()
                    s = item.get("confidence", item.get("score"))
                    if t:
                        lines.append(t)
                        if s is not None:
                            confidences.append(float(s))
        elif isinstance(res, str):
            for line_item in res.split("\n"):
                if line_item.strip():
                    lines.append(line_item.strip())

        if lines:
            text = "\n".join(lines)
            if (
                text.strip()
                and not is_block_repetition_loop(text)
                and not is_hallucinated_arabic_block(text)
            ):
                blocks.append(text)

    blocks.extend(footnotes)
    markdown = "\n\n".join(blocks)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return markdown, mean_confidence


def _process_page_paddleocr_sync(
    image: Image.Image,
    predictor: Any,
) -> tuple[str, float]:
    """Run PaddleOCR PP-Structure layout and OCR on an image and format as Markdown."""
    if image.mode != "RGB":
        image = image.convert("RGB")
    img_arr = np.array(image)[:, :, ::-1]
    mock_ret = getattr(predictor, "_mock_return_value", None)
    if mock_ret is not None and type(mock_ret).__name__ != "_Sentinel":
        regions = predictor(img_arr)
    elif hasattr(predictor, "predict"):
        regions = predictor.predict(img_arr)
    elif callable(predictor):
        regions = predictor(img_arr)
    else:
        regions = []
    return _format_paddleocr_regions(image, regions)


def _process_page_surya_sync(
    image: Image.Image,
    recognition_predictor: Any,
    precomputed_result: Any = None,
) -> tuple[str, float]:
    result = (
        precomputed_result
        if precomputed_result is not None
        else recognize_page(recognition_predictor, image)
    )
    img_w, img_h = image.size
    non_marginalia_blocks = [
        b for b in result.blocks if not _is_vertical_marginalia_block(b, img_w, img_h)
    ]
    page_blocks = _reocr_looping_blocks(
        recognition_predictor, image, non_marginalia_blocks
    )

    footnotes: list[str] = []
    confidences: list[float] = []
    gray_arr = np.array(image.convert("L"))

    valid_blocks: list[Any] = []

    phantom_candidates = [
        b
        for b in page_blocks
        if not (b.skipped or b.error or b.label in DISCARD_LABELS)
        and b.label in _PHANTOM_CHECK_LABELS
    ]
    ink_contrast_reference = _page_ink_contrast_reference(
        phantom_candidates, gray_arr, _page_paper_level(gray_arr)
    )

    for block in sorted(page_blocks, key=lambda b: b.reading_order):
        if (
            block.skipped
            or block.error
            or block.label in DISCARD_LABELS
            or _is_vertical_marginalia_block(block, img_w, img_h)
        ):
            continue

        if block.confidence is not None:
            confidences.append(block.confidence)

        html = (block.html or "").strip()
        if not html:
            continue

        # PageFooter blocks containing only isolated page numbers or blank text are discarded;
        # footers with actual text content (dates, locations, signatures, notes) are preserved.
        if block.label == "PageFooter":
            footer_text = _html_to_text(html)
            if not footer_text or is_isolated_page_number(footer_text):
                continue

        # Filter phantom bleed-through text blocks with no dark ink
        if block.label in _PHANTOM_CHECK_LABELS:
            if _is_phantom_bleed_through_block(block, gray_arr, ink_contrast_reference):
                logger.info(
                    "Discarding phantom bleed-through block %s (no dark ink)",
                    getattr(block, "reading_order", 0),
                )
                continue

        valid_blocks.append(block)

    # Group vertically adjacent Text blocks that belong to the same poem stanza.
    # Surya frequently segments each verse line of a poem as an independent Text block.
    # Lines within the same stanza have tight line spacing (gap <= 0.45 * line_height),
    # while stanza breaks (couplet separators) have larger vertical gaps (> 0.45 * line_height).
    # Prose paragraphs must never be grouped together.
    blocks: list[str] = []
    current_group: list[Any] = []

    def flush_group() -> None:
        nonlocal current_group
        if not current_group:
            return

        if len(current_group) == 1:
            b = current_group[0]
            txt = _block_html_to_markdown(b.html, b.label)
            if (
                txt.strip()
                and not is_block_repetition_loop(txt)
                and not is_hallucinated_arabic_block(txt)
            ):
                blocks.append(txt)
        else:
            lines: list[str] = []
            for b in current_group:
                soup = BeautifulSoup(b.html, "html.parser")
                for br in soup.find_all("br"):
                    br.replace_with("\n")
                raw = soup.get_text()
                for line in raw.split("\n"):
                    line_str = line.strip()
                    if line_str:
                        lines.append(line_str)

            if lines:
                # Consolidate the group into one block, each source line kept
                # on its own line exactly as printed - never reflowed into
                # flowing prose and never split apart into separate
                # paragraphs. This keeps a poem's scattered verse-line blocks
                # together as one stanza, and equally keeps consecutive
                # print-wrapped prose lines together without a spurious
                # blank-line gap between them.
                txt = "\n".join(lines)

                if (
                    txt.strip()
                    and not is_block_repetition_loop(txt)
                    and not is_hallucinated_arabic_block(txt)
                ):
                    blocks.append(txt)

        current_group = []

    for block in valid_blocks:
        if block.label in FOOTNOTE_LABELS:
            flush_group()
            txt = _block_html_to_markdown(block.html, block.label)
            if (
                txt.strip()
                and not is_block_repetition_loop(txt)
                and not is_hallucinated_arabic_block(txt)
            ):
                footnotes.append(txt)
            continue

        if getattr(block, "label", "") != "Text":
            flush_group()
            txt = _block_html_to_markdown(block.html, block.label)
            if (
                txt.strip()
                and not is_block_repetition_loop(txt)
                and not is_hallucinated_arabic_block(txt)
            ):
                blocks.append(txt)
            continue

        box = _get_block_bbox(block)
        is_curr_verse = _is_single_line_verse_block(block)

        if not box or not current_group or not is_curr_verse:
            flush_group()
            current_group.append(block)
            continue

        prev_block = current_group[-1]
        prev_box = _get_block_bbox(prev_block)
        is_prev_verse = _is_single_line_verse_block(prev_block)

        if not prev_box or not is_prev_verse:
            flush_group()
            current_group.append(block)
            continue

        prev_x0, prev_x1, prev_y0, prev_y1 = prev_box
        curr_x0, curr_x1, curr_y0, curr_y1 = box

        overlap_x0 = max(prev_x0, curr_x0)
        overlap_x1 = min(prev_x1, curr_x1)
        overlap_w = max(0.0, overlap_x1 - overlap_x0)
        min_w = min(prev_x1 - prev_x0, curr_x1 - curr_x0)
        has_h_overlap = min_w > 0 and (overlap_w / min_w) >= 0.5

        prev_line_h = prev_y1 - prev_y0
        curr_line_h = curr_y1 - curr_y0
        est_line_h = (prev_line_h + curr_line_h) / 2.0

        gap = curr_y0 - prev_y1

        # A vertical gap within [-0.5 * h, 0.45 * h] indicates lines in the same stanza
        if (
            has_h_overlap
            and curr_y0 >= prev_y0
            and (-0.5 * est_line_h <= gap <= 0.45 * est_line_h)
        ):
            current_group.append(block)
        else:
            flush_group()
            current_group.append(block)

    flush_group()
    blocks.extend(footnotes)
    markdown = "\n\n".join(blocks)
    mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return markdown, mean_confidence


def _is_surya_context(recognition_predictor: Any) -> bool:
    try:
        from surya.recognition import RecognitionPredictor

        if isinstance(recognition_predictor, RecognitionPredictor):
            return True
    except ImportError:
        pass
    if hasattr(recognize_page, "mock_calls"):
        return True
    ret = getattr(recognition_predictor, "return_value", None)
    if isinstance(ret, list) and ret and hasattr(ret[0], "blocks"):
        return True
    if hasattr(recognition_predictor, "blocks"):
        return True
    return False


def _process_page_sync(
    image: Image.Image,
    recognition_predictor: Any,
    engine: str | None = None,
) -> tuple[str, float]:
    target_engine = (engine or get_configured_engine()).strip().lower()
    if target_engine == "surya" or _is_surya_context(recognition_predictor):
        return _process_page_surya_sync(image, recognition_predictor)

    return _process_page_paddleocr_sync(image, recognition_predictor)


async def ocr_page(
    page: fitz.Page,
    recognition_predictor: Any,
    timeout: float | None = None,
    *,
    max_parallel_pages: int = DEFAULT_MAX_PARALLEL_PAGES,
    min_confidence: float = 0.3,
    max_retries: int | None = None,
    valid_words: set[str] | None = None,
    engine: str | None = None,
) -> str:
    workers = min(max(1, max_parallel_pages), MAX_SURYA_PARALLEL_PAGES)
    executor = _get_executor(workers)
    loop = asyncio.get_running_loop()

    effective_timeout = (
        timeout if timeout is not None else get_configured_page_timeout()
    )
    total_attempts = max(1, max_retries) if max_retries is not None else OCR_MAX_RETRIES
    base_zoom = OCR_PAGE_ZOOM_FACTOR
    adaptive_zoom = get_adaptive_page_zoom(page, base_zoom)

    last_exc: Exception | None = None
    for attempt in range(total_attempts):
        zoom = adaptive_zoom + (attempt * 0.5)
        try:
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
            if is_page_blank(pix):
                return ""

            image = Image.open(io.BytesIO(pix.tobytes("png")))
            if is_bleed_through_suppression_enabled():
                image = suppress_bleed_through(image)
            if is_dot_enhancement_enabled():
                image = enhance_dots_and_contrast(image)

            if engine is not None:
                process_fn = partial(
                    _process_page_sync, image, recognition_predictor, engine=engine
                )
            else:
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
