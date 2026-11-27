"""Pure utility functions for RAG service (no I/O, no side-effects)."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import List

import numpy as np

from app.core.i18n import t


# ---------------------------------------------------------------------------
# Uyghur character normalization
# ---------------------------------------------------------------------------


def normalize_uyghur(text: str) -> str:
    """Normalize Uyghur character variants and strip invisible joiners/formatters.

    ې (U+06D0), ۑ (U+06D1), ى (U+0649), and ي (U+064A) are often used
    interchangeably with ی (U+06CC) depending on keyboard/input method.
    Zero-width joiners/spaces (U+200B/C/D), tatweel (U+0640), and BOM (U+FEFF)
    frequently appear inside Uyghur words from keyboards/copy-paste (e.g.
    ``ئ\\u200dۆتكۈرنىڭ``) and must be stripped before matching.
    """
    return (
        text.replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\u0640", "")
        .replace("\ufeff", "")
        .replace("\u06d0", "\u06cc")
        .replace("\u06d1", "\u06cc")
        .replace("\u0649", "\u06cc")
        .replace("\u064a", "\u06cc")
    )


def normalize_uyghur_spelling(text: str) -> str:
    """Normalize Uyghur character variants and collapse duplicate letter variants.

    Handles common orthographical variations like double-y (ىى/ىي/يى/يي) vs single-y.
    """
    if not text:
        return ""
    normalized = normalize_uyghur(text)
    return re.sub(r"\u06cc{2,}", "\u06cc", normalized)


# Punctuation commonly wrapping Uyghur words/titles that must be stripped
# before word-level matching (quotes, brackets, sentence punctuation).
PUNCTUATION_STRIP_CHARS = "«»،؟!()[]{}\"''"

_QUOTE_PATTERN = re.compile(r'"([^"]+)"|«([^»]+)»|“([^”]+)”')

# Explicit literary/bibliographic words that strongly mark the preceding word
# as a book/work title (used for both short-title gating and exempting
# explicitly-signaled single-word titles from common-word suppression).
STRONG_TITLE_FOLLOWERS = tuple(
    normalize_uyghur(w)
    for w in (
        "كىتاب",
        "ناملىق",
        "رومان",
        "ئەسەر",
        "داستان",
        "ھېكايە",
        "پوۋېست",
        "ژۇرنال",
        "ئاپتور",
        "يازغۇچى",
    )
)

# Softer topic/postposition followers accepted for >= 4-char single-word titles.
_TOPIC_TITLE_FOLLOWERS = tuple(
    normalize_uyghur(w)
    for w in (
        "ھەققىدە",
        "تۆغرىسىدا",
        "توغرىسىدا",
        "بىلەن",
        "ئۈستىدە",
        "دەپ",
    )
)

# Uyghur case/locative suffixes allowed on short (< 4 char) single-word titles
# (e.g. ئىز → ئىزنىڭ / ئىزدا / ئىزدىكى) without matching unrelated stems that
# merely share a 2–3 char prefix (e.g. ئىزدىنىش, ئىزچىلار, ئىزاھات).
_SHORT_TITLE_CASE_SUFFIXES = tuple(
    normalize_uyghur(s)
    for s in (
        "",
        "نىڭ",
        "نى",
        "دا",
        "دە",
        "تا",
        "تە",
        "دىكى",
        "تىكى",
        "دىن",
        "تىن",
        "غا",
        "گە",
        "قا",
        "كە",
    )
)


def short_token_matches(e_word: str, q_word: str) -> bool:
    """Strict stem+case-suffix match for short (< 4 char) normalized tokens."""
    if not e_word or not q_word:
        return False
    stems = [e_word]
    if e_word.endswith("ە"):
        stems.append(e_word[:-1] + "\u06cc")
    for stem in stems:
        if (
            q_word.startswith(stem)
            and q_word[len(stem) :] in _SHORT_TITLE_CASE_SUFFIXES
        ):
            return True
    return False


def _extract_normalized_quotes(question: str) -> List[str]:
    return [
        normalize_uyghur(g.strip())
        for match in _QUOTE_PATTERN.finditer(question)
        for g in match.groups()
        if g is not None and g.strip()
    ]


def has_explicit_single_word_title_signal(
    title: str, question: str, author: str | None = None
) -> bool:
    """Return True when a single-word *title* is explicitly signaled as a book
    title in *question* — via quotation marks, a strong literary/bibliographic
    follower (e.g. ناملىق, رومانى, كىتابى, ئاپتورى), or co-occurrence with the
    book's *author* name.
    """
    title_words = normalize_uyghur(title.strip()).split()
    if len(title_words) != 1:
        return False
    e_word = title_words[0]
    is_short = len(e_word) < 4
    alt = e_word[:-1] + "\u06cc" if e_word.endswith("ە") else None

    def _matches_tok(tok: str) -> bool:
        if is_short:
            return short_token_matches(e_word, tok)
        return tok.startswith(e_word) or (alt is not None and tok.startswith(alt))

    extracted_quotes = _extract_normalized_quotes(question)
    if any(_matches_tok(q) for q in extracted_quotes):
        return True

    norm_q = normalize_uyghur(question)
    q_words = [w.strip(PUNCTUATION_STRIP_CHARS) for w in norm_q.strip().split()]
    for idx, w in enumerate(q_words[:-1]):
        if _matches_tok(w):
            next_w = q_words[idx + 1]
            if any(next_w.startswith(ind) for ind in STRONG_TITLE_FOLLOWERS):
                return True

    if author and author.strip() and entity_matches_question(author, question):
        return True

    return False


def fuzzy_token_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """True if two normalized words are near-identical (spelling-tolerant match).

    Both words must be at least 4 characters — shorter words produce too many
    false positives under edit-distance similarity.
    """
    return (
        len(a) >= 4 and len(b) >= 4 and SequenceMatcher(None, a, b).ratio() >= threshold
    )


def entity_matches_question(entity: str, question: str) -> bool:
    """Return True if an author name or book title is referenced in the question.

    Handles Uyghur agglutinative suffixes (e.g. 'سابىر' matches 'سابىرنىڭ').
    Each word of the entity must appear as a prefix of at least one word in
    the question.  Single-word entities shorter than 4 characters (e.g. 'ئىز',
    'داغ') are allowed only when explicitly signaled (quoted as a standalone
    span, followed by a strong title indicator such as ناملىق/رومانى/كىتابى, or
    passed as a bare single-word query) and use strict stem+case-suffix
    matching so unrelated words sharing a prefix (e.g. 'ئىزدىنىش') do not
    match.  Normalizes ى/ې/ي variants and strips zero-width joiners before
    comparison.

    Also handles the ە → ى alternation before case suffixes
    (e.g. 'بابۇرنامە' matches 'بابۇرنامىنىڭ').
    """
    entity_words = normalize_uyghur(entity.strip()).split()
    if not entity_words:
        return False
    norm_q = normalize_uyghur(question)
    q_words = [
        w.strip(PUNCTUATION_STRIP_CHARS)
        for w in norm_q.strip().split()
        if w.strip(PUNCTUATION_STRIP_CHARS)
    ]
    if not q_words:
        return False

    if len(entity_words) == 1 and len(entity_words[0]) < 4:
        e_word = entity_words[0]
        if len(e_word) < 2:
            return False
        # Bare 1-word query (e.g. find_books_by_title("ئىز"))
        if len(q_words) == 1 and short_token_matches(e_word, q_words[0]):
            return True
        # Explicitly quoted (e.g. «ئىز», «ئىزنى») — must match the whole span
        extracted_quotes = _extract_normalized_quotes(question)
        if any(short_token_matches(e_word, q) for q in extracted_quotes):
            return True
        # Followed immediately by a strong literary/title indicator
        for idx, w in enumerate(q_words[:-1]):
            if short_token_matches(e_word, w):
                next_w = q_words[idx + 1]
                if any(next_w.startswith(ind) for ind in STRONG_TITLE_FOLLOWERS):
                    return True
        return False

    # Structural rule for single-word titles (>= 4 chars) in multi-word questions (>= 3 words):
    # Single-word titles are matched if:
    # 1. Enclosed in quotation marks («...», "...", “...”), OR
    # 2. Positioned at sentence start (subject position), OR
    # 3. Followed by a title indicator (e.g. كىتابى, ناملىق, رومانى) or topic postposition (e.g. ھەققىدە, توغرىسىدا)
    if len(q_words) >= 3 and len(entity_words) == 1:
        e_word = entity_words[0]
        is_sentence_start = q_words[0].startswith(e_word) or (
            e_word.endswith("ە") and q_words[0].startswith(e_word[:-1] + "\u06cc")
        )
        extracted_quotes = _extract_normalized_quotes(question)
        is_quoted = any(q.startswith(e_word) for q in extracted_quotes)
        if not (is_sentence_start or is_quoted):
            valid_followers = STRONG_TITLE_FOLLOWERS + _TOPIC_TITLE_FOLLOWERS
            followed_by_indicator = False
            for idx, w in enumerate(q_words[:-1]):
                if w.startswith(e_word) or (
                    e_word.endswith("ە") and w.startswith(e_word[:-1] + "\u06cc")
                ):
                    next_w = q_words[idx + 1]
                    if any(next_w.startswith(ind) for ind in valid_followers):
                        followed_by_indicator = True
                        break
            if not followed_by_indicator:
                return False

    def _word_matches(e_word: str) -> bool:
        alt = e_word[:-1] + "\u06cc" if e_word.endswith("ە") else None
        if any(
            q_word.startswith(e_word) or (alt is not None and q_word.startswith(alt))
            for q_word in q_words
        ):
            return True
        # Fuzzy fallback: catch single-character spelling variations (e.g. ھەمدى vs ھەمىدى).
        # Both words must be ≥4 chars to avoid false positives on short tokens.
        if len(e_word) < 4:
            return False
        for q_word in q_words:
            if (
                len(q_word) >= 4
                and SequenceMatcher(None, e_word, q_word).ratio() >= 0.85
            ):
                return True
        return False

    return all(_word_matches(e_word) for e_word in entity_words)


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

from app.services.rag.keywords import (
    CURRENT_VOLUME_KEYWORDS,
    CURRENT_PAGE_KEYWORDS,
    CATALOG_QUERY_KEYWORDS,
    CONTENT_SIGNAL_KEYWORDS,
)


def is_current_volume_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    return any(k in q for k in CURRENT_VOLUME_KEYWORDS)


def is_current_page_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    return any(k in q for k in CURRENT_PAGE_KEYWORDS)


def is_author_or_catalog_query(question: str) -> bool:
    """Detect if the question is about book authors or which books exist in the library."""
    if not question:
        return False
    q = normalize_uyghur(question.strip())
    normalized_keywords = [normalize_uyghur(k) for k in CATALOG_QUERY_KEYWORDS]
    if not any(k in q for k in normalized_keywords):
        return False

    # "قايسى ئەسەردىكى X" / "قايسى كىتابتا X" are content queries ("X is in which work"),
    # not catalog queries — even though they contain "قايسى ئەسەر".
    normalized_signals = [normalize_uyghur(k) for k in CONTENT_SIGNAL_KEYWORDS]
    if any(k in q for k in normalized_signals):
        return False

    return True


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def extract_keywords(question: str) -> List[str]:
    tokens = [
        re.sub(r"[^\w]", "", k, flags=re.UNICODE).strip() for k in question.split()
    ]
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


def is_islam_or_quran_query(question: str) -> bool:
    """Check if the question or its context pertains to Islam or the Quran."""
    if not question:
        return False
    q_norm = normalize_uyghur(question.lower())

    # Comprehensive, unambiguous terms to avoid false positives on general words
    islam_keywords = [
        # Uyghur
        "قۇرئان",
        "سۈرە",
        "ئايەت",
        "ئاللاھ",
        "خۇدا",
        "پەرۋەردىگار",
        "پەيغەمبەر",
        "مۇھەممەد",
        "ئىسلام",
        "مۇسۇلمان",
        "ناماز",
        "روزا",
        "زاكات",
        "ھەج",
        "ھەدىس",
        "شەرىئەت",
        # English
        "quran",
        "koran",
        "surah",
        "ayah",
        "verse",
        "allah",
        "prophet",
        "muhammad",
        "islam",
        "muslim",
        "ramadan",
        "hadith",
        "sharia",
    ]

    normalized_keywords = [normalize_uyghur(k.lower()) for k in islam_keywords]
    return any(k in q_norm for k in normalized_keywords)


def is_who_is_query(question: str) -> bool:
    """Check if the query is a 'who is X' style question in English or Uyghur.

    Such queries ask about a person's biography/identity rather than looking up
    names in a person name dictionary, so they should skip names_dictionary check.
    """
    if not question:
        return False
    q_norm = normalize_uyghur(question.lower())

    # Check English patterns: match "who", "who's", "whos" as whole words.
    # Excludes possessive "whose" or objective "whom".
    english_who = re.search(r"\b(who|whos|who's)\b", q_norm)
    if english_who:
        return True

    # Check Uyghur patterns: match "كىم", "كىمدۇر", "كىملەر", "كىملىكى", "كىملىك".
    # Excludes case-suffixed variants like "كىمنىڭ" (whose), "كىمگە" (to whom), "كىمنى" (whom), etc.
    allowed_ug = {"كیم", "كیمدۇر", "كیملەر", "كیملیكی", "كیملیك"}
    words = [w.strip(".,?!;:()[]{}«»\"'`؟،؛") for w in q_norm.split()]
    for w in words:
        if w in allowed_ug:
            return True

    return False
