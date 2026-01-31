import re


def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""

    # Join words split by hyphen/dash at line endings
    text = re.sub(r"(\w)[-—–_]\s*\n\s*(\w)", r"\1\2", text)

    # Standardize hyphens/dashes at line ends
    text = re.sub(r"(\w)[-—–_]\s*\n\s*", r"\1", text)

    # Remove tatweels at line breaks
    text = re.sub(r"ـ+\s*\n\s*", "", text)

    # Split by paragraphs (double newlines or more)
    paragraphs = re.split(r"\n\s*\n", text)
    cleaned_paragraphs = []

    for para in paragraphs:
        if not para.strip():
            continue

        lines = [line.strip() for line in para.split("\n") if line.strip()]
        if not lines:
            continue

        result_para = ""
        for idx, line in enumerate(lines):
            if idx < len(lines) - 1:
                next_line = lines[idx + 1]
                is_ending = re.search(r"[.؟!:؛»\"”)\]}﴾﴿…]\s*$", line)
                is_new_item = re.match(r"^\s*([-—–*•\d])", next_line)
                if is_ending or is_new_item:
                    result_para += line + "\n"
                else:
                    result_para += line + " "
            else:
                result_para += line

        cleaned_paragraphs.append(result_para.strip())

    return "\n\n".join(cleaned_paragraphs)
