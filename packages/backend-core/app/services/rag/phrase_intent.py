"""Detect exact-phrase search intent (Phase 1 of the keyword-search rework).

The keyword (lexical) retrieval leg only runs when the user genuinely wants
an exact match: a quoted phrase, or the explicit UI "Exact phrase" mode.
Everything else is answered by vector + graph retrieval.

`«...»` used to also mark a quoted book title (see
`find_books_by_title_in_question` / `entity_matches_question`); it is now
reserved exclusively for phrase-search intent, and those call sites fall
back to their non-quote heuristics instead.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

_QUOTE_PATTERN = re.compile(r'"([^"]+)"|«([^»]+)»|“([^”]+)”')

# English examples given by the plan; add localized equivalents alongside
# these once product/content supplies vetted (non-machine-translated)
# Uyghur phrasing for the same page-finding intent.
_PAGE_FINDING_MARKERS = (
    "find pages with",
    "which pages mention",
    "show me where",
)


@dataclass
class PhraseIntent:
    is_exact: bool
    phrases: List[str] = field(default_factory=list)
    is_page_finding: bool = False

    @property
    def phrase(self) -> str | None:
        """Single-phrase convenience accessor; None when no phrase applies."""
        return self.phrases[0] if self.phrases else None


def _extract_quoted_phrases(text: str) -> List[str]:
    phrases = []
    for match in _QUOTE_PATTERN.finditer(text):
        phrase = next(g for g in match.groups() if g is not None).strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def _is_page_finding_request(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _PAGE_FINDING_MARKERS)


def detect_phrase_intent(text: str, exact_phrase_flag: bool = False) -> PhraseIntent:
    """Classify *text* as exact-phrase search intent, or not.

    Quoted spans (`"..."`, `«...»`, `“...”`) always trigger exact-phrase
    intent; multiple quoted phrases in one query are ANDed together by the
    retrieval leg. `exact_phrase_flag` covers the explicit UI "Exact phrase"
    mode, where the whole (unquoted) text is the phrase.
    """
    stripped = text.strip()
    if not stripped:
        return PhraseIntent(is_exact=False)

    phrases = _extract_quoted_phrases(stripped)
    if phrases:
        return PhraseIntent(
            is_exact=True,
            phrases=phrases,
            is_page_finding=_is_page_finding_request(stripped),
        )

    if exact_phrase_flag:
        return PhraseIntent(is_exact=True, phrases=[stripped], is_page_finding=False)

    return PhraseIntent(is_exact=False)
