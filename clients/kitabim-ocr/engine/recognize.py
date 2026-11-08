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
import threading
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
    is_hallucinated_ghost_text,
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
_PHANTOM_CHECK_LABELS = frozenset(
    {"Text", "PageFooter", "SectionHeader", "Title", "Caption", "Footnote", "List-item"}
)
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
_predictor_lock = asyncio.Lock()
_toc_line_detector: Any = None
_toc_detector_lock = threading.Lock()
_executor: ThreadPoolExecutor | None = None


async def get_recognition_predictor(engine: str | None = None) -> Any:
    """Return the initialized OCR predictor for the requested or configured engine.

    Supported engines: 'surya' (default).
    """
    global _surya_predictor

    target_engine = (engine or get_configured_engine()).strip().lower()

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

    raise ValueError(f"Unknown OCR engine '{target_engine}'. Expected 'surya'.")


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


_SURYA_COMPACT_TOKEN_RE = re.compile(r"<\|(?:\d{1,4}|box|[A-Za-z-]+)\|>")
_DOT_LEADER_RE = re.compile(r"[.·•∙⋅․﹒｡\-—–_]{2,}|…{2,}")
_ROW_NUMBER_RE = re.compile(r"[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}")
_LEADING_DOT_LEADER_RE = re.compile(r"^\s*(?:[.·•∙⋅․﹒｡\-—–_]{2,}|…{2,})")
_TRAILING_DOT_LEADER_RE = re.compile(r"(?:[.·•∙⋅․﹒｡\-—–_]{2,}|…{2,})\s*$")
_TOC_DOT_RUN_RE = re.compile(r"[.·•∙⋅․﹒｡]{3,}|…{2,}")
_TOC_DOT_TARGET_OR_TOKEN_RE = re.compile(
    r"(?:[.·•∙⋅․﹒｡]{3,}|[_\-—–]{4,}|…{2,})\s*"
    r"(?:<\|(?:\d{1,4}|box|[A-Za-z-]+)\|>[\s.]*)*"
    r"(?:[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}|<\|\d{1,4}\|>)"
    r"|(?:^|\n)\s*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*"
    r"(?:[.·•∙⋅․﹒｡]{3,}|[_\-—–]{4,}|…{2,})"
)
_TOC_LINE_HAS_TARGET_RE = re.compile(
    r"(?:[.·•∙⋅․﹒｡\-—–_]{2,}|…+)\s*"
    r"(?:<\|(?:\d{1,4}|box|[A-Za-z-]+)\|>[\s.]*)*"
    r"[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*$"
    r"|^\s*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*(?:[.·•∙⋅․﹒｡\-—–_]{2,}|…+)"
)
_TOC_INLINE_SPLIT_RE = re.compile(
    r"((?:[.·•∙⋅․﹒｡]{3,}|…{2,})\s*(?:<\|(?:\d{1,4}|box|[A-Za-z-]+)\|>[\s.]*)*"
    r"[0-9\u0660-\u0669\u06F0-\u06F9]{1,4})\s+(?=\S)"
)
_TOC_PIPE_ROW_RE = re.compile(
    r"^\|\s*[^|]+?\s*\|\s*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*\|?$"
)
_NEW_TOC_ITEM_START_RE = re.compile(
    r"^(?:[0-9\u0660-\u0669\u06F0-\u06F9]{1,3}\s*[.)،\-]|\([0-9\u0660-\u0669\u06F0-\u06F9]{1,3}\)"
    r"|(?:بىرىنچى|ئىككىنچى|ئۈچىنچى|تۆتىنچى|بەشىنچى|ئالتىنچى|يەتتىنچى|سەككىزىنچى|توققۇزىنچى|ئونىنچى)\s+(?:باب|قىسىم|بۆلەك))"
)
_PAGE_NUM_DIGIT_MAP = str.maketrans(
    {
        "O": "0",
        "o": "0",
        "I": "1",
        "l": "1",
        "|": "1",
        "Z": "2",
        "z": "2",
        "S": "5",
        "s": "5",
        "B": "8",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
    }
)


