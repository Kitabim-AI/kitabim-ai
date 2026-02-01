import re


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    # 1. Join words split by hyphen/dash at line endings (standardizing line breaks)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    # 2. Split into blocks by double newlines (paragraphs)
    blocks = re.split(r"\n\s*\n", text)
    cleaned_blocks = []

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
                
                if is_ending or is_new_item:
                    result_block += line + "\n"
                else:
                    # Join with space if it's clearly part of the same sentence flow
                    result_block += line + " "
            else:
                result_block += line

        cleaned_blocks.append(result_block)

    return "\n\n".join(cleaned_blocks)
