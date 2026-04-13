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

# Matches OCR structural marker lines: "[Header] ..." or "[Footer] ..."
_OCR_MARKER_LINE = re.compile(r"^\s*\[(Header|Footer)\]", re.IGNORECASE)


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    text = normalize_uyghur_chars(text)

    # 1. Strip OCR structural marker lines ([Header] ..., [Footer] ...)
    text = "\n".join(
        line for line in text.splitlines()
        if not _OCR_MARKER_LINE.match(line)
    )

    # 3. Join words split by hyphen/dash at line endings (standardizing line breaks)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    # 4. Split into blocks by double newlines (paragraphs)
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

def is_toc_page(text: str) -> bool:
    """
    Detect if a page is likely a Table of Contents. 
    
    Supports:
    1. Modern pipe tables (OCR_PROMPT output: "| Title | 123 |")
    2. Old book styles with dot leaders (dot_leader_pattern: "Title ....... 123")
    3. Keyword identification ("مۇندەرىجە")
    
    To avoid false positives from numbered lists, numeric sequences are ONLY 
    considered when paired with structural markers like pipe tables or dot leaders.
    """
    if not text:
        return False
    
    # 1. Simple keyword check: "مۇندەرىجە" (Munderije - Table of contents)
    # This is a very strong signal.
    if "مۇندەرىجە" in text:
        return True

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False
        
    # Pattern 1: Modern Pipe Tables (highly specific to our OCR output)
    pipe_table_pattern = re.compile(r"^\|.*\|\s*\d+\s*\|?$")
    pipe_count = sum(1 for line in lines if pipe_table_pattern.match(line))
    if pipe_count >= 5 and (pipe_count / len(lines)) >= 0.5:
        return True

    # Pattern 2: Dot/Dash Leaders (Standard TOC style)
    # Must have a significant sequence of dot leaders (at least 6 characters)
    dot_leader_pattern = re.compile(r"(\.{6,}|_{6,}|-{6,}|·{6,})")
    
    dot_digit_count = 0
    edge_digits = []
    
    for line in lines:
        has_dots = bool(dot_leader_pattern.search(line))
        # Match digits at edges (where page numbers live)
        digit_match = re.search(r"(^\d+)|(\d+$)", line)
        
        if has_dots and digit_match:
            dot_digit_count += 1
            edge_digits.append(int(digit_match.group()))
        elif digit_match:
            # We track edge digits even without dots for progression check
            # but we require dots to be present to avoid regular numbered lists.
            edge_digits.append(int(digit_match.group()))
            
    # Pattern 3: Numeric Progression combined with dot leaders
    # Check if numbers at the edges are mostly non-decreasing
    if len(edge_digits) >= 5 and dot_digit_count >= 3:
        non_decreasing = sum(1 for i in range(len(edge_digits)-1) if edge_digits[i+1] >= edge_digits[i])
        is_increasing = (non_decreasing / (len(edge_digits)-1)) >= 0.8
        
        # If the page has non-decreasing edge numbers AND many dot leaders, it's a TOC.
        # dot_digit_count check prevents regular lists (1. , 2. ) from matching 
        # unless they also use dot leaders to page numbers.
        if is_increasing and dot_digit_count >= (len(lines) * 0.3):
            return True
        
    # Final fallback: Density of dot leader lines
    if dot_digit_count >= 5 and (dot_digit_count / len(lines)) >= 0.5:
        return True
        
    return False


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
