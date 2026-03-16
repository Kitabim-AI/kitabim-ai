import re
import unicodedata

# ── Arabic Presentation Forms Normalization ───────────────────────────────────
# Pre-calculate mapping for performance. range(0xFB50, 0xFE00) and range(0xFE70, 0xFF00)
# contain the Arabic presentation forms A and B.
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
    
    # 1. Standardize presentation forms (ﻼ -> لا) BEFORE anything else
    # This is critical for search consistency but changes string length.
    text = "".join(_PRES_FORM_MAP.get(ord(c), c) for c in text)

    # 2. Normalize common OCR artifacts (invisible characters)
    return (
        text.replace("\u064A\u0654", "\u0626")  # ئ (Yeh + Hamza) -> ئ (Hamza seat)
        .replace("\u200C", "")   # Remove ZWNJ
        .replace("\u200D", "")   # Remove ZWJ
        .replace("\u200B", "")   # Remove Zero-width space
        .replace("\u0640", "")   # Remove Tatweel/Kashida
    )

def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    text = normalize_uyghur_chars(text)

    # 1. Join words split by hyphen/dash at line endings (standardizing line breaks)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    # 2. Split into blocks by double newlines (paragraphs)
    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    dot_leader_pattern = re.compile(r"(?:[\.·•∙⋅․﹒｡]\s*){3,}|…{2,}")
    list_marker_pattern = re.compile(r"^\s*([-—–*•]|\d+[.)])\s+")
    header_prefixes = ("[Header]", "[Footer]", "#", "|")

    for block in blocks:
        if not block.strip():
            continue
        
        # We split by single newline to process lines within a block
        # DO NOT use line.strip() here as it kills indentation
        lines = [line.rstrip() for line in block.split("\n") if line.strip()]
        if not lines:
            continue

        result_block = ""
        for idx, line in enumerate(lines):
            # If line has leading spaces, it's likely intentional indentation
            # We preserve it.
            if idx < len(lines) - 1:
                next_line = lines[idx + 1]
                is_ending = re.search(r"[.؟!:؛»\"”)\]}﴾﴿…]\s*$", line)
                
                # A line is a "New Item" (list) only if the previous line ended a sentence.
                # Otherwise, it's just a continuation (like a mid-line dash).
                raw_next = next_line.lstrip()
                is_list_marker = raw_next and raw_next[0] in "-—–*•"
                is_digit_marker = raw_next and raw_next[0].isdigit() and (len(raw_next) > 1 and raw_next[1] in ". )")
                
                is_new_item = is_ending and (is_list_marker or is_digit_marker)

                raw_line = line.lstrip()
                is_markdown_list = bool(list_marker_pattern.match(raw_line))
                is_markdown_header = raw_line.startswith(header_prefixes)
                is_toc_line = bool(dot_leader_pattern.search(line))
                
                if is_markdown_list or is_markdown_header or is_toc_line or is_ending or is_new_item or is_list_marker or is_digit_marker:
                    result_block += line + "\n"
                else:
                    # Join with space if it's clearly part of the same sentence flow
                    result_block += line + " "
            else:
                result_block += line

        cleaned_blocks.append(result_block)

    return "\n\n".join(cleaned_blocks)


def generate_uyghur_regex(q: str) -> str:
    """
    Generate a regex that handles common Uyghur character variants
    (like the multiple ways to encode 'ئ' and 'ۇ').
    """
    if not q:
        return ""
    
    # 1. Escape regex special characters first
    res = re.escape(q)
    
    # Define mapping of single character/sequence to a common group
    # We work on the string after re.escape(), so we use escaped keys
    norm_map = {
        re.escape("\u0626"): "(\u0626|\u064A\u0654)",
        re.escape("\u064A\u0654"): "(\u0626|\u064A\u0654)",
    }
    
    # Use a single-pass regex substitution to avoid nested/double replacements
    # Sort keys by length descending to match longer sequences (like ئ) first.
    pattern = re.compile("|".join(sorted(norm_map.keys(), key=len, reverse=True)))
    
    return pattern.sub(lambda m: norm_map[m.group(0)], res)
