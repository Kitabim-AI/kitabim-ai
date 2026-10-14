"""Book category normalization.

Applied on every category write (book update endpoint) and mirrored by
migration 099, which cleaned the existing data. Keep CATEGORY_ALIASES and the
mapping in migrations/099_normalize_book_categories.sql identical —
tests/app/utils/categories_test.py checks this.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional

# Invisible characters that made visually identical categories distinct
# (e.g. "ئ‍ىسلام" vs "ئىسلام"): zero-width space, zero-width joiner, BOM.
_INVISIBLE = re.compile("[​‍﻿]")

# Variant → canonical category name. Chosen by the project owner on
# 2026-10-14 (spelling variants and singular → plural merges).
CATEGORY_ALIASES: dict[str, str] = {
    "مۇۋاپېقىيەتشۇناسلىق": "مۇۋەپپەقىيەتشۇناسلىق",
    "مۇۋاپپىقىيەتشۇناسلىق": "مۇۋەپپەقىيەتشۇناسلىق",
    "ماقالىلار": "ماقالىلەر",
    "نەسرلەر": "نەسىرلەر",
    "ئەدەبىي ئاخبارات": "ئەدەبىي ئاخباراتلار",
    "ئوچېرك": "ئوچېركلار",
    "داستان": "داستانلار",
    "پوۋېست": "پوۋېستلار",
    "ئەدەبىي خاتىرە": "ئەدەبىي خاتىرىلەر",
    "تەزكىرە": "تەزكىرىلەر",
}


def normalize_category(category: str) -> str:
    """Strip invisible characters, surrounding whitespace and quotes, then map
    a known variant to its canonical name. Returns "" for an empty category."""
    cleaned = _INVISIBLE.sub("", category).strip().strip('"').strip()
    return CATEGORY_ALIASES.get(cleaned, cleaned)


def normalize_categories(categories: Optional[Iterable[object]]) -> List[str]:
    """Normalize each category, dropping empties and non-strings, and remove
    duplicates while keeping the first occurrence's position."""
    if not categories:
        return []
    result: List[str] = []
    seen: set[str] = set()
    for category in categories:
        if not isinstance(category, str):
            continue
        normalized = normalize_category(category)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result
