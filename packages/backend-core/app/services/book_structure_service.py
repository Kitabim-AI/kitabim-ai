"""Deterministic Book Structure Analysis Service (`Book.structure_milestone`).

Implements:
- Stage 1: Piecewise-monotonic + ToC-anchored `Page.content_page_number` solver
  (preserving `content_page_number_manual == True` overrides).
- Stage 2: Deterministic two-tier (`chapter` -> `work`) `book_sections` extraction
  with ToC reconciliation, header-driven fallback, and `synthetic_body` fallback.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
import logging
import re
from typing import Any, List, Optional, Sequence, Union

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
    BOOK_MILESTONE_PARTIAL_FAILURE,
)
from app.db.models import Book
from app.db.repositories.book_sections_repository import BookSectionsRepository
from app.db.repositories.pages_repository import PagesRepository
from app.utils.text import (
    _OCR_MARKER_RE,
    clean_uyghur_text,
    extract_standalone_page_number,
    is_colophon_entry_title,
    is_colophon_page,
    is_isolated_page_number,
    is_metadata_or_key_value_block,
    is_poem_block,
    is_title_cover_page,
    is_toc_page,
    normalize_digits,
    normalize_section_title,
    normalize_uyghur_chars,
    parse_footnote_line,
    parse_toc_entries,
)

logger = logging.getLogger(__name__)

# Uyghur structural chapter/division headings (Tier 1)
_UYGHUR_ORDINAL_PREFIX_RE = (
    r"(?:"
    r"(?:(?:ئون|يىگىرمە|ئوتتۇز|قىرىق|ئەللىك|ئاتمىش|يەتمىش|سەكسەن|توقسان|يۈز)\s+)?"
    r"(?:بىرىنچى|ئىككىنچى|ئۈچىنچى|تۆتىنچى|بەشىنچى|ئالتىنچى|يەتتىنچى|سەككىزىنچى|توققۇزىنچى)"
    r"|"
    r"(?:ئونىنچى|يىگىرمىنچى|ئوتتۇزىنچى|قىرىقىنچى|ئەللىكىنچى|ئاتمىشىنچى|يەتمىشىنچى|سەكسىنىنچى|توقسىنىنچى|يۈزىنچى)"
    r"|"
    r"\d+\s*-\s*"
    r")"
)
_STRUCTURAL_PART_RE = re.compile(
    rf"""^\s*(?:#{{1,3}}\s*)?(?:
        (?:[0-9\u0660-\u0669\u06F0-\u06F9IVXLCDM]+\s*[-–—.]*\s*)?(?:قىسىم|بۆلۈم)\b
        |
        {_UYGHUR_ORDINAL_PREFIX_RE}\s*(?:قىسىم|بۆلۈم)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_STRUCTURAL_CHAPTER_ONLY_RE = re.compile(
    rf"""^\s*(?:#{{1,3}}\s*)?(?:
        (?:[0-9\u0660-\u0669\u06F0-\u06F9IVXLCDM]+\s*[-–—.]*\s*)?(?:باب|پەسىل)\b
        |
        {_UYGHUR_ORDINAL_PREFIX_RE}\s*(?:باب|پەسىل)\b
    )""",
    re.IGNORECASE | re.VERBOSE,
)
_STRUCTURAL_CHAPTER_RE = re.compile(
    rf"""^\s*(?:#{{1,3}}\s*)?(?:
        (?:[0-9\u0660-\u0669\u06F0-\u06F9IVXLCDM]+\s*[-–—.]*\s*)?(?:باب|قىسىم|بۆلۈم|پەسىل)\b
        |
        {_UYGHUR_ORDINAL_PREFIX_RE}\s*(?:باب|قىسىم|بۆلۈم|پەسىل)\b
        |
        (?:مۇقەددىمە|خاتىمە|كىرىش\s+سۆز|سۆز\s+بېشى|ئاخىرقى\s+سۆز|ئاپتوردىن|تۈزگۈچىدىن|نەشرىياتتىن)\s*$
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Noise patterns that must never be promoted to headings
_DIVIDER_NOISE_RE = re.compile(r"^\s*(?:[*•·\-—–=~_※✦✧❖◆◇▪▫×xX]\s*){2,}\s*$")
_HTML_COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$")
_INLINE_TOC_ENTRY_RE = re.compile(
    r"^(?:[-*•]|\d+[.)])\s+.*[.\s]\d{1,4}\s*$"
    r"|^(?:[-*•]|\d+[.)])\s*\d{1,4}\b"
    r"|.*[.·•∙⋅…]{3,}\s*[\(\[]?\d{1,4}[\)\]]?\s*$"
    r"|^\|\s*.+\s*\|\s*[\(\[]?[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}[\)\]]?\s*\|?\s*$"
)
_GENERIC_SUBSECTION_RUBRICS = frozenset(
    {
        "تەرجىمىسى",
        "تەپسىرى",
        "مۇھىم نۇقتىلىرى",
        "مۇھىم نۇقتىلار",
        "نازىل بولۇش سەۋەبى",
        "سەۋەبى نۇزۇل",
        "ئىزاھات",
        "ئىزاھاتلار",
        "لۇغەت",
        "سۆزلۈك",
        "ئەسكەرتىش",
        "مەشىق",
        "تاپشۇرۇق",
        "قىسقىچە مەزمۇنى",
        "پايدىلانغان مەنبەلەر",
        "پايدىلانغان ئەدەبىياتلار",
        "بۇ ئايەتنىڭ ئالدىنقى ئايەتلەر بىلەن بولغان مۇناسىۋىتى",
    }
)
_POETIC_FORM_TITLES = frozenset(
    {
        "غەزەل",
        "مۇخەممەس",
        "مۇسەددەس",
        "مۇستەزاد",
        "رۇبائىي",
        "تۇيۇق",
        "قوشماق",
        "مەسنەۋى",
        "قەسىدە",
        "شېئىر",
        "ناخشا",
        "داستان",
    }
)
_STANDALONE_YEAR_OR_DATE_RE = re.compile(
    r"""^\s*(?:#{1,6}\s*)?(?:
        (?:1[0-9]{3}|20[0-2][0-9])\s*(?:-\s*يىل(?:ى)?.*)?
        |
        [\u0600-\u06FF\w\s،,()-]{0,35}\b(?:1[89][0-9]{2}|20[0-2][0-9])\s*-\s*يىل(?:ى)?[\u0600-\u06FF\w\s،,.\-()0-9]*
        |
        [\u0600-\u06FF\w\s،,()-]{1,35}\s*[-—–]\s*(?:1[89][0-9]{2}|20[0-2][0-9])
    )\s*$""",
    re.VERBOSE,
)
_BRACKET_META_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:\([^()\n]{1,45}\)|\[[^\[\]\n]{1,45}\])\s*$"
)
_PUBLISHER_OR_COLOPHON_LINE_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:.*?\bنەشرىياتى|ISBN\b|书号|定价|印张|字数).*$",
    re.IGNORECASE,
)
_MARKDOWN_HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")


@dataclass(frozen=True)
class PageBlock:
    """Typed structural block within a single physical page."""

    block_index: int
    kind: str  # 'heading' | 'prose' | 'verse' | 'table' | 'footnote' | 'toc' | 'meta_noise'
    raw_text: str
    normalized_text: str
    heading_level: int = 0  # 1 = chapter/H1, 2 = work/H2+


def is_structural_chapter_title(title: str) -> bool:
    """Return True if `title` matches a Tier-1 structural chapter/section marker."""
    if not title:
        return False
    cleaned = normalize_digits(normalize_uyghur_chars(title)).strip()
    if cleaned.endswith((".", "۔", "؛")) or re.search(r"[\.۔؟!]\s+\S", cleaned):
        return False
    return bool(_STRUCTURAL_CHAPTER_RE.match(cleaned))


def is_part_division_title(title: str) -> bool:
    """Return True if `title` is a book-part / division marker (`قىسىم` or `بۆلۈم`)."""
    if not title:
        return False
    cleaned = normalize_digits(normalize_uyghur_chars(title)).strip()
    if cleaned.endswith((".", "۔", "؛")) or re.search(r"[\.۔؟!]\s+\S", cleaned):
        return False
    return bool(_STRUCTURAL_PART_RE.match(cleaned))


def is_chapter_section_title(title: str) -> bool:
    """Return True if `title` is a chapter / section marker (`باب` or `پەسىل`)."""
    if not title:
        return False
    cleaned = normalize_digits(normalize_uyghur_chars(title)).strip()
    if cleaned.endswith((".", "۔", "؛")) or re.search(r"[\.۔؟!]\s+\S", cleaned):
        return False
    return bool(_STRUCTURAL_CHAPTER_ONLY_RE.match(cleaned))


def _looks_like_inline_toc_entries(lines: Sequence[str]) -> bool:
    clean = [ln.strip() for ln in lines if ln.strip()]
    if not clean:
        return False
    matches = sum(1 for ln in clean if _INLINE_TOC_ENTRY_RE.match(ln))
    return matches / len(clean) >= 0.5


def _is_heading_noise(
    text: str, repeated_running_headers: Optional[set[str]] = None
) -> bool:
    """Return True if a candidate heading is actually a divider, date/location sign-off,
    isolated page number, bracketed stage note, publisher/colophon line, or repeated running header."""
    stripped = re.sub(r"^\s*#{1,6}\s*", "", text or "").strip()
    if not stripped:
        return True
    if is_isolated_page_number(stripped):
        return True
    if _DIVIDER_NOISE_RE.match(stripped) or _HTML_COMMENT_RE.match(stripped):
        return True
    ascii_stripped = normalize_digits(stripped)
    if _STANDALONE_YEAR_OR_DATE_RE.match(ascii_stripped):
        return True
    if _BRACKET_META_RE.match(stripped):
        return True
    if _PUBLISHER_OR_COLOPHON_LINE_RE.match(stripped) or is_colophon_entry_title(
        stripped
    ):
        return True
    norm = normalize_section_title(stripped)
    if not norm:
        return True
    if repeated_running_headers and norm in repeated_running_headers:
        return True
    return False


def _split_raw_chunks_preserving_headings_and_footnotes(text: str) -> List[str]:
    """Split page text on blank lines and also isolate standalone markdown headings
    and footnote definition lines so each receives its own `block_index`."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    units: List[str] = []

    for para in paragraphs:
        lines = [ln.rstrip() for ln in para.split("\n") if ln.strip()]
        if not lines:
            continue

        current_lines: List[str] = []
        for ln in lines:
            stripped = ln.strip()
            is_md_heading = bool(_MARKDOWN_HEADING_RE.match(stripped))
            is_struct_heading = len(stripped) <= 90 and is_structural_chapter_title(
                stripped
            )
            is_fn = parse_footnote_line(stripped) is not None

            if is_md_heading or is_struct_heading or is_fn:
                if current_lines:
                    units.append("\n".join(current_lines))
                    current_lines = []
                units.append(stripped)
            else:
                current_lines.append(ln)

        if current_lines:
            units.append("\n".join(current_lines))

    return units


def parse_page_blocks(
    text: str,
    *,
    is_toc: bool = False,
    repeated_running_headers: Optional[set[str]] = None,
) -> List[PageBlock]:
    """Parse a page's text into indexed `PageBlock` units with explicit `kind`."""
    if not text or not text.strip():
        return []

    normalized_page = normalize_uyghur_chars(text)
    if is_toc:
        return [
            PageBlock(
                block_index=0,
                kind="toc",
                raw_text=normalized_page.strip(),
                normalized_text=normalize_section_title(normalized_page),
                heading_level=0,
            )
        ]

    units = _split_raw_chunks_preserving_headings_and_footnotes(normalized_page)
    blocks: List[PageBlock] = []
    skipping_inline_toc = False

    for unit_idx, unit in enumerate(units):
        stripped = unit.strip()
        if not stripped:
            continue

        idx = len(blocks)
        is_last_unit = unit_idx == len(units) - 1

        # 1. Explicit OCR header/footer markers, HTML comments, isolated page numbers, or dividers -> meta_noise
        if (
            stripped.startswith(("[Header]", "[Footer]"))
            or _HTML_COMMENT_RE.match(stripped)
            or is_isolated_page_number(stripped)
            or _DIVIDER_NOISE_RE.match(stripped)
        ):
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="meta_noise",
                    raw_text=stripped,
                    normalized_text="",
                )
            )
            continue

        # Strip mid-line glued [Header]/[Footer] suffixes and inline HTML comments
        cleaned_unit_lines: List[str] = []
        for raw_ln in stripped.split("\n"):
            no_marker = _OCR_MARKER_RE.sub("", raw_ln).rstrip()
            ln_s = no_marker.strip()
            if (
                ln_s
                and not _HTML_COMMENT_RE.match(ln_s)
                and not _DIVIDER_NOISE_RE.match(ln_s)
            ):
                cleaned_unit_lines.append(no_marker)
        if not cleaned_unit_lines:
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="meta_noise",
                    raw_text=stripped,
                    normalized_text="",
                )
            )
            continue

        stripped = "\n".join(cleaned_unit_lines).strip()
        lines = [ln.strip() for ln in cleaned_unit_lines if ln.strip()]
        if not lines:
            continue

        # 1b. Inline ToC heading ("مۇندەرىجە") and immediately following ToC entry blocks
        if len(lines) == 1 and normalize_section_title(lines[0]) == "مۇندەرىجە":
            skipping_inline_toc = True
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="toc",
                    raw_text=stripped,
                    normalized_text="مۇندەرىجە",
                )
            )
            continue

        if skipping_inline_toc:
            if _looks_like_inline_toc_entries(lines):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="toc",
                        raw_text=stripped,
                        normalized_text=normalize_section_title(stripped),
                    )
                )
                continue
            skipping_inline_toc = False

        # 2. Multi-line colophon / publishing key-value block -> meta_noise
        if len(lines) >= 2 and is_metadata_or_key_value_block(lines):
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="meta_noise",
                    raw_text=stripped,
                    normalized_text="",
                )
            )
            continue

        # 3. Footnote definition line -> footnote
        if len(lines) == 1 and parse_footnote_line(lines[0]) is not None:
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="footnote",
                    raw_text=stripped,
                    normalized_text=normalize_section_title(stripped),
                )
            )
            continue

        # 4. Pipe table -> table
        if len(lines) >= 2 and sum(1 for ln in lines if ln.startswith("|")) >= 2:
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="table",
                    raw_text=stripped,
                    normalized_text=normalize_section_title(stripped),
                )
            )
            continue

        # 5. Markdown heading (# / ## / ###) or single-line structural heading
        md_match = _MARKDOWN_HEADING_RE.match(stripped) if len(lines) == 1 else None
        if md_match:
            hashes, heading_body = md_match.groups()
            if _is_heading_noise(heading_body, repeated_running_headers):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="meta_noise",
                        raw_text=stripped,
                        normalized_text="",
                    )
                )
                continue
            # Colon-ending introducers ("تەپسىرنى كۆرۈپ چىققۇچىلار:", "ئىزاھات:") or
            # long punctuated sentences accidentally prefixed with # -> prose
            body_after_num = re.sub(
                r"^\s*[0-9\u0660-\u0669\u06F0-\u06F9IVXLCDM]+\s*\.\s*",
                "",
                heading_body,
            )
            if (
                len(heading_body) > 110
                or heading_body.rstrip().endswith((":", "："))
                or re.search(r"[\.؟!]\s+\S", body_after_num)
            ):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="prose",
                        raw_text=heading_body.strip(),
                        normalized_text=normalize_section_title(heading_body),
                    )
                )
                continue

            level = (
                1
                if (len(hashes) == 1 or is_structural_chapter_title(heading_body))
                else 2
            )
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="heading",
                    raw_text=stripped,
                    normalized_text=normalize_section_title(heading_body),
                    heading_level=level,
                )
            )
            continue

        if len(lines) == 1:
            line = lines[0]
            if _is_heading_noise(line, repeated_running_headers):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="meta_noise",
                        raw_text=stripped,
                        normalized_text="",
                    )
                )
                continue
            if len(line) <= 90 and is_structural_chapter_title(line):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="heading",
                        raw_text=stripped,
                        normalized_text=normalize_section_title(line),
                        heading_level=1,
                    )
                )
                continue
            # Short standalone unpunctuated line (e.g. poem or story title without # prefix).
            # Exclude dialogue attributions ('A: ...', '**A:** ...'), mid-line clauses
            # with commas/semicolons/colons, and trailing bottom-of-page incomplete prose
            # sentences that wrap onto the next page.
            if (
                2 <= len(line) <= 65
                and len(line.split()) <= 8
                and not (is_last_unit and len(units) >= 2)
                and not line.endswith(
                    (".", "۔", "؟", "!", ":", "：", "؛", "،", ",", "—", "-")
                )
                and not line.startswith(("-", "—", "–", "«", '"', "…", "."))
                and not re.search(r"[\.؟!،,؛:;：]\s+\S", line)
            ):
                blocks.append(
                    PageBlock(
                        block_index=idx,
                        kind="heading",
                        raw_text=stripped,
                        normalized_text=normalize_section_title(line),
                        heading_level=2,
                    )
                )
                continue

        # 6. Poetic verse stanza vs. prose paragraph
        if is_poem_block(lines):
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="verse",
                    raw_text=stripped,
                    normalized_text=normalize_section_title(stripped),
                )
            )
        else:
            cleaned_prose = clean_uyghur_text(stripped) or stripped
            blocks.append(
                PageBlock(
                    block_index=idx,
                    kind="prose",
                    raw_text=cleaned_prose,
                    normalized_text=normalize_section_title(cleaned_prose),
                )
            )

    return blocks


