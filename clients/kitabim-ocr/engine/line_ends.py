"""Which words end a printed line with a hyphen, read from the page image.

Surya's full-page OCR reflows each block into running text, so a line-end
hyphen ("ھەز-" / "رىتى" on the next line) comes back as "ھەز - رىتى" and can't
be told apart from a real pair or a dash. Surya's text-line detector still sees
the printed lines: reading just the end of each line (its left edge, since
Uyghur runs right to left) tells us which words were split by a line break.
"""

from __future__ import annotations

import re
import threading
from typing import Any

from bs4 import BeautifulSoup
from PIL import Image

from engine.text_cleanup import normalize_uyghur_chars

# Part of each line, from its left (end) edge, sent for recognition. Narrower
# strips push the recognizer toward Arabic/Persian letter forms and the whole
# line makes it drop the end; 0.6 read the most line ends correctly on a test
# page. The cut-off first word is ignored.
_LINE_END_FRACTION = 0.6
# Lines narrower than this share of the widest line (page numbers, headers,
# short last lines of a paragraph) can't end with a split word.
_MIN_LINE_WIDTH_FRACTION = 0.25
_HYPHENS = "-\u2010\u2011\u2012\u2013\u2014\u00ad\u0640"
# Arabic heh (U+0647) never occurs in Uyghur text; on a line-end crop it is
# the recognizer's reading of Uyghur ae (U+06D5), e.g. "خه-" for "خە-".
_ARABIC_HEH = "\u0647"
_UYGHUR_AE = "\u06d5"
_TRAILING_HYPHEN_RE = re.compile(rf"[\s{re.escape(_HYPHENS)}]+$")

_detector: Any = None
_detector_lock = threading.Lock()


def get_line_detector() -> Any:
    """Return the process-wide Surya text-line detector, loading it on first use."""
    global _detector
    with _detector_lock:
        if _detector is None:
            from surya.detection import DetectionPredictor

            _detector = DetectionPredictor.local()
    return _detector


def read_line_end_words(image: Image.Image, detector: Any, recognizer: Any) -> set[str]:
    """Return the normalized words that end a printed line with a hyphen."""
    from surya.layout.schema import LayoutBox, LayoutResult

    lines = detector([image])[0].bboxes
    if not lines:
        return set()
    widest = max(line.bbox[2] - line.bbox[0] for line in lines)

    boxes: list[LayoutBox] = []
    for line in sorted(lines, key=lambda b: b.bbox[1]):
        x0, y0, x1, y1 = line.bbox
        if x1 - x0 < _MIN_LINE_WIDTH_FRACTION * widest:
            continue
        boxes.append(
            LayoutBox(
                polygon=[x0, y0, x0 + _LINE_END_FRACTION * (x1 - x0), y1],
                label="Text",
                raw_label="Text",
                position=len(boxes),
                count=60,
            )
        )
    if not boxes:
        return set()

    w, h = image.size
    layout = LayoutResult(bboxes=boxes, image_bbox=[0, 0, float(w), float(h)])
    blocks = recognizer([image], [layout], full_page=False)[0].blocks

    words: set[str] = set()
    for block in blocks:
        if block.error or not block.html:
            continue
        line_end = BeautifulSoup(block.html, "html.parser").get_text(" ", strip=True)
        body = _TRAILING_HYPHEN_RE.sub("", line_end)
        tail = line_end[len(body) :]
        if not body or not any(c in _HYPHENS for c in tail):
            continue
        last = body.split()[-1].replace(_ARABIC_HEH, _UYGHUR_AE)
        words.add(normalize_uyghur_chars(last))
    return words


_FOOTNOTE_START_RE = re.compile(r"^\s*(?:[①-⑳]|[¹²³⁴⁵⁶⁷⁸⁹]|\[\d{1,2}\]|\(\d{1,2}\))\s+")
_LINE_END_HYPHEN_WORD_RE = re.compile(
    rf"([\u0600-\u06FFa-zA-Z]{{1,30}})\s*[{re.escape(_HYPHENS)}]\s*$"
)
_LEADING_WORD_FRAGMENT_RE = re.compile(
    r"^(\s*)([\u0600-\u06FFa-zA-Z]{1,16})([\s.,،؛:!؟?\)\]\»”’…\-—–].*|$)",
    re.DOTALL,
)


def _last_body_block_index(blocks: list[str]) -> int | None:
    """Return index of the last non-empty non-footnote body block."""
    for idx in range(len(blocks) - 1, -1, -1):
        block = blocks[idx].strip()
        if not block:
            continue
        first_line = block.split("\n", 1)[0].strip()
        if _FOOTNOTE_START_RE.match(first_line):
            continue
        return idx
    return None


def text_ends_with_hyphen(text: str) -> bool:
    """Return True if the last body block of ``text`` ends with a hyphenated word stem."""
    if not text or not text.strip():
        return False
    blocks = [b for b in re.split(r"\n\s*\n", text.strip()) if b.strip()]
    idx = _last_body_block_index(blocks)
    if idx is None:
        return False
    lines = [line.rstrip() for line in blocks[idx].split("\n") if line.strip()]
    if not lines:
        return False
    last_line = lines[-1]
    if last_line.lstrip().startswith(("#", "|")):
        return False
    return bool(_LINE_END_HYPHEN_WORD_RE.search(last_line))


