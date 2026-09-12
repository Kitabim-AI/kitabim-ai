"""Detect "locate a named short work" intent -- a question asking to find,
show, or describe the content of a specific poem/song/short piece by title,
as opposed to a book-level question or a generic content question.

This is a deterministic, non-LLM-discretionary gate (mirrors
``phrase_intent.py``'s exact-phrase gate): the retrieval agent's own system
prompt already tells it when to reach for lexical search on "titles of
short works," but that's prose the model can silently fail to follow --
exactly the root cause of poem-title lookups failing in production.
Deciding this in code, before the agent loop ever runs, removes that
dependency on model compliance entirely.

Book-vs-short-work disambiguation: the existing catalog-first resolution
(``find_books_by_title_in_question``, run earlier in the orchestrator)
already matches quoted spans against real book titles, so by the time this
classifier runs, a quote naming a real book has already been consumed into
``ctx.context_book_ids``. This classifier only picks the candidate
short-work title out of the question text; book scoping from there is the
caller's job (see ``toc_lookup_service.resolve_short_work``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

# Same quote marks phrase_intent.py's exact-phrase gate recognizes -- Uyghur
# text uses «...» (guillemets) as its quotation convention, plus the
# straight/curly double-quote variants some inputs use. Duplicated (not
# imported) so each module stays independently readable, but must stay in
# sync with phrase_intent._QUOTE_PATTERN.
_QUOTE_PATTERN = re.compile(r'"([^"]+)"|«([^»]+)»|“([^”]+)”')

# Verbs/phrasings that mean "locate/show/give the content of X" -- drawn
# directly from real production queries that failed to find a named poem.
# Deliberately narrow: a broader net risks misclassifying a book-level or
# open-ended question as a short-work lookup.
_LOCATE_MARKERS = (
    "تېپىپ بەر",  # "find/locate and give [it]"
    "كۆرسەت",  # "show [it]"
    "تولۇق تېكىستى",  # "full text of"
    "تېكىستى قانداق",  # "what does the text say"
    "مەزمۇنى",  # "content/theme of" -- ambiguous alone (could mean "explain"
    # rather than "show me"), but included because it's the exact phrasing
    # used in real failing queries; the Answer Agent can still synthesize
    # an explanation once handed the real content.
)

# Authorship questions ("whose work is «X»?") are already handled by the
# existing get_book_author path and want a book-level author lookup, not
# this work's raw page content -- excluded so this classifier doesn't
# compete with that path.
_AUTHORSHIP_MARKERS = (
    "كىمنىڭ ئەسىرى",
    "كىمگە تەئەللۇق",
    "ئاپتورى كىم",
)


@dataclass(frozen=True)
class ShortWorkIntent:
    applies: bool
    title: Optional[str] = None


def _extract_quoted_phrases(text: str) -> List[str]:
    phrases = []
    for match in _QUOTE_PATTERN.finditer(text):
        phrase = next(g for g in match.groups() if g is not None).strip()
        if phrase:
            phrases.append(phrase)
    return phrases


def detect_short_work_intent(text: str) -> ShortWorkIntent:
    """Classify *text* as a "locate this named short work" question.

    Exactly one quoted span -> that span is the candidate title.
    Exactly two quoted spans (the "«book» ناملىق ئەسەردىكى «work»" shape)
    -> the SECOND span is the candidate title (the first is presumed
    already resolved as a book title further upstream, if it is one).
    Zero, or more than two, quoted spans -> does not apply.
    """
    stripped = text.strip()
    if not stripped:
        return ShortWorkIntent(applies=False)

    if any(marker in stripped for marker in _AUTHORSHIP_MARKERS):
        return ShortWorkIntent(applies=False)

    if not any(marker in stripped for marker in _LOCATE_MARKERS):
        return ShortWorkIntent(applies=False)

    phrases = _extract_quoted_phrases(stripped)
    if len(phrases) == 1:
        return ShortWorkIntent(applies=True, title=phrases[0])
    if len(phrases) == 2:
        return ShortWorkIntent(applies=True, title=phrases[1])

    return ShortWorkIntent(applies=False)