def format_section_hierarchy_title(
    title: Optional[str],
    section_type: Optional[str] = None,
    parent_title: Optional[str] = None,
    parent_section_type: Optional[str] = None,
) -> Optional[str]:
    """Format a `BookSection` title with optional parent prefix (`Parent › Child`),
    returning `None` for non-topical container types (`front_matter`, `synthetic_body`)."""
    if section_type in ("front_matter", "synthetic_body"):
        return None
    s_clean = (title or "").strip() if isinstance(title, str) else ""
    if not s_clean:
        return None
    p_clean = (parent_title or "").strip() if isinstance(parent_title, str) else ""
    if (
        p_clean
        and parent_section_type not in ("front_matter", "synthetic_body")
        and p_clean != s_clean
    ):
        return f"{p_clean} › {s_clean}"
    return s_clean


def _detect_repeated_running_headers(pages: Sequence[Any]) -> set[str]:
    """Identify short top-of-page lines that repeat across >= 4 pages and >= 20% of body pages."""

    def _p_is_toc(pg: Any) -> bool:
        return bool(
            pg.get("is_toc", False)
            if isinstance(pg, dict)
            else getattr(pg, "is_toc", False)
        )

    def _p_text(pg: Any) -> str:
        return (
            pg.get("text") if isinstance(pg, dict) else getattr(pg, "text", None)
        ) or ""

    body_pages = [p for p in pages if not _p_is_toc(p) and _p_text(p).strip()]
    if len(body_pages) < 6:
        return set()

    first_line_counts: Counter[str] = Counter()
    for p in body_pages:
        raw_lines = [ln.strip() for ln in _p_text(p).split("\n") if ln.strip()]
        first_candidate: Optional[str] = None
        for raw_ln in raw_lines:
            if re.match(r"^\s*\[Footer\]", raw_ln, flags=re.IGNORECASE):
                continue
            if re.match(r"^\s*\[Header\]", raw_ln, flags=re.IGNORECASE):
                header_inner = re.sub(
                    r"^\s*\[Header\]\s*", "", raw_ln, flags=re.IGNORECASE
                ).strip()
                header_inner = re.sub(r"^\s*#{1,6}\s*", "", header_inner).strip()
                if (
                    not header_inner
                    or is_isolated_page_number(header_inner)
                    or _DIVIDER_NOISE_RE.match(header_inner)
                    or _HTML_COMMENT_RE.match(header_inner)
                ):
                    continue
                # Explicit [Header] text is already stripped as meta_noise by parse_page_blocks;
                # never count it toward repeated_running_headers lest a chapter running header
                # wipe out the real in-page chapter heading.
                break
            unwrapped = _OCR_MARKER_RE.sub("", raw_ln).strip()
            unwrapped = re.sub(r"^\s*#{1,6}\s*", "", unwrapped).strip()
            if (
                not unwrapped
                or is_isolated_page_number(unwrapped)
                or _DIVIDER_NOISE_RE.match(unwrapped)
                or _HTML_COMMENT_RE.match(unwrapped)
            ):
                continue
            first_candidate = unwrapped
            break

        if (
            first_candidate
            and 2 <= len(first_candidate) <= 70
            and not is_structural_chapter_title(first_candidate)
        ):
            norm = normalize_section_title(first_candidate)
            if norm:
                first_line_counts[norm] += 1

    threshold = max(4, int(len(body_pages) * 0.20))
    return {norm for norm, count in first_line_counts.items() if count >= threshold}