def read_bottom_line_end_word(
    image: Image.Image, detector: Any, recognizer: Any
) -> str | None:
    """Crop only the bottom body line of ``image`` and return the hyphenated stem if present."""
    from surya.layout.schema import LayoutBox, LayoutResult

    lines = detector([image])[0].bboxes
    if not lines:
        return None
    widest = max(line.bbox[2] - line.bbox[0] for line in lines)
    qualifying = [
        line
        for line in sorted(lines, key=lambda b: b.bbox[1])
        if (line.bbox[2] - line.bbox[0]) >= _MIN_LINE_WIDTH_FRACTION * widest
    ]
    if not qualifying:
        return None
    bottom_line = qualifying[-1]
    x0, y0, x1, y1 = bottom_line.bbox
    box = LayoutBox(
        polygon=[x0, y0, x0 + _LINE_END_FRACTION * (x1 - x0), y1],
        label="Text",
        raw_label="Text",
        position=0,
        count=60,
    )
    w, h = image.size
    layout = LayoutResult(bboxes=[box], image_bbox=[0, 0, float(w), float(h)])
    blocks = recognizer([image], [layout], full_page=False)[0].blocks
    if not blocks:
        return None
    block = blocks[0]
    if block.error or not block.html:
        return None
    line_end = BeautifulSoup(block.html, "html.parser").get_text(" ", strip=True)
    body = _TRAILING_HYPHEN_RE.sub("", line_end)
    tail = line_end[len(body) :]
    if not body or not any(c in _HYPHENS for c in tail):
        return None
    last = body.split()[-1].replace(_ARABIC_HEH, _UYGHUR_AE)
    return normalize_uyghur_chars(last)


def join_cross_page_hyphenated_words(
    prev_text: str,
    next_text: str,
    *,
    verified_stem: str | None = None,
) -> tuple[str, str]:
    """Join a word split by a line-break hyphen across contiguous body pages ``(p, p + 1)``.

    Moves the leading word fragment of ``next_text`` onto the hyphenated stem at the end
    of ``prev_text``'s last body block and strips the trailing hyphen. Leaves both pages
    unchanged if ``prev_text`` does not end with a hyphen (or ``verified_stem``) or if
    ``next_text`` begins with a heading, table, dialogue dash, or footnote.
    """
    if not prev_text or not next_text:
        return prev_text, next_text

    prev_blocks = [b for b in re.split(r"\n\s*\n", prev_text.strip()) if b.strip()]
    next_blocks = [b for b in re.split(r"\n\s*\n", next_text.strip()) if b.strip()]
    if not prev_blocks or not next_blocks:
        return prev_text, next_text

    prev_idx = _last_body_block_index(prev_blocks)
    if prev_idx is None:
        return prev_text, next_text

    first_next = next_blocks[0].strip()
    if first_next.startswith(("#", "|", "—", "–", "-")) or _FOOTNOTE_START_RE.match(
        first_next
    ):
        return prev_text, next_text

    prev_lines = [
        line.rstrip() for line in prev_blocks[prev_idx].split("\n") if line.strip()
    ]
    if not prev_lines:
        return prev_text, next_text

    last_line = prev_lines[-1]
    m_end = _LINE_END_HYPHEN_WORD_RE.search(last_line)
    if not m_end:
        if verified_stem and last_line.endswith(verified_stem):
            stem = verified_stem
            prefix_line = last_line[: len(last_line) - len(verified_stem)]
        else:
            return prev_text, next_text
    else:
        stem = m_end.group(1)
        if verified_stem and normalize_uyghur_chars(stem) != normalize_uyghur_chars(
            verified_stem
        ):
            return prev_text, next_text
        prefix_line = last_line[: m_end.start()]

    m_next = _LEADING_WORD_FRAGMENT_RE.match(first_next)
    if not m_next:
        return prev_text, next_text

    _, fragment, remainder = m_next.groups()
    remainder = remainder.lstrip()

    prev_lines[-1] = f"{prefix_line}{stem}{fragment}"
    prev_blocks[prev_idx] = "\n".join(prev_lines)

    if remainder:
        next_blocks[0] = remainder
    else:
        next_blocks.pop(0)

    return "\n\n".join(prev_blocks), "\n\n".join(next_blocks)


def apply_cross_page_dehyphenation(
    pages: list[Any],
    fresh_page_numbers: set[int] | None = None,
    hyphen_ended_pages: set[int] | None = None,
) -> int:
    """Apply cross-page dehyphenation across contiguous freshly OCR'd body page pairs.

    Returns the number of page boundaries where a hyphenated word was joined.
    """
    by_num = {p.page_number: p for p in pages}
    sorted_nums = sorted(by_num)
    joined_count = 0

    for p_num in sorted_nums:
        next_num = p_num + 1
        if next_num not in by_num:
            continue
        if fresh_page_numbers is not None and (
            p_num not in fresh_page_numbers or next_num not in fresh_page_numbers
        ):
            continue

        curr_p = by_num[p_num]
        next_p = by_num[next_num]
        if (
            curr_p.is_toc
            or next_p.is_toc
            or getattr(curr_p, "skipped", False)
            or getattr(next_p, "skipped", False)
            or curr_p.status == "failed"
            or next_p.status == "failed"
        ):
            continue

        if hyphen_ended_pages is not None:
            is_hyphen_end = p_num in hyphen_ended_pages or text_ends_with_hyphen(
                curr_p.text
            )
        else:
            is_hyphen_end = text_ends_with_hyphen(curr_p.text)

        if not is_hyphen_end:
            continue

        new_prev, new_next = join_cross_page_hyphenated_words(curr_p.text, next_p.text)
        if new_prev != curr_p.text or new_next != next_p.text:
            curr_p.text = new_prev
            next_p.text = new_next
            joined_count += 1

    return joined_count
