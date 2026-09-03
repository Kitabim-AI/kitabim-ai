"""Vendored from packages/backend-core/app/utils/text.py (kitabim-ai main
repo). Copied, not imported, so this client stays free of backend-core's
FastAPI/SQLAlchemy/Neo4j dependency chain. Keep in sync manually if the
source functions change - the source of truth is the main repo."""

import re
import unicodedata
from collections import Counter

_PRES_FORM_MAP: dict[int, str] = {}
for _cp in range(0xFB50, 0xFE00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf
for _cp in range(0xFE70, 0xFF00):
    _nf = unicodedata.normalize("NFKC", chr(_cp))
    if _nf != chr(_cp):
        _PRES_FORM_MAP[_cp] = _nf


def normalize_uyghur_chars(text: str) -> str:
    if not text:
        return ""

    text = "".join(_PRES_FORM_MAP.get(ord(c), c) for c in text)

    return (
        text.replace("ئ", "ئ")  # ئ (Yeh + Hamza) -> ئ (Hamza seat)
        .replace("\u064a\u0654", "\u0626")
        .replace("ة", "ە")  # Arabic Teh Marbuta -> Uyghur E
        .replace("ہ", "ە")  # Urdu Heh Goal -> Uyghur E
        .replace("ے", "ې")  # Urdu Bari Ye -> Uyghur E
        .replace("‌", "")  # Remove ZWNJ
        .replace("‍", "")  # Remove ZWJ
        .replace("​", "")  # Remove Zero-width space
        .replace("ـ", "")  # Remove Tatweel/Kashida
    )


_OCR_MARKER_RE = re.compile(r"\s*\[(?:Header|Footer)\].*", re.IGNORECASE)

_PAGE_NUMBER_RE = re.compile(
    r"""^\s*
    (?:
        # Decorated / standalone digits: e.g. "- 4 -", "( 12 )", "[3]", "· 4 ·", "4", "— 123 —"
        (?:[-—–•·*#\(\[\{/\\~]\s*)*
        [0-9\u0660-\u0669\u06F0-\u06F9]{1,4}
        (?:\s*[-—–•·*#\)\]\}/\\~])*
        |
        # Uyghur / English page labels: e.g. "4 - بەت", "بەت: 4", "Page 4", "p. 4"
        (?:بەت|page|p\.)\s*[:\-\s]*[0-9\u0660-\u0669\u06F0-\u06F9]{1,4}
        |
        [0-9\u0660-\u0669\u06F0-\u06F9]{1,4}\s*[:\-]?\s*(?:بەت|page)
    )\s*$""",
    re.IGNORECASE | re.VERBOSE,
)


def is_isolated_page_number(text: str) -> bool:
    """Return True if text is a standalone page number, decorated digit, or page label."""
    if not text:
        return False
    return bool(_PAGE_NUMBER_RE.match(text.strip()))


def strip_page_numbers(text: str) -> str:
    """Strip isolated header and footer page numbers from the top and bottom of page text."""
    if not text:
        return ""

    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    if not blocks:
        return ""

    # Strip trailing footer page numbers
    while blocks and is_isolated_page_number(blocks[-1]):
        blocks.pop()

    # Strip leading header page numbers
    while blocks and is_isolated_page_number(blocks[0]):
        blocks.pop(0)

    if not blocks:
        return ""

    # Check if the very last line of the last block is an isolated page number
    last_lines = [line for line in blocks[-1].split("\n") if line.strip()]
    if len(last_lines) > 1 and is_isolated_page_number(last_lines[-1]):
        last_lines.pop()
        blocks[-1] = "\n".join(last_lines)

    # Check if the very first line of the first block is an isolated page number
    first_lines = [line for line in blocks[0].split("\n") if line.strip()]
    if len(first_lines) > 1 and is_isolated_page_number(first_lines[0]):
        first_lines.pop(0)
        blocks[0] = "\n".join(first_lines)

    return "\n\n".join(b for b in blocks if b.strip())


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    # 1. Normalize characters
    text = normalize_uyghur_chars(text)

    # 2. Strip OCR markers
    text = "\n".join(_OCR_MARKER_RE.sub("", line) for line in text.splitlines())

    # 3. Strip header and footer page numbers
    text = strip_page_numbers(text)

    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    dot_leader_pattern = re.compile(r"(?:[\.·•∙⋅․﹒｡]\s*){3,}|…{2,}")
    list_marker_pattern = re.compile(r"^\s*([-—–*•]|\d+[.)])\s+")
    header_prefixes = ("[Header]", "[Footer]", "#", "|")

    for block in blocks:
        if not block.strip():
            continue

        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        result_block = ""
        for idx, line in enumerate(lines):
            if idx < len(lines) - 1:
                next_line = lines[idx + 1]
                is_ending = re.search(r"[.؟!:؛»\"”)\]}﴾﴿…]\s*$", line)

                raw_next = next_line.lstrip()
                is_list_marker = raw_next and raw_next[0] in "-—–*•"
                is_digit_marker = (
                    raw_next
                    and raw_next[0].isdigit()
                    and (len(raw_next) > 1 and raw_next[1] in ". )")
                )

                is_new_item = is_ending and (is_list_marker or is_digit_marker)

                raw_line = line.lstrip()
                is_markdown_list = bool(list_marker_pattern.match(raw_line))
                is_markdown_header = raw_line.startswith(header_prefixes)
                is_toc_line = bool(dot_leader_pattern.search(line))
                # A following header/table-row line must never get the current
                # line's content merged into its front - check the *next*
                # line's own prefix too, not just the current line's.
                is_next_markdown_header = raw_next.startswith(header_prefixes)

                if (
                    is_markdown_list
                    or is_markdown_header
                    or is_toc_line
                    or is_ending
                    or is_new_item
                    or is_list_marker
                    or is_digit_marker
                    or is_next_markdown_header
                ):
                    result_block += line + "\n"
                else:
                    result_block += line + " "
            else:
                result_block += line

        cleaned_blocks.append(result_block)

    cleaned = "\n\n".join(cleaned_blocks)
    return strip_page_numbers(cleaned)


def is_toc_page(text: str) -> bool:
    if not text:
        return False

    if "مۇندەرىجە" in text:
        return True

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines:
        return False

    pipe_table_pattern = re.compile(r"^\|.*\|\s*\d+\s*\|?$")
    pipe_count = sum(1 for line in lines if pipe_table_pattern.match(line))
    if pipe_count >= 5 and (pipe_count / len(lines)) >= 0.5:
        return True

    dot_leader_pattern = re.compile(r"(\.{6,}|_{6,}|-{6,}|·{6,})")

    dot_digit_count = 0
    edge_digits = []

    for line in lines:
        has_dots = bool(dot_leader_pattern.search(line))
        digit_match = re.search(r"(^\d+)|(\d+$)", line)

        if has_dots and digit_match:
            dot_digit_count += 1
            edge_digits.append(int(digit_match.group()))
        elif digit_match:
            edge_digits.append(int(digit_match.group()))

    if len(edge_digits) >= 5 and dot_digit_count >= 3:
        non_decreasing = sum(
            1
            for i in range(len(edge_digits) - 1)
            if edge_digits[i + 1] >= edge_digits[i]
        )
        is_increasing = (non_decreasing / (len(edge_digits) - 1)) >= 0.8

        if is_increasing and dot_digit_count >= (len(lines) * 0.3):
            return True

    if dot_digit_count >= 5 and (dot_digit_count / len(lines)) >= 0.5:
        return True

    return False


_MAX_SANE_OCR_CHARS = 10000


def is_degenerate_ocr_output(text: str) -> bool:
    if not text:
        return False
    if len(text) > _MAX_SANE_OCR_CHARS:
        return True

    words = [w for w in text.split() if any(ch.isalnum() for ch in w)]
    if len(words) < 30:
        return False
    _, most_common_count = Counter(words).most_common(1)[0]
    return most_common_count >= 20 and (most_common_count / len(words)) >= 0.2
