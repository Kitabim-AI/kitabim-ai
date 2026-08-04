"""Pure utility functions for history-term fact deduplication (no I/O, no side-effects)."""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

from app.services.rag.utils import normalize_uyghur_spelling

DUPLICATE_TEXT_SIMILARITY_THRESHOLD = 0.85


def fact_text_similarity(a: str, b: str) -> float:
    """Spelling-normalized similarity ratio between two fact texts (0.0-1.0)."""
    norm_a = normalize_uyghur_spelling(a.strip())
    norm_b = normalize_uyghur_spelling(b.strip())
    if not norm_a or not norm_b:
        return 0.0
    return SequenceMatcher(None, norm_a, norm_b).ratio()


def _digit_sequences(text: str) -> List[str]:
    return re.findall(r"\d+", text)


def find_deterministic_duplicate(
    candidate_text: str,
    existing_facts: List[Dict[str, Any]],
    threshold: float = DUPLICATE_TEXT_SIMILARITY_THRESHOLD,
) -> Optional[int]:
    """Return the id of an existing *active* fact that is a near-exact spelling
    variant of candidate_text (best match above threshold), or None.

    Facts whose digit sequences differ (e.g. different years or counts) are
    never treated as tier-1 duplicates, even at high text similarity — a
    single differing digit is far more likely to be a genuine distinguishing
    fact than spelling noise, so that case is deferred to tier 3 (LLM
    classification), which can tell "same fact, reworded" apart from "same
    shape, different year" (a conflict)."""
    candidate_digits = _digit_sequences(candidate_text)
    best_id: Optional[int] = None
    best_score = 0.0
    for fact in existing_facts:
        if fact.get("status") != "active":
            continue
        fact_text = fact.get("text", "")
        if _digit_sequences(fact_text) != candidate_digits:
            continue
        score = fact_text_similarity(candidate_text, fact_text)
        if score >= threshold and score > best_score:
            best_score = score
            best_id = fact.get("id")
    return best_id


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Cosine similarity between two equal-length embedding vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def merge_citation(existing_fact: Dict[str, Any], new_citation: Dict[str, Any]) -> None:
    """Merge a new citation into an existing fact's citations in-place, unioning
    page numbers when the citation is for a book already cited by this fact."""
    citations = existing_fact.setdefault("citations", [])
    for c in citations:
        if c.get("book_id") == new_citation.get("book_id"):
            c["pages"] = sorted(
                set(c.get("pages", [])) | set(new_citation.get("pages", []))
            )
            return
    citations.append(dict(new_citation))


def bootstrap_legacy_facts(
    facts: List[Dict[str, Any]], definition: Optional[str]
) -> List[Dict[str, Any]]:
    """Defense-in-depth fallback: if a live/staging record still has empty
    `facts` (e.g. created between the 080 migration's bulk bootstrap and this
    code running), wrap its prose `definition` as a single legacy fact so the
    merge pipeline has something to diff new facts against."""
    if facts:
        return facts
    text = (definition or "").strip()
    if not text:
        return []
    return [
        {
            "id": 1,
            "text": text,
            "citations": [],
            "status": "active",
            "conflict_group": None,
        }
    ]