def _title_similarity(norm_a: str, norm_b: str) -> float:
    """Compute normalized title similarity in [0.0, 1.0]."""
    if not norm_a or not norm_b:
        return 0.0
    if norm_a == norm_b:
        return 1.0
    if norm_a in norm_b or norm_b in norm_a:
        shorter = min(len(norm_a), len(norm_b))
        longer = max(len(norm_a), len(norm_b))
        if shorter >= 4 and (
            shorter / longer >= 0.6
            or norm_a.startswith(norm_b + " ")
            or norm_b.startswith(norm_a + " ")
        ):
            return 0.90
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def solve_content_page_numbers(
    pages: Sequence[Any],
    toc_entries: Optional[Sequence[tuple[str, int]]] = None,
) -> tuple[dict[int, Optional[str]], int]:
    """Stage 1: Solve `Page.content_page_number` across all pages of a book.

    1. Preserves `Page.content_page_number` on any page with `content_page_number_manual == True`.
    2. Fits a piecewise-constant offset `c_p = page_number - printed_page` via dynamic
       programming with a step-change penalty requiring >= 3 corroborating detections
       to shift offsets (handling mid-book scan gaps/plates while rejecting single-page
       outliers like years `1985`).
    3. When `< 15%` of body pages carry `detected_page_number` and `toc_entries` exist,
       anchors offsets by matching unique ToC titles against in-page headings.

    Returns `(page_number_to_content_page_str, modal_offset)`.
    """
    if not pages:
        return {}, 0

    ordered_pages = sorted(pages, key=lambda p: int(p.page_number))
    max_valid_printed = max(len(ordered_pages) + 100, 5000)

    # Collect observations: (page_number, offset = page_number - printed_page, weight)
    observations: List[tuple[int, int, float]] = []
    manual_pages: dict[int, Optional[str]] = {}
    detected_body_count = 0
    body_pages_count = 0

    for p in ordered_pages:
        pnum = int(p.page_number)
        is_toc = bool(getattr(p, "is_toc", False))
        if not is_toc:
            body_pages_count += 1

        if bool(getattr(p, "content_page_number_manual", False)):
            manual_val = getattr(p, "content_page_number", None)
            manual_pages[pnum] = str(manual_val) if manual_val is not None else None
            if manual_val is not None and str(manual_val).isdigit():
                printed = int(str(manual_val))
                if printed >= 1:
                    observations.append((pnum, pnum - printed, 10.0))
            continue

        if is_toc:
            continue

        det = getattr(p, "detected_page_number", None)
        if det is None:
            det = extract_standalone_page_number(getattr(p, "text", "") or "")
        if det is not None:
            printed = int(det)
            offset = pnum - printed
            if 1 <= printed <= max_valid_printed and -5 <= offset < len(ordered_pages):
                detected_body_count += 1
                observations.append((pnum, offset, 1.0))

    detection_ratio = (
        detected_body_count / body_pages_count if body_pages_count > 0 else 0.0
    )

    # Stage 1.3: ToC-Anchor Fallback when < 15% of body pages carry detected_page_number
    if detection_ratio < 0.15 and toc_entries:
        norm_toc_counts = Counter(
            normalize_section_title(title)
            for title, _ in toc_entries
            if normalize_section_title(title)
        )
        unique_toc = [
            (normalize_section_title(title), int(printed_p))
            for title, printed_p in toc_entries
            if norm_toc_counts[normalize_section_title(title)] == 1
            and int(printed_p) >= 1
        ]
        if unique_toc:
            running_headers = _detect_repeated_running_headers(ordered_pages)
            page_headings: dict[int, List[str]] = {}
            for p in ordered_pages:
                if getattr(p, "is_toc", False):
                    continue
                p_blocks = parse_page_blocks(
                    getattr(p, "text", "") or "",
                    is_toc=False,
                    repeated_running_headers=running_headers,
                )
                h_norms = [
                    b.normalized_text
                    for b in p_blocks
                    if b.kind == "heading" and b.normalized_text
                ]
                if h_norms:
                    page_headings[int(p.page_number)] = h_norms

            for toc_norm, toc_printed in unique_toc:
                matching_pages = [
                    pnum
                    for pnum, h_list in page_headings.items()
                    if any(_title_similarity(toc_norm, h) >= 0.86 for h in h_list)
                    and pnum - toc_printed >= -2
                ]
                if len(matching_pages) == 1:
                    pnum = matching_pages[0]
                    observations.append((pnum, pnum - toc_printed, 1.5))

    if not observations:
        # Check if book has no observations at all: preserve manual overrides, leave rest None
        result: dict[int, Optional[str]] = {}
        for p in ordered_pages:
            pnum = int(p.page_number)
            if pnum in manual_pages:
                result[pnum] = manual_pages[pnum]
            else:
                result[pnum] = None
        return result, 0

    # Candidate offsets from observations
    offset_weights: Counter[int] = Counter()
    for _, off, w in observations:
        offset_weights[off] += w

    # Require either manual override weight (>= 10) or >= 2 corroborating observations
    # (or the single modal ToC observation when only 1-2 unique ToC anchors exist)
    candidate_offsets = sorted(off for off, w in offset_weights.items() if w >= 2.0)
    if not candidate_offsets:
        # If fewer than 2 observations agreed, fall back to None unless a single ToC anchor matched
        top_off, top_w = offset_weights.most_common(1)[0]
        if top_w >= 1.5:
            candidate_offsets = [top_off]
        else:
            result = {
                int(p.page_number): manual_pages.get(int(p.page_number), None)
                for p in ordered_pages
            }
            return result, 0

    # Dynamic programming over observations sorted by page_number
    observations.sort(key=lambda item: item[0])
    m_obs = len(observations)
    k_cands = len(candidate_offsets)
    step_penalty = 2.6  # Requires >= 3 corroborating observations to switch offsets

    dp = [[0.0] * k_cands for _ in range(m_obs)]
    backptr = [[0] * k_cands for _ in range(m_obs)]

    for j, c in enumerate(candidate_offsets):
        _, obs_off, weight = observations[0]
        dp[0][j] = 0.0 if obs_off == c else weight

    for i in range(1, m_obs):
        _, obs_off, weight = observations[i]
        prev_row = dp[i - 1]
        min_prev_idx = min(range(k_cands), key=lambda k: prev_row[k])
        min_prev_cost_with_step = prev_row[min_prev_idx] + step_penalty
        for j, c in enumerate(candidate_offsets):
            mismatch_cost = 0.0 if obs_off == c else weight
            best_prev_cost = prev_row[j]
            best_prev_idx = j
            if min_prev_idx != j and min_prev_cost_with_step < best_prev_cost:
                best_prev_cost = min_prev_cost_with_step
                best_prev_idx = min_prev_idx
            dp[i][j] = best_prev_cost + mismatch_cost
            backptr[i][j] = best_prev_idx

    # Backtrack optimal offset sequence at observation points
    best_last_j = min(range(k_cands), key=lambda j: dp[m_obs - 1][j])
    fitted_obs_offsets = [0] * m_obs
    curr_j = best_last_j
    for i in range(m_obs - 1, -1, -1):
        fitted_obs_offsets[i] = candidate_offsets[curr_j]
        curr_j = backptr[i][curr_j]

    # Build page -> fitted offset map across all physical pages
    obs_pages = [obs[0] for obs in observations]
    fitted_offset_by_page: dict[int, int] = {}
    obs_ptr = 0
    for p in ordered_pages:
        pnum = int(p.page_number)
        while obs_ptr + 1 < m_obs and obs_pages[obs_ptr + 1] <= pnum:
            obs_ptr += 1
        fitted_offset_by_page[pnum] = fitted_obs_offsets[obs_ptr]

    modal_offset = Counter(fitted_obs_offsets).most_common(1)[0][0]
    modal_offset = max(0, int(modal_offset))

    content_map: dict[int, Optional[str]] = {}
    for p in ordered_pages:
        pnum = int(p.page_number)
        if pnum in manual_pages:
            content_map[pnum] = manual_pages[pnum]
            continue
        if getattr(p, "is_toc", False):
            content_map[pnum] = None
            continue
        c_p = fitted_offset_by_page.get(pnum, modal_offset)
        printed_num = pnum - c_p
        if printed_num <= 0:
            content_map[pnum] = None
        else:
            content_map[pnum] = str(printed_num)

    return content_map, modal_offset


