import re


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    # Normalize common OCR character variants
    text = text.replace("ی", "ي").replace("ه", "ە")

    # 1. Join words split by hyphen/dash at line endings (standardizing line breaks)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    # 2. Split into blocks by double newlines (paragraphs)
    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

    dot_leader_pattern = re.compile(r"(?:[\.·•∙⋅․﹒｡]\s*){3,}|…{2,}")
    list_marker_pattern = re.compile(r"^\s*([-—–*•]|\d+[.)])\s+")
    header_prefixes = ("[Header]", "[Footer]", "#")

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
    (like the multiple ways to encode 'ئ').
    """
    if not q:
        return ""
    
    # 1. Escape regex special characters
    res = re.escape(q)
    
    # 2. Handle 'ئ' (U+0626) and 'ئ' (U+064A + U+0654)
    # The user might type either, and the DB might contain either.
    # We replace any form of hemza-carrier with a group that matches both.
    hemza_variants = [
        "\u0626",          # ئ (Standard)
        "\u064A\u0654",    # ئ (Decomposed)
    ]
    
    for variant in hemza_variants:
        res = res.replace(re.escape(variant), f"({'|'.join(hemza_variants)})")
        
    return res
