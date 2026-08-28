from __future__ import annotations

import re
from typing import List, Tuple


def apply_auto_corrections(text: str, pairs: List[Tuple[str, str]]) -> str:
    """
    Apply word-level auto-correction pairs to transcribed Uyghur text.
    Uses regex boundaries that respect Uyghur Arabic script characters.
    """
    if not text or not pairs:
        return text

    valid_pairs = [
        (wrong.strip(), correct.strip())
        for wrong, correct in pairs
        if wrong.strip() and wrong.strip() != correct.strip()
    ]
    if not valid_pairs:
        return text

    # Sort pairs by length descending to match longer specific words first
    valid_pairs.sort(key=lambda p: len(p[0]), reverse=True)

    result = text
    for wrong, correct in valid_pairs:
        pattern = re.compile(
            rf"(?<![\u0600-\u06FF\w]){re.escape(wrong)}(?![\u0600-\u06FF\w])"
        )
        result = pattern.sub(correct, result)

    return result