def close_span_before_next(
    start_page: int,
    start_block: int,
    nxt_page: int,
    nxt_block: int,
    blocks_by_page: Optional[dict[int, List[PageBlock]]] = None,
) -> tuple[int, int]:
    """Compute `(end_page, end_block_index)` immediately before `(nxt_page, nxt_block)`.

    When `nxt_block > 0` on `nxt_page > start_page`, only extends into `nxt_page` if
    there is at least one non-`meta_noise` block before `nxt_block` on `nxt_page`.
    """
    if nxt_page == start_page:
        return nxt_page, max(start_block, nxt_block - 1)
    if nxt_block > 0 and (
        blocks_by_page is None
        or any(
            b.kind != "meta_noise"
            for b in blocks_by_page.get(nxt_page, [])
            if b.block_index < nxt_block
        )
    ):
        return nxt_page, nxt_block - 1
    return max(start_page, nxt_page - 1), 999999


def _close_section_boundaries(
    raw_sections: List[dict[str, Any]],
    max_body_page: int,
    blocks_by_page: Optional[dict[int, List[PageBlock]]] = None,
) -> List[dict[str, Any]]:
    """Assign deterministic `section_index`, `parent_section_index`, and closed
    `(end_page, end_block_index)` spans across all sections."""
    if not raw_sections:
        return []

    # Sort sections in reading order: (start_page, start_block_index, level)
    raw_sections.sort(
        key=lambda s: (
            int(s["start_page"]),
            int(s.get("start_block_index", 0)),
            int(s.get("level", 1)),
        )
    )

    for idx, sec in enumerate(raw_sections):
        sec["section_index"] = idx

    # Link level-2 sections to the most recent preceding level-1 chapter section
    active_chapter_idx: Optional[int] = None
    for sec in raw_sections:
        can_parent = bool(sec.pop("_can_parent", True))
        if int(sec.get("level", 1)) == 1:
            if sec.get("section_type") == "chapter" and can_parent:
                active_chapter_idx = sec["section_index"]
            else:
                active_chapter_idx = None
            sec["parent_section_index"] = None
        else:
            if active_chapter_idx is not None:
                sec["parent_section_index"] = active_chapter_idx
            else:
                # Promote orphan level-2 work/chapter to level-1 if no chapter precedes it
                sec["level"] = 1
                sec["parent_section_index"] = None

    parent_indices = {
        sec["parent_section_index"]
        for sec in raw_sections
        if sec.get("parent_section_index") is not None
    }

    # Close leaf section boundaries immediately before the next section in reading order starts
    # (whether that next section is a sibling work or the next level-1 chapter).
    for idx, sec in enumerate(raw_sections):
        if sec["section_index"] in parent_indices:
            continue
        leaf = sec
        if idx + 1 < len(raw_sections):
            nxt = raw_sections[idx + 1]
            leaf["end_page"], leaf["end_block_index"] = close_span_before_next(
                int(leaf["start_page"]),
                int(leaf.get("start_block_index", 0)),
                int(nxt["start_page"]),
                int(nxt.get("start_block_index", 0)),
                blocks_by_page,
            )
        else:
            leaf["end_page"] = max(int(leaf["start_page"]), max_body_page)
            leaf["end_block_index"] = 999999

    # Close parent chapter boundaries over their children (or up to the next level-1 section)
    level1_sections = [sec for sec in raw_sections if int(sec.get("level", 1)) == 1]
    for i, ch in enumerate(level1_sections):
        if ch["section_index"] not in parent_indices:
            continue
        children = [
            sec
            for sec in raw_sections
            if sec.get("parent_section_index") == ch["section_index"]
        ]
        if children:
            ch["end_page"] = max(int(c["end_page"]) for c in children)
            last_child = max(
                children, key=lambda c: (int(c["end_page"]), int(c["end_block_index"]))
            )
            ch["end_block_index"] = int(last_child["end_block_index"])
        elif i + 1 < len(level1_sections):
            nxt_l1 = level1_sections[i + 1]
            ch["end_page"] = max(int(ch["start_page"]), int(nxt_l1["start_page"]) - 1)
            ch["end_block_index"] = 999999
        else:
            ch["end_page"] = max(int(ch["start_page"]), max_body_page)
            ch["end_block_index"] = 999999

    return raw_sections


