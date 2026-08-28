from __future__ import annotations

import re
from typing import List, Tuple, Optional


COMMON_OCR_CORRECTIONS: List[Tuple[str, str]] = [
    ("تۆز تىنچى", "تۆتىنچى"),
    ("تۆزتىنچى", "تۆتىنچى"),
    ("تۆتىنچاق", "تۆتىنچى"),
    ("سەككىزد ىنچى", "سەككىزىنچى"),
    ("سەككىزدىنچى", "سەككىزىنچى"),
    ("سەككىزد", "سەككىزىنچى"),
    ("رسەججاد ۇ", "سەججادۇ بەھىشىن"),
    ("رسەججادۇ", "سەججادۇ بەھىشىن"),
    ("سەججادۇ بېھىشىن", "سەججادۇ بەھىشىن"),
    ("سەجادە بېھىشىن", "سەججادۇ بەھىشىن"),
    ("كارامىتۇللا", "كارامەتۇللا"),
    ("مىر راسخور", "مىراسخور"),
    ("گېز ەندىلەر", "گېزەندىلەر"),
    ("گېزەندىلەر", "گېزەندىلەر"),
    ("رەشىدىل", "رەشدىل"),
    ("ئىنەلھەق", "ئەنەلھەق"),
    ("مەرۋايىت", "مەرۋائىت"),
    ("دۇئاغا", "دوئاغا"),
    ("تۈتقان", "تۇتقان"),
    ("ۋەبلىيۇالاز", "ۋەلىيۇللا"),
    ("ئون ئۇچىفچق", "ئون ئۈچىنچى"),
    ("قارغىش ئاداۋەت", "قارغىش - ئاداۋەت"),
    ("قارغىش . ئاداۋەت", "قارغىش - ئاداۋەت"),
    ("چۈز وشكەن", "چۈشكەن"),
    ("چۈزوشكەن", "چۈشكەن"),
    ("چۈز", "چۈشكەن"),
    ("وشكەن", "چۈشكەن"),
    ("قو وغلىنىش", "قوغلىنىش"),
    ("م0م", ""),
]


def apply_auto_corrections(
    text: str, pairs: Optional[List[Tuple[str, str]]] = None
) -> str:
    """
    Apply word-level auto-correction pairs to transcribed Uyghur text.
    Uses regex boundaries that respect Uyghur Arabic script characters.
    """
    if not text:
        return ""

    all_pairs = list(COMMON_OCR_CORRECTIONS)
    if pairs:
        all_pairs.extend(pairs)

    valid_pairs = [
        (wrong.strip(), correct.strip())
        for wrong, correct in all_pairs
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
