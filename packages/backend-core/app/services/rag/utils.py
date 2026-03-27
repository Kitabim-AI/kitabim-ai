"""Pure utility functions for RAG service (no I/O, no side-effects)."""
from __future__ import annotations

import re
from typing import List, Optional

import numpy as np

from app.core.i18n import t


# ---------------------------------------------------------------------------
# Uyghur character normalization
# ---------------------------------------------------------------------------

def normalize_uyghur(text: str) -> str:
    """Normalize Uyghur character variants for reliable keyword matching.

    ې (U+06D0) and ي (U+064A) are often used interchangeably with
    ى (U+06CC) depending on keyboard/input method.
    """
    return (
        text
        .replace("\u06D0", "\u06CC")
        .replace("\u0649", "\u06CC")
        .replace("\u064A", "\u06CC")
    )


def entity_matches_question(entity: str, question: str) -> bool:
    """Return True if an author name or book title is referenced in the question.

    Handles Uyghur agglutinative suffixes (e.g. 'سابىر' matches 'سابىرنىڭ').
    Each word of the entity must appear as a prefix of at least one word in
    the question.  Single-word entities are allowed when they are at least 4
    characters long (avoids false positives on short tokens).  Normalizes
    ى/ې/ي variants before comparison.
    """
    entity_words = normalize_uyghur(entity.strip()).split()
    if not entity_words:
        return False
    if len(entity_words) == 1 and len(entity_words[0]) < 4:
        return False
    _PUNCT = "«»،؟!()[]{}\"""''"
    q_words = [
        normalize_uyghur(w).strip(_PUNCT)
        for w in question.strip().split()
    ]
    return all(
        any(q_word.startswith(e_word) for q_word in q_words)
        for e_word in entity_words
    )


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

def is_current_volume_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    keywords = [
        "ئۇشبۇ تومدا", "ئۇشبۇ قىسىمدا",
        "مەزكور تومدا", "مەزكور قىسىمدا",
        "بۇ تومدا", "بۇ قىسىمدا",
    ]
    return any(k in q for k in keywords)


def is_current_page_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    keywords = ["ئۇشبۇ بەتتە", "مەزكور بەتتە", "بۇ بەتتە"]
    return any(k in q for k in keywords)


def is_author_or_catalog_query(question: str) -> bool:
    """Detect if the question is about book authors or which books exist in the library."""
    if not question:
        return False
    q = normalize_uyghur(question.strip())
    keywords = [
        # Author-related — "who wrote X" / "author of X"
        "مۇئەللىپ", "مۇئەللىپى", "يازغۇچى", "يازغۇچىسى", "ئاپتور", "ئاپتورى",
        "كىم يازغان", "يازغان كىشى", "يازغان كىم",
        "كىم تەرىپىدىن", "يازغانلىقى", "كىمنىڭ", "كىمنىكى",
        # Author-related — "X's books / works"
        "ئەسەر يازغان", "ئەسەرلىرى", "كىتابلىرى",
        # Catalog / book-list related
        "كىتابلىرىڭىز", "كىتاب بارمۇ", "كىتابخانىڭىز",
        "كىتاب تىزىملىكى", "قانچە كىتاب", "نەچچە كىتاب",
        "قايسى كىتابلار", "قايسى ئەسەر",
    ]
    normalized_keywords = [normalize_uyghur(k) for k in keywords]
    return any(k in q for k in normalized_keywords)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def extract_keywords(question: str) -> List[str]:
    tokens = [re.sub(r"[^\w]", "", k, flags=re.UNICODE).strip() for k in question.split()]
    return [k for k in tokens if len(k) > 2]


def expand_history_categories(categories: List[str]) -> List[str]:
    """When تارىخ is matched, also include ئۇيغۇر تارىخى and ئىسلام تارىخى."""
    if "تارىخ" in categories:
        extra = [c for c in ["ئۇيغۇر تارىخى", "ئىسلام تارىخى"] if c not in categories]
        return categories + extra
    return categories


def format_chat_history(history: List[dict]) -> str:
    if not history:
        return "No previous conversation."
    formatted = []
    for msg in history[-6:]:  # Limit to last 6 turns
        role = "User" if msg.get("role") == "user" else "AI"
        text = msg.get("text", "").replace("\n", " ").strip()
        formatted.append(f"{role}: {text}")
    return "\n".join(formatted)


def build_empty_response_message() -> str:
    return t("errors.chat_no_context")


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    if not v1 or not v2:
        return 0.0
    a = np.array(v1)
    b = np.array(v2)
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def format_book_catalog(books) -> str:
    """Format a list of Book ORM objects as LLM context."""
    if not books:
        return "NO BOOKS FOUND IN THE LIBRARY."
    lines = ["Library catalog — available books:"]
    for book in books:
        title = book.title or "Unknown"
        author = book.author
        if author:
            lines.append(f"- {title} (Author: {author})")
        else:
            lines.append(f"- {title}")
    return "\n".join(lines)