def extract_book_sections(
    pages: Sequence[Any],
    toc_entries: Optional[Sequence[tuple[str, int]]] = None,
    *,
    book_title: Optional[str] = None,
) -> List[dict[str, Any]]:
    """Stage 2: Deterministic two-tier (`chapter` -> `work`) `book_sections` extraction."""
    ordered_pages = sorted(pages, key=lambda p: int(p.page_number))
    body_pages = [
        p
        for p in ordered_pages
        if not getattr(p, "is_toc", False) and (getattr(p, "text", "") or "").strip()
    ]
    if not body_pages:
        return []

    first_body_page = int(body_pages[0].page_number)
    max_body_page = int(body_pages[-1].page_number)
    running_headers = _detect_repeated_running_headers(ordered_pages)

    blocks_by_page: dict[int, List[PageBlock]] = {}
    for p in body_pages:
        pnum = int(p.page_number)
        blocks_by_page[pnum] = parse_page_blocks(
            getattr(p, "text", "") or "",
            is_toc=False,
            repeated_running_headers=running_headers,
        )

    # Build printed_page -> physical_page map from Page.content_page_number
    printed_to_physical: dict[int, int] = {}
    offsets: List[int] = []
    for p in body_pages:
        pnum = int(p.page_number)
        cp = getattr(p, "content_page_number", None)
        if cp is not None and str(cp).isdigit():
            printed_int = int(str(cp))
            if printed_int not in printed_to_physical:
                printed_to_physical[printed_int] = pnum
            offsets.append(pnum - printed_int)
    modal_offset = Counter(offsets).most_common(1)[0][0] if offsets else 0

    raw_sections: List[dict[str, Any]] = []

    # ── Mode A: ToC Reconciliation Mode ────────────────────────────────────────
    if toc_entries:
        has_structural_toc = any(
            is_structural_chapter_title(title) for title, _ in toc_entries
        )
        cursor_page = first_body_page
        cursor_block = 0

        for title, printed_page in toc_entries:
            clean_title = re.sub(
                r"^\s*#{1,6}\s*", "", normalize_uyghur_chars(title)
            ).strip()
            norm_title = normalize_section_title(clean_title)
            if not norm_title:
                continue

            expected_phys = printed_to_physical.get(
                int(printed_page), int(printed_page) + modal_offset
            )
            expected_phys = min(max(expected_phys, first_body_page), max_body_page)

            # Search heading blocks within expected_phys ± 2 in monotonic (page, block_index) order
            search_start = max(cursor_page, expected_phys - 2)
            search_end = min(max_body_page, expected_phys + 2)

            best_match: Optional[tuple[int, int, float]] = None
            for cand_page in range(search_start, search_end + 1):
                for blk in blocks_by_page.get(cand_page, []):
                    if blk.kind != "heading" or not blk.normalized_text:
                        continue
                    if cand_page == cursor_page and blk.block_index < cursor_block:
                        continue
                    sim = _title_similarity(norm_title, blk.normalized_text)
                    if sim >= 0.78:
                        if best_match is None or sim > best_match[2]:
                            best_match = (cand_page, blk.block_index, sim)
                            if sim == 1.0 and cand_page == expected_phys:
                                break
                if (
                    best_match
                    and best_match[2] == 1.0
                    and best_match[0] == expected_phys
                ):
                    break

            is_struct = is_structural_chapter_title(clean_title)
            if has_structural_toc:
                level = 1 if is_struct else 2
                section_type = "chapter" if is_struct else "work"
            else:
                level = 1
                section_type = "chapter" if is_struct else "work"

            if best_match is not None:
                m_page, m_block, m_sim = best_match
                start_page = m_page
                start_block = m_block
                source = "toc_matched"
                confidence = round(float(m_sim), 3)
                cursor_page = m_page
                cursor_block = m_block + 1
            else:
                start_page = max(cursor_page, expected_phys)
                start_block = cursor_block if start_page == cursor_page else 0
                source = "toc_interpolated"
                confidence = 0.60
                cursor_page = start_page

            raw_sections.append(
                {
                    "level": level,
                    "section_type": section_type,
                    "title": clean_title,
                    "normalized_title": norm_title,
                    "toc_printed_page": int(printed_page),
                    "start_page": start_page,
                    "start_block_index": start_block,
                    "end_page": start_page,
                    "end_block_index": 999999,
                    "source": source,
                    "confidence": confidence,
                }
            )

        # Attach child `work` sections inside chapter-only ToCs when explicit Markdown level-2 headings exist in-page
        if raw_sections and all(
            s["level"] == 1 and s["section_type"] == "chapter" for s in raw_sections
        ):
            matched_keys = {
                (int(s["start_page"]), int(s["start_block_index"]))
                for s in raw_sections
            }
            first_ch_page = min(int(s["start_page"]) for s in raw_sections)
            for pnum, p_blocks in blocks_by_page.items():
                if pnum < first_ch_page:
                    continue
                page_toc_norms = [
                    s["normalized_title"]
                    for s in raw_sections
                    if int(s["start_page"]) == pnum and s.get("normalized_title")
                ]
                for blk in p_blocks:
                    if (
                        blk.kind == "heading"
                        and blk.heading_level == 2
                        and _MARKDOWN_HEADING_RE.match(blk.raw_text)
                        and (pnum, blk.block_index) not in matched_keys
                    ):
                        clean_h = re.sub(r"^\s*#{1,6}\s*", "", blk.raw_text).strip()
                        if clean_h and blk.normalized_text:
                            # Skip subtitle line that is already part of the chapter's ToC title on the same page
                            if any(
                                blk.normalized_text in ch_norm
                                for ch_norm in page_toc_norms
                            ):
                                continue
                            raw_sections.append(
                                {
                                    "level": 2,
                                    "section_type": "work",
                                    "title": clean_h,
                                    "normalized_title": blk.normalized_text,
                                    "toc_printed_page": None,
                                    "start_page": pnum,
                                    "start_block_index": blk.block_index,
                                    "end_page": pnum,
                                    "end_block_index": 999999,
                                    "source": "header_detected",
                                    "confidence": 0.85,
                                }
                            )

    # ── Mode B: Header-Driven Mode (ToC-less books) ───────────────────────────
    if not raw_sections:
        has_markdown_headings = any(
            blk.kind == "heading" and _MARKDOWN_HEADING_RE.match(blk.raw_text)
            for p_blocks in blocks_by_page.values()
            for blk in p_blocks
        )
        norm_book_title = normalize_section_title(book_title or "")
        cover_pages = {
            int(p.page_number)
            for p in body_pages
            if int(p.page_number) <= 4
            and getattr(p, "content_page_number", None) is None
            and is_title_cover_page(
                getattr(p, "text", "") or "",
                book_title=book_title,
                page_number=int(p.page_number),
            )
            and not any(
                (b.kind == "heading" and is_structural_chapter_title(b.raw_text))
                or (
                    b.kind == "prose"
                    and b.raw_text.rstrip().endswith((".", "۔", "؟", "!"))
                )
                for b in blocks_by_page.get(int(p.page_number), [])
            )
        }
        title_stack_pages: set[int] = set()
        for pnum, p_blocks in blocks_by_page.items():
            if pnum > 2:
                continue
            h_cnt = sum(1 for b in p_blocks if b.kind == "heading")
            body_cnt = sum(1 for b in p_blocks if b.kind in {"prose", "verse", "table"})
            if h_cnt >= 3 and body_cnt == 0:
                title_stack_pages.add(pnum)

        # Collect raw candidate headings first so recurring template rubrics and
        # repeated book-title headers can be filtered before assigning section levels.
        raw_candidates: List[tuple[int, PageBlock, str]] = []
        for pnum, p_blocks in blocks_by_page.items():
            for blk_pos, blk in enumerate(p_blocks):
                if blk.kind != "heading" or not blk.normalized_text:
                    continue
                if (
                    has_markdown_headings
                    and blk.heading_level == 2
                    and not _MARKDOWN_HEADING_RE.match(blk.raw_text)
                ):
                    continue
                clean_h = re.sub(r"^\s*#{1,6}\s*", "", blk.raw_text).strip()
                if not clean_h:
                    continue
                is_struct_h = is_structural_chapter_title(clean_h)
                if not is_struct_h:
                    if blk.normalized_text in _GENERIC_SUBSECTION_RUBRICS:
                        continue
                    if pnum in (cover_pages | title_stack_pages):
                        continue
                    # Skip page-1 leading book/genre title line stacked directly above a chapter heading
                    if pnum <= 2:
                        following = p_blocks[blk_pos + 1 :]
                        next_substantive = next(
                            (b for b in following if b.kind != "meta_noise"), None
                        )
                        if (
                            next_substantive is not None
                            and next_substantive.kind == "heading"
                            and is_structural_chapter_title(next_substantive.raw_text)
                        ):
                            continue
                raw_candidates.append((pnum, blk, clean_h))

        cand_norm_counts = Counter(blk.normalized_text for _, blk, _ in raw_candidates)
        book_title_matches = [
            (pnum, blk)
            for pnum, blk, _ in raw_candidates
            if norm_book_title
            and len(norm_book_title) >= 3
            and _title_similarity(blk.normalized_text, norm_book_title) >= 0.88
        ]
        has_other_candidates = len(raw_candidates) > len(book_title_matches)

        kept_candidates: List[tuple[int, PageBlock, str]] = []
        for pnum, blk, clean_h in raw_candidates:
            is_struct_h = is_structural_chapter_title(clean_h)
            if (
                not is_struct_h
                and cand_norm_counts[blk.normalized_text] >= 3
                and blk.normalized_text not in _POETIC_FORM_TITLES
            ):
                continue
            if (
                has_other_candidates
                and norm_book_title
                and len(norm_book_title) >= 3
                and _title_similarity(blk.normalized_text, norm_book_title) >= 0.88
                and (
                    len(book_title_matches) >= 2
                    or pnum in {first_body_page, max_body_page}
                )
            ):
                continue
            kept_candidates.append((pnum, blk, clean_h))

        has_level1_chapters = any(
            blk.heading_level == 1 for _, blk, _ in kept_candidates
        )
        for pnum, blk, clean_h in kept_candidates:
            if blk.heading_level == 1:
                level = 1
                sec_type = "chapter"
            else:
                level = 2 if has_level1_chapters else 1
                sec_type = "work"
            raw_sections.append(
                {
                    "level": level,
                    "section_type": sec_type,
                    "title": clean_h,
                    "normalized_title": blk.normalized_text,
                    "toc_printed_page": None,
                    "start_page": pnum,
                    "start_block_index": blk.block_index,
                    "end_page": pnum,
                    "end_block_index": 999999,
                    "source": "header_detected",
                    "confidence": 0.90,
                }
            )

    # ── Nest Chapter (`باب`/`پەسىل`) under Part (`قىسىم`/`بۆلۈم`) when both exist ──
    if raw_sections:
        has_parts = any(is_part_division_title(s["title"]) for s in raw_sections)
        has_chapters = any(is_chapter_section_title(s["title"]) for s in raw_sections)
        if has_parts and has_chapters:
            has_existing_level2 = any(int(s.get("level", 1)) == 2 for s in raw_sections)
            if not has_existing_level2:
                for s in raw_sections:
                    if is_part_division_title(s["title"]):
                        s["level"] = 1
                        s["section_type"] = "chapter"
                        s["_can_parent"] = True
                    elif is_chapter_section_title(s["title"]):
                        s["level"] = 2
                        s["section_type"] = "chapter"
                    else:
                        s["level"] = 1
                        s["_can_parent"] = False
            else:
                # 3-tier book (Part -> Chapter -> Work): fold body-less Part divider
                # headings into child chapters so 2-level schema holds without divider stubs.
                raw_sections.sort(
                    key=lambda s: (
                        int(s["start_page"]),
                        int(s.get("start_block_index", 0)),
                        int(s.get("level", 1)),
                    )
                )

                def _span_has_body(sp: int, sb: int, np: int, nb: int) -> bool:
                    ep, eb = close_span_before_next(sp, sb, np, nb, blocks_by_page)
                    for pg_n in range(sp, ep + 1):
                        for b in blocks_by_page.get(pg_n, []):
                            if (pg_n > sp or b.block_index >= sb) and (
                                pg_n < ep or b.block_index <= eb
                            ):
                                if b.kind in {"prose", "verse", "table", "footnote"}:
                                    return True
                    return False

                folded_sections: List[dict[str, Any]] = []
                active_part_prefix: Optional[str] = None
                for idx_s, s in enumerate(raw_sections):
                    if is_part_division_title(s["title"]):
                        active_part_prefix = s["title"]
                        if idx_s + 1 < len(raw_sections):
                            nxt_s = raw_sections[idx_s + 1]
                            if not _span_has_body(
                                int(s["start_page"]),
                                int(s.get("start_block_index", 0)),
                                int(nxt_s["start_page"]),
                                int(nxt_s.get("start_block_index", 0)),
                            ):
                                continue
                    elif (
                        active_part_prefix
                        and int(s.get("level", 1)) == 1
                        and is_chapter_section_title(s["title"])
                    ):
                        s["title"] = f"{active_part_prefix} — {s['title']}"
                        s["normalized_title"] = normalize_section_title(s["title"])
                    elif int(s.get("level", 1)) == 1 and not is_chapter_section_title(
                        s["title"]
                    ):
                        active_part_prefix = None
                    folded_sections.append(s)
                raw_sections = folded_sections

    # Leading front-matter section when content pages precede the first detected section
    if raw_sections:
        raw_sections.sort(
            key=lambda s: (int(s["start_page"]), int(s.get("start_block_index", 0)))
        )
        first_sec = raw_sections[0]
        if int(first_sec["start_page"]) > first_body_page or (
            int(first_sec["start_page"]) == first_body_page
            and int(first_sec.get("start_block_index", 0)) > 0
        ):
            raw_sections.insert(
                0,
                {
                    "level": 1,
                    "section_type": "front_matter",
                    "title": "باش قىسىم",
                    "normalized_title": normalize_section_title("باش قىسىم"),
                    "toc_printed_page": None,
                    "start_page": first_body_page,
                    "start_block_index": 0,
                    "end_page": int(first_sec["start_page"]),
                    "end_block_index": 999999,
                    "source": "header_detected",
                    "confidence": 1.0,
                },
            )
    else:
        # Plain-prose fallback: single synthetic_body section covering the book
        fallback_title = (book_title or "").strip() or "تېكىست"
        raw_sections.append(
            {
                "level": 1,
                "section_type": "synthetic_body",
                "title": fallback_title,
                "normalized_title": normalize_section_title(fallback_title) or "تېكىست",
                "toc_printed_page": None,
                "start_page": first_body_page,
                "start_block_index": 0,
                "end_page": max_body_page,
                "end_block_index": 999999,
                "source": "synthetic_body",
                "confidence": 1.0,
            }
        )

    return _close_section_boundaries(raw_sections, max_body_page, blocks_by_page)