def _html_to_text(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(separator=" ", strip=True)


def _format_table_row(item_text: str) -> str:
    item_text = _SURYA_COMPACT_TOKEN_RE.sub(" ", item_text)
    matches = list(_ROW_NUMBER_RE.finditer(item_text))
    if not matches:
        return item_text.strip()
    if len(matches) == 1:
        number_match = matches[0]
    else:
        first, last = matches[0], matches[-1]
        at_trailing_edge = not item_text[last.end() :].strip(" .·•-|")
        at_leading_edge = not item_text[: first.start()].strip(" .·•-|")
        if at_trailing_edge and _TRAILING_DOT_LEADER_RE.search(
            item_text[: last.start()]
        ):
            number_match = last
        elif at_leading_edge and _LEADING_DOT_LEADER_RE.search(
            item_text[first.end() :]
        ):
            number_match = first
        elif at_trailing_edge:
            number_match = last
        else:
            number_match = first
    value = number_match.group()
    title = item_text[: number_match.start()] + " " + item_text[number_match.end() :]
    title = _DOT_LEADER_RE.sub(" ", title)
    title = " ".join(title.split())
    title = re.sub(r"^[.·•∙⋅․﹒｡…_\s]+|[.·•∙⋅․﹒｡…_\s]+$", "", title)
    if not title:
        return item_text.strip()
    return f"| {title} | {value} |"


def _join_toc_wrapped_lines(parts: list[str]) -> str:
    joined = ""
    for raw in parts:
        part = raw.strip()
        if not part:
            continue
        if not joined:
            joined = part
        elif re.search(r"[\u0600-\u06FF][-\u2010\u2011_]$", joined):
            joined = joined[:-1] + part
        else:
            joined = f"{joined} {part}"
    return joined


def _split_inline_toc_entries(line: str) -> list[str]:
    marked = _TOC_INLINE_SPLIT_RE.sub(r"\1\n", line)
    return [seg.strip() for seg in marked.split("\n") if seg.strip()]


def _is_munderije_heading_line(line: str) -> bool:
    stripped = re.sub(r"^[#\s\-—–:«»\"'()]+|[\s\-—–:«»\"'().]+$", "", line)
    return "مۇندەرىجە" in stripped and len(stripped) <= 35


def _format_toc_lines_to_markdown(
    lines: list[str], *, promote_munderije_heading: bool = False
) -> str:
    expanded: list[str] = []
    for raw_line in lines:
        cleaned = _SURYA_COMPACT_TOKEN_RE.sub(" ", raw_line).strip()
        if not cleaned:
            continue
        expanded.extend(_split_inline_toc_entries(cleaned))

    sections: list[str] = []
    table_rows: list[str] = []
    pending: list[str] = []

    def flush_table() -> None:
        if table_rows:
            sections.append("\n".join(table_rows))
            table_rows.clear()

    def flush_pending() -> None:
        if pending:
            flush_table()
            sections.append(_join_toc_wrapped_lines(pending))
            pending.clear()

    for line in expanded:
        if line.startswith("#") or (
            _is_munderije_heading_line(line)
            and not _TOC_LINE_HAS_TARGET_RE.search(line)
        ):
            flush_pending()
            flush_table()
            if line.startswith("#") or not promote_munderije_heading:
                sections.append(line)
            else:
                sections.append(f"## {line}")
            continue

        if _TOC_PIPE_ROW_RE.match(line):
            flush_pending()
            table_rows.append(line)
            continue

        if _TOC_LINE_HAS_TARGET_RE.search(line):
            if (
                len(pending) == 1
                and len(pending[0]) <= 35
                and _NEW_TOC_ITEM_START_RE.match(line)
            ):
                flush_pending()
            full_entry = _join_toc_wrapped_lines([*pending, line])
            pending.clear()
            table_rows.append(_format_table_row(full_entry))
        else:
            if (
                len(pending) == 1
                and len(pending[0]) <= 35
                and _NEW_TOC_ITEM_START_RE.match(line)
            ):
                flush_pending()
            pending.append(line)

    flush_table()
    if pending:
        sections.append(_join_toc_wrapped_lines(pending))

    return "\n\n".join(s for s in sections if s.strip())


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
    """Render a block containing headings/lists/tables, keeping paragraphs around them.

    Surya can return a whole page or section as one block (e.g. prose paragraphs
    followed by a numbered list, or a heading followed by body paragraphs), so
    each top-level element is rendered in order instead of collapsing them.
    """
    soup = BeautifulSoup(html, "html.parser")
    parts: list[str] = []
    for node in soup.children:
        if isinstance(node, str):
            text = node.strip()
        elif node.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = min(int(node.name[1]), 6)
            heading_text = _html_to_text(str(node))
            text = f"{'#' * level} {heading_text}" if heading_text else ""
        elif node.name in ("ol", "ul", "table") or node.find(["li", "tr"]):
            text = (
                _html_rows_to_markdown(str(node))
                if format_rows
                else _list_html_to_lines(str(node))
            )
        else:
            for br in node.find_all("br"):
                br.replace_with("\n")
            node_lines = [
                line.strip() for line in node.get_text().split("\n") if line.strip()
            ]
            if format_rows and any(
                _TOC_LINE_HAS_TARGET_RE.search(line) for line in node_lines
            ):
                text = _format_toc_lines_to_markdown(
                    node_lines, promote_munderije_heading=False
                )
            else:
                text = "\n".join(node_lines)
        if text:
            parts.append(text)
    return "\n\n".join(parts)


def _block_html_to_markdown(html: str, label: str | None = None) -> str:
    stripped = html.strip()
    if not stripped:
        return ""

    soup = BeautifulSoup(stripped, "html.parser")
    root: Any = soup
    top_tags = [n for n in root.children if getattr(n, "name", None) is not None]
    top_texts = [n.strip() for n in root.children if isinstance(n, str) and n.strip()]
    if len(top_tags) == 1 and not top_texts and top_tags[0].name == "div":
        root = top_tags[0]
        top_tags = [n for n in root.children if getattr(n, "name", None) is not None]
        top_texts = [
            n.strip() for n in root.children if isinstance(n, str) and n.strip()
        ]

    if (
        len(top_tags) == 1
        and not top_texts
        and top_tags[0].name in ("h1", "h2", "h3", "h4", "h5", "h6")
    ):
        level = min(int(top_tags[0].name[1]), 6)
        heading_text = _html_to_text(str(top_tags[0]))
        return f"{'#' * level} {heading_text}" if heading_text else ""

    if (
        "<li" in stripped
        or "<tr" in stripped
        or any(t.name in ("h1", "h2", "h3", "h4", "h5", "h6") for t in top_tags)
    ):
        # TOC-style "| title | page |" rows only for TOC/table blocks; plain
        # lists keep their items as printed.
        format_rows = label is None or label in _ROW_FORMAT_LABELS
        inner_html = (
            "".join(str(c) for c in root.children) if root is not soup else stripped
        )
        return _mixed_list_html_to_markdown(inner_html, format_rows)

    p_tags = root.find_all("p")
    if len(p_tags) > 1:
        paras = []
        all_p_lines: list[str] = []
        for p in p_tags:
            for br in p.find_all("br"):
                br.replace_with("\n")
            p_lines = [
                line.strip() for line in p.get_text().split("\n") if line.strip()
            ]
            if p_lines:
                paras.append("\n".join(p_lines))
                all_p_lines.extend(p_lines)
        if paras:
            if label == "TableOfContents":
                return _format_toc_lines_to_markdown(
                    all_p_lines, promote_munderije_heading=False
                )
            return "\n\n".join(paras)

    for br in soup.find_all("br"):
        br.replace_with("\n")
    raw_text = soup.get_text()
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    if not lines:
        return ""
    if label == "TableOfContents":
        return _format_toc_lines_to_markdown(lines, promote_munderije_heading=False)
    if len(lines) == 1:
        return lines[0]

    return "\n".join(lines)


def suppress_bleed_through(img: Image.Image) -> Image.Image:
    """Auto-detect page scan profile and adaptively suppress bleed-through or enhance faded ink.

    Detects three scan regimes from the page's background level (`bg_val`) and the
    10th-percentile luminance of foreground ink pixels (`ink_p10`):
    1. Clean digital/white page (`bg_val >= 248`, `faint_bleed_fraction < 0.014`,
       `ink_p10 < 70`): returned untouched.
    2. Light / faded scan (`ink_p10 >= 70`): foreground ink itself is mid-gray
       (e.g. 90-215 luminance) while verso show-through sits near the paper level
       (>= 226). Avoids speckle-mask erosion that would erase real light strokes,
       clips only faint near-paper show-through, and stretches faded ink to dark contrast.
    3. Dark-ink scan with bleed-through (`ink_p10 < 70`): front-side ink has a solid
       dark core while reverse-side bleed-through appears as lighter markings/speckles;
       applies speckle-mask filtering and background clipping to remove verso text.
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

    # Measure foreground ink darkness from pixels in the foreground ink range (< 160),
    # excluding background-adjacent verso bleed-through (>= 160).
    ink_pixels = gray[gray < 160.0]
    ink_p10 = float(np.percentile(ink_pixels, 10)) if ink_pixels.size > 0 else 0.0

    # Light / faded scan regime: foreground ink core is mid-gray (>= 70) rather than black.
    # Stretch faded strokes toward black and clip only very faint near-paper show-through
    # without eroding thin gray letter loops/dots via speckle_mask.
    if ink_p10 >= 70.0:
        white_point = max(ink_p10 + 60.0, min(226.0, bg_val - 26.0))
        black_point = max(35.0, min(95.0, ink_p10 - 20.0))
        scale = 255.0 / max(1.0, white_point - black_point)
        if arr.ndim == 3 and arr.shape[2] == 4:
            rgb = arr[:, :, :3].astype(np.float32)
            adjusted_rgb = np.clip((rgb - black_point) * scale, 0, 255).astype(np.uint8)
            return Image.fromarray(np.dstack((adjusted_rgb, arr[:, :, 3])))
        return Image.fromarray(
            np.clip((arr.astype(np.float32) - black_point) * scale, 0, 255).astype(
                np.uint8
            )
        )

    # Check for faint bleed-through / show-through in the background-adjacent range.
    # On clean digital/white pages, almost all pixels are pure background with only a tiny
    # border of anti-aliased edge pixels (< 1.2%). Scanned pages with verso show-through have
    # a larger pixel population in this faint range (typically 1.8%-6% depending on margin width).
    faint_bleed_fraction = float(
        np.mean((gray >= 160.0) & (gray <= max(160.0, bg_val - 12.0)))
    )
    if bg_val >= 248.0 and faint_bleed_fraction < 0.014:
        return img

    ink_shift = max(0.0, ink_p10 - 30.0)
    white_point = max(
        175.0,
        min(200.0 + ink_shift * 0.6, bg_val - max(28.0, 50.0 - ink_shift * 0.5)),
    )
    black_point = 40.0

    # Scanned bleed-through often contains thin 1-pixel contour speckles with dark
    # raw values (70-190) surrounded by white paper, whereas real front-side strokes
    # and diacritical dots have a solid dark core (min_blur < speckle_threshold).
    # Scale blur radius with image width so 1500px+ PDF renders match 1000px crops.
    blur_radius = max(1.0, min(2.0, gray.shape[1] / 1000.0))
    gray_u8 = Image.fromarray(np.clip(gray, 0, 255).astype(np.uint8))
    b3_img = gray_u8.filter(ImageFilter.BoxBlur(blur_radius))
    blur3 = np.array(b3_img, dtype=np.float32)
    min_blur3 = np.array(b3_img.filter(ImageFilter.MinFilter(3)), dtype=np.float32)
    speckle_threshold = max(115.0, ink_p10 + 75.0)
    speckle_mask = min_blur3 >= speckle_threshold

    scale = 255.0 / (white_point - black_point)
    if arr.ndim == 3 and arr.shape[2] == 4:
        rgb = arr[:, :, :3].astype(np.float32)
        effective_rgb = np.where(
            speckle_mask[:, :, None], np.maximum(rgb, blur3[:, :, None]), rgb
        )
        adjusted_rgb = np.clip((effective_rgb - black_point) * scale, 0, 255).astype(
            np.uint8
        )
        adjusted = np.dstack((adjusted_rgb, arr[:, :, 3]))
    elif arr.ndim == 3:
        rgb = arr.astype(np.float32)
        effective_rgb = np.where(
            speckle_mask[:, :, None], np.maximum(rgb, blur3[:, :, None]), rgb
        )
        adjusted = np.clip((effective_rgb - black_point) * scale, 0, 255).astype(
            np.uint8
        )
    else:
        effective_gray = np.where(
            speckle_mask,
            np.maximum(arr.astype(np.float32), blur3),
            arr.astype(np.float32),
        )
        adjusted = np.clip((effective_gray - black_point) * scale, 0, 255).astype(
            np.uint8
        )

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

        # Inset crop boundaries slightly to avoid sampling stray dark ink from
        # adjacent text blocks whose ascenders/descenders graze the bounding box edges.
        bh, bw = crop.shape[:2]
        pad_y = min(6, int(bh * 0.05)) if bh >= 20 else 0
        pad_x = min(6, int(bw * 0.03)) if bw >= 30 else 0
        inner_crop = (
            crop[pad_y : bh - pad_y, pad_x : bw - pad_x]
            if (bh > 2 * pad_y and bw > 2 * pad_x)
            else crop
        )

        percentile_level = min(1.0, max(0.5, 50.0 / inner_crop.size))
        return paper_level - float(np.percentile(inner_crop, percentile_level))
    except Exception:
        return None


def _page_paper_level(image_gray: np.ndarray) -> float:
    return float(np.percentile(image_gray, 90))


def _page_ink_contrast_reference(
    blocks: list[Any], image_gray: np.ndarray, paper_level: float
) -> float:
    """Typical ink contrast on this page: the 75th-percentile block contrast, so a
    light (faded) print run is judged against its own ink while sparse pages with
    multiple bleed-through blocks still anchor to real front-side ink."""
    contrasts = [
        c
        for b in blocks
        if (c := _block_ink_contrast(b, image_gray, paper_level)) is not None
    ]
    if contrasts:
        return float(np.percentile(contrasts, 75))
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
    """Return (x0, x1, y0, y1) bounding box for block polygon or bbox attribute."""
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
    horizontal script, text in the outer margin that spans multiple stacked characters
    (height >= 2.5 * width and >= 8% of page height) represents running side marginalia,
    whereas a single short horizontal RTL word on a wide right margin is only one print
    line tall (~2%-4% of page height) and must be preserved.
    """
    box = _get_block_bbox(block)
    if not box or img_w <= 0 or img_h <= 0:
        return False
    x0, x1, y0, y1 = box
    w = x1 - x0
    h = y1 - y0
    if w <= 0 or h <= 0:
        return False

    if h < 2.5 * w or (h / img_h) < 0.08:
        return False

    is_left_margin = (x1 / img_w) <= 0.15
    is_right_margin = (x0 / img_w) >= 0.85
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
    intra_looping: set[int] = set()

    for b in sorted(blocks, key=lambda x: getattr(x, "reading_order", 0)):
        if b.skipped or b.error or not b.html:
            continue
        text = _html_to_text(b.html)
        if not text.strip():
            continue
        if has_repeated_word_span(text, min_words=8):
            looping.add(id(b))
            intra_looping.add(id(b))
        elif has_repeated_word_span(text, min_words=8, seen_spans=seen_page_spans):
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
            # If crop-mode failed with an internal error on a cross-block match
            # (e.g. a real repeated chorus/refrain stanza with no intra-block loop),
            # preserve the original recognition rather than wiping real content.
            if getattr(new, "error", False) and id(old) not in intra_looping:
                continue
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
                replacements[id(old)] = new
        elif not getattr(new, "error", False) and getattr(new, "html", None):
            if len(_html_to_text(new.html)) >= (
                _REOCR_NEIGHBOUR_MIN_GROWTH * len(_html_to_text(old.html))
            ):
                replacements[id(old)] = new
    return [replacements.get(id(b), b) for b in blocks]


def _get_toc_line_detector() -> Any:
    global _toc_line_detector
    with _toc_detector_lock:
        if _toc_line_detector is None:
            from surya.detection import DetectionPredictor

            try:
                _toc_line_detector = DetectionPredictor()
            except Exception:
                _toc_line_detector = DetectionPredictor.local()
    return _toc_line_detector


def _extract_block_lines(html: str) -> list[str]:
    # Protect Surya compact tokens (<|635|>) before BeautifulSoup parses HTML,
    # otherwise html.parser strips '<|...|>' as an unknown HTML tag.
    safe_html = _SURYA_COMPACT_TOKEN_RE.sub(" __SURYA_TOK__ ", html or "")
    soup = BeautifulSoup(safe_html, "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    return [
        line.replace("__SURYA_TOK__", "<|0|>").strip()
        for line in soup.get_text().split("\n")
        if line.strip()
    ]


def _extract_page_num_from_crop_text(txt: str) -> str | None:
    cleaned = re.sub(r"[\s.·•∙⋅․﹒｡…\-—–_()\[\]{}:]+", "", txt.strip())
    if not cleaned:
        return None
    mapped = cleaned.translate(_PAGE_NUM_DIGIT_MAP)
    if re.fullmatch(r"\d{1,4}", mapped):
        return mapped
    match = re.search(r"\d{1,4}", txt.translate(_PAGE_NUM_DIGIT_MAP))
    return match.group(0) if match else None


def _tall_ink_mask_1d(crop_gray: np.ndarray, ink_thresh: float) -> np.ndarray:
    h, w = crop_gray.shape
    if h < 6 or w < 2:
        return np.zeros(w, dtype=bool)
    ink = crop_gray < ink_thresh
    ink3 = ink.copy()
    if w >= 3:
        ink3[:, 1:-1] = ink[:, :-2] | ink[:, 1:-1] | ink[:, 2:]
    min_span = max(8, int(round(0.30 * h)))
    min_pixels = max(3, int(round(0.14 * h)))
    tall = np.zeros(w, dtype=bool)
    for x in range(w):
        ys = np.flatnonzero(ink3[:, x])
        if ys.size >= min_pixels and (int(ys[-1]) - int(ys[0]) + 1) >= min_span:
            tall[x] = True
    return tall


def _is_unformatted_toc_page(content_blocks: list[Any]) -> bool:
    if not content_blocks:
        return False
    all_lines: list[str] = []
    has_unformatted_block = False
    for b in content_blocks:
        html = (b.html or "").strip()
        if not html:
            continue
        if b.label in _ROW_FORMAT_LABELS and ("<li" in html or "<tr" in html):
            if _SURYA_COMPACT_TOKEN_RE.search(html):
                has_unformatted_block = True
        else:
            has_unformatted_block = True
        all_lines.extend(_extract_block_lines(html))

    if not all_lines or not has_unformatted_block:
        return False

    joined = "\n".join(all_lines)
    dot_targets = len(_TOC_DOT_TARGET_OR_TOKEN_RE.findall(joined))
    long_dot_lines = sum(
        1 for line in all_lines if re.search(r"[.·•∙⋅․﹒｡]{6,}|…{3,}", line)
    )
    has_munderije = any(_is_munderije_heading_line(line) for line in all_lines)
    if has_munderije and (dot_targets >= 1 or long_dot_lines >= 1):
        return True
    return dot_targets >= 3 or (dot_targets >= 1 and long_dot_lines >= 3)


def _needs_toc_line_reocr(blocks: list[Any]) -> bool:
    if not _is_unformatted_toc_page(blocks):
        return False
    for b in blocks:
        html = (b.html or "").strip()
        if not html or getattr(b, "skipped", False) or getattr(b, "error", False):
            continue
        if _SURYA_COMPACT_TOKEN_RE.search(html):
            return True
        for line in _extract_block_lines(html):
            if len(_TOC_DOT_RUN_RE.findall(line)) >= 2:
                return True
            # Dot leader with no recognized page number means full-page decoding
            # dropped or truncated the margin page number after the leader run.
            if re.search(
                r"[.·•∙⋅․﹒｡]{4,}|…{2,}", line
            ) and not _TOC_LINE_HAS_TARGET_RE.search(line):
                return True
    return False


def _format_toc_blocks_to_markdown(content_blocks: list[Any]) -> str:
    lines: list[str] = []
    for b in content_blocks:
        rendered = _block_html_to_markdown(b.html, b.label)
        if not rendered.strip():
            continue
        for line in rendered.split("\n"):
            if line.strip():
                lines.append(line.strip())
    return _format_toc_lines_to_markdown(lines, promote_munderije_heading=True)


def _reocr_toc_page_lines(
    image: Image.Image,
    recognition_predictor: Any,
    all_page_blocks: list[Any],
    valid_blocks: list[Any],
    gray_arr: np.ndarray,
) -> str | None:
    try:
        from surya.layout.schema import LayoutBox, LayoutResult

        detector = _get_toc_line_detector()
        det_res = detector([image])
        det_boxes = det_res[0].bboxes if det_res else []
    except Exception as exc:
        logger.warning(
            "Line-level ToC detection unavailable, using text fallback: %s", exc
        )
        return None

    if not det_boxes or len(det_boxes) < 2:
        return None

    w, h = image.size
    paper = float(np.percentile(gray_arr, 90))
    ink_pixels = gray_arr[gray_arr < max(40.0, paper - 35.0)]
    ink_ref = paper - float(np.percentile(ink_pixels, 20)) if ink_pixels.size else 80.0
    ink_thresh = paper - max(30.0, 0.25 * ink_ref)

    valid_ids = {id(b) for b in valid_blocks}
    valid_bboxes: list[tuple[float, float, float, float]] = []
    discard_bboxes: list[tuple[float, float, float, float]] = []
    for b in all_page_blocks:
        bb = _get_block_bbox(b)
        if not bb:
            continue
        bx0, bx1, by0, by1 = bb
        if id(b) in valid_ids and b.label not in FOOTNOTE_LABELS:
            valid_bboxes.append((bx0, by0, bx1, by1))
        else:
            discard_bboxes.append((bx0, by0, bx1, by1))

    min_valid_y = min((b[1] for b in valid_bboxes), default=0.0)
    max_valid_y = max((b[3] for b in valid_bboxes), default=float(h))

    filtered: list[list[float]] = []
    for db in det_boxes:
        x0, y0, x1, y1 = [float(v) for v in db.bbox]
        bw, bh = x1 - x0, y1 - y0
        if bw < 8 or bh < 8:
            continue
        cx, cy = 0.5 * (x0 + x1), 0.5 * (y0 + y1)
        if any(
            dx0 - 10 <= cx <= dx1 + 10 and dy0 - 10 <= cy <= dy1 + 10
            for dx0, dy0, dx1, dy1 in discard_bboxes
        ):
            continue
        if valid_bboxes and (
            y0 > max_valid_y + 2.0 * bh or y1 < min_valid_y - 2.0 * bh
        ):
            continue
        filtered.append([x0, y0, x1, y1])

    if len(filtered) < 2:
        return None

    filtered.sort(key=lambda b: (0.5 * (b[1] + b[3]), b[0]))
    rows: list[list[list[float]]] = []
    for box in filtered:
        if not rows:
            rows.append([box])
            continue
        prev_row = rows[-1]
        ry0 = min(b[1] for b in prev_row)
        ry1 = max(b[3] for b in prev_row)
        ov = min(ry1, box[3]) - max(ry0, box[1])
        min_h = min(ry1 - ry0, box[3] - box[1])
        rcy = 0.5 * (ry0 + ry1)
        bcy = 0.5 * (box[1] + box[3])
        if min_h > 0 and (ov / min_h >= 0.40 or abs(bcy - rcy) <= 0.45 * min_h):
            prev_row.append(box)
        else:
            rows.append([box])

    if len(rows) >= 3:
        last_row, prev_row = rows[-1], rows[-2]
        last_w = max(b[2] for b in last_row) - min(b[0] for b in last_row)
        last_h = max(b[3] for b in last_row) - min(b[1] for b in last_row)
        gap_y = min(b[1] for b in last_row) - max(b[3] for b in prev_row)
        if last_w < 0.08 * w and gap_y > 2.2 * last_h:
            rows.pop()

    wide_rows = [
        (min(b[0] for b in r), max(b[2] for b in r))
        for r in rows
        if (max(b[2] for b in r) - min(b[0] for b in r)) >= 0.35 * w
    ]
    col_left = min((x0 for x0, _ in wide_rows), default=0.1 * w)
    col_right = max((x1 for _, x1 in wide_rows), default=0.9 * w)
    col_w = max(1.0, col_right - col_left)
    max_num_col_x1 = col_left + max(70.0, 0.085 * w)

    layout_boxes: list[Any] = []
    row_specs: list[tuple[int | None, int | None, list[float] | None]] = []
    pad_x = max(8.0, round(0.008 * w))
    title_pad_x = max(14.0, round(0.012 * w))
    pad_y = max(6.0, round(0.003 * h))

    for r in rows:
        r_sorted = sorted(r, key=lambda b: b[0])
        ry0 = float(max(0, round(min(b[1] for b in r_sorted) - pad_y)))
        ry1 = float(min(h, round(max(b[3] for b in r_sorted) + pad_y)))
        raw_y0 = int(max(0, round(min(b[1] for b in r_sorted))))
        raw_y1 = int(min(h, round(max(b[3] for b in r_sorted))))

        num_bbox: list[float] | None = None
        title_bbox: list[float] | None = None

        if (
            len(r_sorted) >= 2
            and r_sorted[0][2] <= max_num_col_x1 + 25
            and (r_sorted[0][2] - r_sorted[0][0]) <= 0.12 * w
        ):
            nb = r_sorted[0]
            num_bbox = [
                max(0.0, nb[0] - pad_x),
                ry0,
                min(float(w), nb[2] + pad_x),
                ry1,
            ]
            tb_x0 = min(b[0] for b in r_sorted[1:])
            tb_x1 = max(b[2] for b in r_sorted[1:])
            title_bbox = [
                max(float(nb[2] + 4.0), tb_x0 - title_pad_x),
                ry0,
                min(float(w), tb_x1 + title_pad_x),
                ry1,
            ]
        else:
            rx0 = min(b[0] for b in r_sorted)
            rx1 = max(b[2] for b in r_sorted)
            split_done = False
            if (rx1 - rx0) >= 0.40 * w and rx0 <= max_num_col_x1:
                rcrop = gray_arr[raw_y0:raw_y1, int(rx0) : int(rx1)]
                tall = _tall_ink_mask_1d(rcrop, ink_thresh)
                tall_idx = np.flatnonzero(tall)
                if tall_idx.size >= 4:
                    diffs = np.diff(tall_idx)
                    min_gap = max(85, int(0.08 * w))
                    gap_positions = np.flatnonzero(diffs >= min_gap)
                    if gap_positions.size > 0:
                        g = int(gap_positions[0])
                        left_end_rel = int(tall_idx[g])
                        right_start_rel = int(tall_idx[g + 1])
                        if rx0 + left_end_rel <= max_num_col_x1 + 30:
                            num_bbox = [
                                max(0.0, rx0 + int(tall_idx[0]) - pad_x),
                                ry0,
                                min(float(w), rx0 + left_end_rel + pad_x),
                                ry1,
                            ]
                            safe_title_x0 = max(
                                rx0 + left_end_rel + 12.0,
                                rx0 + right_start_rel - max(36.0, 2.5 * title_pad_x),
                            )
                            title_bbox = [
                                max(0.0, safe_title_x0),
                                ry0,
                                min(float(w), rx1 + title_pad_x),
                                ry1,
                            ]
                            split_done = True

            if not split_done:
                title_bbox = [
                    max(0.0, rx0 - title_pad_x),
                    ry0,
                    min(float(w), rx1 + title_pad_x),
                    ry1,
                ]
                search_x0 = int(max(0, round(col_left - 18)))
                search_x1 = int(min(round(rx0 - 4), round(max_num_col_x1)))
                if search_x1 - search_x0 >= 10:
                    lcrop = gray_arr[raw_y0:raw_y1, search_x0:search_x1]
                    ltall = _tall_ink_mask_1d(lcrop, ink_thresh)
                    ltall_idx = np.flatnonzero(ltall)
                    if ltall_idx.size >= 2:
                        num_bbox = [
                            max(0.0, float(search_x0 + int(ltall_idx[0])) - pad_x),
                            ry0,
                            min(
                                float(w),
                                float(search_x0 + int(ltall_idx[-1]) + 1) + pad_x,
                            ),
                            ry1,
                        ]

        t_idx: int | None = None
        n_idx: int | None = None
        if title_bbox is not None:
            t_idx = len(layout_boxes)
            layout_boxes.append(
                LayoutBox(
                    polygon=title_bbox,
                    label="Text",
                    raw_label="Text",
                    position=t_idx,
                    count=220,
                )
            )
        if num_bbox is not None:
            n_idx = len(layout_boxes)
            layout_boxes.append(
                LayoutBox(
                    polygon=num_bbox,
                    label="Text",
                    raw_label="Text",
                    position=n_idx,
                    count=24,
                )
            )
        row_specs.append((t_idx, n_idx, title_bbox))

    if not layout_boxes:
        return None

    logger.info(
        "Re-OCRing ToC page line-by-line (%s physical rows, %s crops)",
        len(row_specs),
        len(layout_boxes),
    )
    layout = LayoutResult(
        bboxes=layout_boxes, image_bbox=[0.0, 0.0, float(w), float(h)]
    )
    rec_blocks = recognition_predictor([image], [layout], full_page=False)[0].blocks

    out_sections: list[str] = []
    table_rows: list[str] = []
    pending_title_lines: list[str] = []

    def flush_table() -> None:
        if table_rows:
            out_sections.append("\n".join(table_rows))
            table_rows.clear()

    def flush_pending() -> None:
        if pending_title_lines:
            flush_table()
            out_sections.append(_join_toc_wrapped_lines(pending_title_lines))
            pending_title_lines.clear()

    for t_idx, n_idx, t_bb in row_specs:
        t_txt = ""
        if t_idx is not None and not getattr(rec_blocks[t_idx], "error", False):
            t_txt = _html_to_text(rec_blocks[t_idx].html or "")
        t_txt = _SURYA_COMPACT_TOKEN_RE.sub(" ", t_txt)
        t_txt = " ".join(t_txt.split())

        n_val: str | None = None
        if n_idx is not None and not getattr(rec_blocks[n_idx], "error", False):
            n_raw = _html_to_text(rec_blocks[n_idx].html or "")
            n_val = _extract_page_num_from_crop_text(n_raw)

        if n_val is None and t_txt:
            m_trail = re.search(
                r"(?:[.·•∙⋅․﹒｡…\-—–_]{2,})\s*([0-9\u0660-\u0669\u06F0-\u06F9]{1,4})\s*$",
                t_txt,
            )
            if m_trail:
                n_val = m_trail.group(1)
                t_txt = t_txt[: m_trail.start()].strip()
            else:
                m_lead = re.match(
                    r"^\s*([0-9\u0660-\u0669\u06F0-\u06F9]{1,4})\s*(?:[.·•∙⋅․﹒｡…\-—–_]{2,})",
                    t_txt,
                )
                if m_lead:
                    n_val = m_lead.group(1)
                    t_txt = t_txt[m_lead.end() :].strip()

        t_txt = re.sub(
            r"^\s*(?:[.·•∙⋅․﹒｡…_]{2,})\s*|\s*(?:[.·•∙⋅․﹒｡…_]{2,})\s*$",
            "",
            t_txt,
        ).strip()

        if not t_txt and not n_val:
            continue

        if n_val is None and t_bb is not None:
            tw = t_bb[2] - t_bb[0]
            left_margin = t_bb[0] - col_left
            right_margin = col_right - t_bb[2]
            is_centered = (
                tw < 0.55 * col_w
                and left_margin > 0.14 * col_w
                and right_margin > 0.14 * col_w
            )
            if _is_munderije_heading_line(t_txt):
                flush_pending()
                flush_table()
                out_sections.append(f"## {t_txt.lstrip('#').strip()}")
                continue
            if is_centered and not pending_title_lines:
                flush_table()
                out_sections.append(f"### {t_txt.lstrip('#').strip()}")
                continue

        if n_val is not None:
            if (
                len(pending_title_lines) == 1
                and len(pending_title_lines[0]) <= 35
                and _NEW_TOC_ITEM_START_RE.match(t_txt)
            ):
                flush_pending()
            full_title = _join_toc_wrapped_lines(
                [*pending_title_lines, *([t_txt] if t_txt else [])]
            )
            pending_title_lines.clear()
            if full_title:
                table_rows.append(_format_table_row(f"{full_title} ..... {n_val}"))
        else:
            if (
                len(pending_title_lines) == 1
                and len(pending_title_lines[0]) <= 35
                and _NEW_TOC_ITEM_START_RE.match(t_txt)
            ):
                flush_pending()
            pending_title_lines.append(t_txt)

    flush_table()
    if pending_title_lines:
        out_sections.append(_join_toc_wrapped_lines(pending_title_lines))

    formatted = "\n\n".join(s for s in out_sections if s.strip())
    return formatted if formatted.strip() else None


def _process_page_sync(
    image: Image.Image,
    recognition_predictor: Any,
) -> tuple[str, float]:
    result = recognize_page(recognition_predictor, image)
    img_w, img_h = image.size
    non_marginalia_blocks = [
        b for b in result.blocks if not _is_vertical_marginalia_block(b, img_w, img_h)
    ]
    page_blocks = (
        non_marginalia_blocks
        if _needs_toc_line_reocr(non_marginalia_blocks)
        else _reocr_looping_blocks(recognition_predictor, image, non_marginalia_blocks)
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

    content_blocks = [b for b in valid_blocks if b.label not in FOOTNOTE_LABELS]
    if _is_unformatted_toc_page(content_blocks):
        toc_markdown: str | None = None
        if _needs_toc_line_reocr(content_blocks):
            toc_markdown = _reocr_toc_page_lines(
                image,
                recognition_predictor,
                result.blocks,
                valid_blocks,
                gray_arr,
            )
        if not toc_markdown:
            toc_markdown = _format_toc_blocks_to_markdown(content_blocks)
        for block in valid_blocks:
            if block.label in FOOTNOTE_LABELS:
                ft = _block_html_to_markdown(block.html, block.label)
                if (
                    ft.strip()
                    and not is_block_repetition_loop(ft)
                    and not is_hallucinated_arabic_block(ft)
                    and not is_hallucinated_ghost_text(ft)
                ):
                    footnotes.append(ft)
        toc_parts = [p for p in (toc_markdown, *footnotes) if p and p.strip()]
        mean_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        return "\n\n".join(toc_parts), mean_confidence

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
                and not is_hallucinated_ghost_text(txt)
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
                    and not is_hallucinated_ghost_text(txt)
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
                and not is_hallucinated_ghost_text(txt)
            ):
                footnotes.append(txt)
            continue

        if getattr(block, "label", "") != "Text":
            flush_group()
            txt = _block_html_to_markdown(block.html, block.label)
            is_table_like = block.label in _ROW_FORMAT_LABELS
            if (
                txt.strip()
                and not is_block_repetition_loop(txt)
                and not is_hallucinated_arabic_block(txt)
                and (is_table_like or not is_hallucinated_ghost_text(txt))
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


async def ocr_page(
    page: fitz.Page,
    recognition_predictor: Any,
    timeout: float | None = None,
    *,
    max_parallel_pages: int = DEFAULT_MAX_PARALLEL_PAGES,
    min_confidence: float = 0.3,
    max_retries: int | None = None,
    valid_words: set[str] | None = None,
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