class BookStructureService:
    """Service orchestrating Stage 1 (`content_page_number`) and Stage 2 (`book_sections`)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.pages_repo = PagesRepository(session)
        self.sections_repo = BookSectionsRepository(session)

    async def _run_analyze_and_persist(self, book_id: str) -> dict[str, Any]:
        """Run Stage 1 and Stage 2 for `book_id` and persist `Page.content_page_number`
        and `BookSection` rows in the current transaction."""
        book = await self.session.get(Book, book_id)
        if not book:
            raise ValueError(f"Book not found: {book_id}")

        pages = await self.pages_repo.find_by_book(book_id, limit=20000)
        if not pages:
            await self.sections_repo.replace_for_book(book_id, [])
            return {"book_id": book_id, "sections_count": 0, "content_page_offset": 0}

        # Clear auto-detected is_toc flags on colophon/copyright pages unless manually set by a human editor
        for p in pages:
            if (
                bool(p.is_toc)
                and p.text
                and is_colophon_page(p.text)
                and not (
                    getattr(p, "updated_by", None)
                    and "@" in str(getattr(p, "updated_by", ""))
                )
            ):
                p.is_toc = False

        # Auto-detect ToC pages if none are flagged yet (skip pages manually edited/unflagged by an editor)
        if not any(bool(p.is_toc) for p in pages):
            for p in pages:
                if (
                    not getattr(p, "updated_by", None)
                    and p.text
                    and is_toc_page(p.text)
                ):
                    p.is_toc = True

        toc_entries: List[tuple[str, int]] = []
        for p in pages:
            if p.is_toc and p.text:
                toc_entries.extend(parse_toc_entries(p.text))

        content_map, modal_offset = solve_content_page_numbers(pages, toc_entries)
        for p in pages:
            if not getattr(p, "content_page_number_manual", False):
                p.content_page_number = content_map.get(int(p.page_number))

        if modal_offset > 0 or not any(
            getattr(p, "content_page_number_manual", False) for p in pages
        ):
            book.content_page_offset = modal_offset

        sections_payload = extract_book_sections(
            pages, toc_entries, book_title=book.title
        )
        persisted = await self.sections_repo.replace_for_book(book_id, sections_payload)
        await self.session.flush()

        return {
            "book_id": book_id,
            "sections_count": len(persisted),
            "content_page_offset": book.content_page_offset,
        }

    @classmethod
    async def analyze_and_persist_book_structure(
        cls, session_or_self: Any, book_id: Optional[str] = None
    ) -> dict[str, Any]:
        if isinstance(session_or_self, cls):
            if not book_id:
                raise ValueError("book_id is required")
            return await session_or_self._run_analyze_and_persist(book_id)
        if not book_id:
            raise ValueError("book_id is required")
        return await cls(session_or_self)._run_analyze_and_persist(book_id)


async def analyze_and_persist_book_structure(
    session: AsyncSession, book_id: str
) -> dict[str, Any]:
    """Convenience function wrapping `BookStructureService(session).analyze_and_persist_book_structure`."""
    service = BookStructureService(session)
    return await service.analyze_and_persist_book_structure(book_id)


def preserve_active_structure_claim():
    """Return a SQL expression that keeps `structure_claimed_at` when a job is `in_progress`."""
    return case(
        (
            Book.structure_milestone == BOOK_MILESTONE_IN_PROGRESS,
            Book.structure_claimed_at,
        ),
        else_=None,
    )


def preserve_active_chunking_claim():
    """Return a SQL expression that keeps `chunking_claimed_at` when a job is `in_progress`."""
    return case(
        (
            Book.chunking_milestone == BOOK_MILESTONE_IN_PROGRESS,
            Book.chunking_claimed_at,
        ),
        else_=None,
    )


def structure_dirty_values(**extra_values: Any) -> dict[str, Any]:
    """Build SQL column values for resetting `structure_milestone` to `idle` while
    preserving `structure_claimed_at` if a `structure_job` is currently `in_progress`."""
    values: dict[str, Any] = {
        "structure_milestone": BOOK_MILESTONE_IDLE,
        "structure_retry_count": 0,
        "structure_claimed_at": preserve_active_structure_claim(),
    }
    values.update(extra_values)
    return values


async def mark_structure_dirty(
    session: AsyncSession,
    book_ids: Union[str, Sequence[str]],
    *,
    touch_last_updated: bool = True,
    **extra_values: Any,
) -> None:
    """Reset `structure_milestone = 'idle'` and `structure_retry_count = 0` for `book_ids`
    while preserving `structure_claimed_at` if a `structure_job` is currently `in_progress`."""
    ids = [book_ids] if isinstance(book_ids, str) else [b for b in book_ids if b]
    if not ids:
        return
    values = structure_dirty_values(**extra_values)
    if touch_last_updated and "last_updated" not in values:
        values["last_updated"] = func.now()
    cond = Book.id == ids[0] if len(ids) == 1 else Book.id.in_(ids)
    await session.execute(update(Book).where(cond).values(**values))


async def claim_book_for_chunking(
    session: AsyncSession,
    book_id: str,
) -> bool:
    """Atomically claim `book_id` for `chunking_job` if `chunking_claimed_at IS NULL`."""
    stmt = (
        select(Book.id)
        .where(
            Book.id == book_id,
            Book.ocr_milestone == BOOK_MILESTONE_COMPLETE,
            Book.structure_milestone == BOOK_MILESTONE_COMPLETE,
            Book.chunking_milestone == BOOK_MILESTONE_IDLE,
            Book.chunking_claimed_at.is_(None),
            ~Book.status.in_(["error"]),
        )
        .with_for_update(skip_locked=True)
    )
    res = await session.execute(stmt)
    row = res.first() if hasattr(res, "first") else None
    if not row:
        return False
    await session.execute(
        update(Book)
        .where(Book.id == book_id)
        .values(
            chunking_milestone=BOOK_MILESTONE_IN_PROGRESS,
            chunking_claimed_at=func.now(),
            last_updated=func.now(),
        )
    )
    return True


async def claim_books_for_structure(
    session: AsyncSession,
    *,
    book_ids: Optional[Sequence[str]] = None,
    require_spell_check_terminal: bool = False,
    limit: Optional[int] = None,
) -> List[str]:
    """Atomically claim books eligible for `structure_job`.

    Enforces:
    - `ocr_milestone == 'complete'`
    - `structure_milestone == 'idle'`
    - `structure_claimed_at IS NULL` (never starts a second job while one is in progress)
    - `~status.in_(['error'])`
    - When `require_spell_check_terminal=True`, `spell_check_milestone` is terminal.
    """
    if book_ids is not None and len(book_ids) == 0:
        return []

    where_conditions = [
        Book.ocr_milestone == BOOK_MILESTONE_COMPLETE,
        Book.structure_milestone == BOOK_MILESTONE_IDLE,
        Book.structure_claimed_at.is_(None),
        ~Book.status.in_(["error"]),
    ]
    if book_ids is not None:
        where_conditions.append(Book.id.in_(list(book_ids)))
    if require_spell_check_terminal:
        where_conditions.append(
            Book.spell_check_milestone.in_(
                [
                    BOOK_MILESTONE_COMPLETE,
                    BOOK_MILESTONE_FAILED,
                    BOOK_MILESTONE_PARTIAL_FAILURE,
                ]
            )
        )

    stmt = select(Book.id).where(*where_conditions).with_for_update(skip_locked=True)
    if limit is not None:
        stmt = stmt.limit(limit)

    result = await session.execute(stmt)
    rows = result.fetchall() if hasattr(result, "fetchall") else result.all()
    claimed_book_ids = [row[0] for row in rows if row and row[0]]
    if not claimed_book_ids:
        return []

    await session.execute(
        update(Book)
        .where(Book.id.in_(claimed_book_ids))
        .values(
            structure_milestone=BOOK_MILESTONE_IN_PROGRESS,
            structure_claimed_at=func.now(),
            last_updated=func.now(),
        )
    )
    return claimed_book_ids


async def release_claimed_structure_books(
    book_ids: Sequence[str],
    *,
    session: Optional[AsyncSession] = None,
    session_factory: Optional[Any] = None,
) -> None:
    """Revert claimed books back to `idle` when ARQ enqueueing fails or drops."""
    if not book_ids:
        return
    stmt = (
        update(Book)
        .where(Book.id.in_(list(book_ids)))
        .values(
            structure_milestone=BOOK_MILESTONE_IDLE,
            structure_claimed_at=None,
            last_updated=func.now(),
        )
    )
    if session is not None:
        await session.execute(stmt)
        await session.commit()
        return

    if session_factory is None:
        from app.db import session as db_session

        session_factory = db_session.async_session_factory
    if session_factory is not None:
        async with session_factory() as revert_session:
            await revert_session.execute(stmt)
            await revert_session.commit()


async def enqueue_claimed_structure_jobs(
    redis: Any,
    book_ids: Sequence[str],
    *,
    session: Optional[AsyncSession] = None,
    session_factory: Optional[Any] = None,
) -> int:
    """Enqueue `structure_job` for already-claimed books, reverting claims on failure."""
    if not book_ids:
        return 0
    if redis is None:
        await release_claimed_structure_books(
            book_ids, session=session, session_factory=session_factory
        )
        return 0

    dropped_ids: List[str] = []
    enqueued = 0
    for book_id in book_ids:
        try:
            job = await redis.enqueue_job(
                "structure_job",
                book_id=book_id,
            )
            if job is None:
                dropped_ids.append(book_id)
            else:
                enqueued += 1
        except Exception as exc:
            logger.error(
                f"Failed to enqueue structure_job for book {book_id}: {exc}",
                exc_info=True,
            )
            dropped_ids.append(book_id)

    if dropped_ids:
        await release_claimed_structure_books(
            dropped_ids, session=session, session_factory=session_factory
        )
    return enqueued


async def claim_and_enqueue_structure_for_book(
    book_id: str,
    *,
    session: Optional[AsyncSession] = None,
    session_factory: Optional[Any] = None,
    redis: Optional[Any] = None,
    require_spell_check_terminal: bool = False,
) -> bool:
    """Atomically claim `book_id` for structure analysis (if eligible) and enqueue `structure_job`."""
    try:
        if redis is None:
            try:
                from app.core.arq import get_arq_pool

                redis = await get_arq_pool()
            except Exception:
                from app.db.redis import get_arq_pool

                redis = await get_arq_pool()
        if redis is None:
            return False

        if session is not None:
            claimed = await claim_books_for_structure(
                session,
                book_ids=[book_id],
                require_spell_check_terminal=require_spell_check_terminal,
                limit=1,
            )
            if claimed:
                await session.commit()
        else:
            if session_factory is None:
                from app.db import session as db_session

                session_factory = db_session.async_session_factory
            if session_factory is None:
                return False
            async with session_factory() as claim_session:
                claimed = await claim_books_for_structure(
                    claim_session,
                    book_ids=[book_id],
                    require_spell_check_terminal=require_spell_check_terminal,
                    limit=1,
                )
                if claimed:
                    await claim_session.commit()

        if not claimed:
            return False

        count = await enqueue_claimed_structure_jobs(
            redis,
            claimed,
            session=session,
            session_factory=session_factory,
        )
        return count > 0
    except Exception as exc:
        logger.debug("Optional structure_job enqueue skipped for %s: %s", book_id, exc)
        return False
