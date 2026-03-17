"""
Spell Check Service — core per-page spell check logic shared between
the API (on-demand) and the background worker (batch).
"""
from __future__ import annotations

import asyncio
from collections import Counter
import re
import unicodedata
from typing import List, TypedDict, Dict

from sqlalchemy import delete, func, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Page, PageSpellIssue, SpellCheckCorrection
from app.utils.text import normalize_uyghur_chars
from sqlalchemy import select

class SpellCheckCache(TypedDict, total=False):
    """Optional per-job cache to avoid redundant DB lookups."""
    unknown_words: Dict[str, bool]  # word -> is_unknown
    ocr_corrections: Dict[str, list[str]] # word -> corrections
    _locks: Dict[str, asyncio.Lock]  # Internal locks for thread safety
    _stats: Dict[str, int]  # Cache hit/miss statistics


class ThreadSafeSpellCheckCache:
    """Thread-safe wrapper for spell check cache with hit rate tracking."""

    def __init__(self):
        self.unknown_words: Dict[str, bool] = {}
        self.ocr_corrections: Dict[str, list[str]] = {}
        self._locks = {
            'unknown': asyncio.Lock(),
            'ocr': asyncio.Lock()
        }
        self._stats = {
            'unknown_hits': 0,
            'unknown_misses': 0,
            'ocr_hits': 0,
            'ocr_misses': 0
        }

    def get_stats(self) -> dict:
        """Return cache statistics including hit rates."""
        total_unknown = self._stats['unknown_hits'] + self._stats['unknown_misses']
        total_ocr = self._stats['ocr_hits'] + self._stats['ocr_misses']

        return {
            'unknown_words': {
                'hits': self._stats['unknown_hits'],
                'misses': self._stats['unknown_misses'],
                'hit_rate': self._stats['unknown_hits'] / total_unknown if total_unknown > 0 else 0
            },
            'ocr_corrections': {
                'hits': self._stats['ocr_hits'],
                'misses': self._stats['ocr_misses'],
                'hit_rate': self._stats['ocr_hits'] / total_ocr if total_ocr > 0 else 0
            },
            'total_lookups': total_unknown + total_ocr,
            'overall_hit_rate': (
                (self._stats['unknown_hits'] + self._stats['ocr_hits']) /
                (total_unknown + total_ocr)
                if (total_unknown + total_ocr) > 0 else 0
            )
        }

# ── Tokenizer ──────────────────────────────────────────────────────────────────

_WORD_RE = re.compile(
    # Start at U+0621 (ء) to skip Arabic punctuation in U+0600–U+0620.
    # Included \u200C (ZWNJ) and \u200D (ZWJ) to prevent splitting words.
    r"[\u0621-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u200C\u200D]+"
)
_MIN_WORD_LEN = 4



def tokenize(page_text: str) -> list[tuple[str, int, int]]:
    """Return (normalized_word, start, end) tuples from raw page text.

    Offsets (start, end) always refer to positions in the *raw* page_text
    that was passed in — they are NOT re-based after any normalization.
    The word value is normalized for dictionary lookup only.
    """
    tokens = []
    for m in _WORD_RE.finditer(page_text):
        raw = m.group()
        left = 0
        while left < len(raw) and unicodedata.category(raw[left])[0] not in ('L', 'M'):
            left += 1
        right = len(raw)
        while right > left and unicodedata.category(raw[right - 1])[0] not in ('L', 'M'):
            right -= 1
        if left >= right:
            continue
        # Normalize only for dictionary lookup; raw slice is what we store
        word_normalized = normalize_uyghur_chars(raw[left:right])
        # The raw word (as it appears in the source text) is used for display
        word_raw = raw[left:right]
        if len(word_normalized) >= _MIN_WORD_LEN:
            tokens.append((word_normalized, word_raw, m.start() + left, m.start() + right))
    return tokens


# ── OCR character confusion pairs ──────────────────────────────────────────────

_OCR_PAIRS: list[tuple[str, str, str]] = [
    ("\u0643", "\u06AD", "ك→ڭ"),
    ("\u06AD", "\u0643", "ڭ→ك"),
    ("\u0648", "\u06C7", "و→ۇ"),
    ("\u06C7", "\u0648", "ۇ→و"),
    ("\u06C6", "\u06C7", "ۆ→ۇ"),
    ("\u06C7", "\u06C6", "ۇ→ۆ"),
    ("\u06D5", "\u06BE", "ە→ھ"),
    ("\u06BE", "\u06D5", "ھ→ە"),
    ("\u0646", "\u06AD", "ن→ڭ"),
    ("\u06AF", "\u0643", "گ→ك"),
    ("\u0643", "\u06AF", "ك→گ"),
    ("\u06CB", "\u0648", "ۋ→و"),
    ("\u0648", "\u06CB", "و→ۋ"),
    ("\u0631", "\u0632", "ر→ز"),
    ("\u0632", "\u0631", "ز→ر"),
    ("\u0642", "\u0641", "ق→ف"),
    ("\u0641", "\u0642", "ف→ق"),
    ("\u0639", "\u063A", "ع→غ"),
    ("\u063A", "\u0639", "غ→ع"),
    ("\u062D", "\u062E", "ح→خ"),
    ("\u062E", "\u062D", "خ→ح"),
]


def ocr_variants(word: str) -> list[str]:
    """Generate all single- and double-substitution OCR variants for a word."""
    seen: set[str] = set()
    results: list[str] = []

    def _apply_single(w: str) -> list[str]:
        out = []
        for wrong, correct, _ in _OCR_PAIRS:
            if wrong not in w:
                continue
            idx = 0
            while True:
                pos = w.find(wrong, idx)
                if pos == -1:
                    break
                out.append(w[:pos] + correct + w[pos + len(wrong):])
                idx = pos + 1
        return out

    for variant in _apply_single(word):
        if variant not in seen and variant != word:
            seen.add(variant)
            results.append(variant)

    for v1 in list(results):
        for v2 in _apply_single(v1):
            if v2 not in seen and v2 != word:
                seen.add(v2)
                results.append(v2)

    return results


# ── Insertion variants (OCR dropped a character) ───────────────────────────────
# Uyghur vowels most commonly dropped/fused by OCR
_VOWEL_INSERTIONS: list[str] = [
    "\u064A",   # ى ya/ye — most frequently dropped
    "\u0627",   # ا alef
    "\u06D5",   # ە ae
    "\u06C7",   # ۇ u
    "\u06C6",   # ۆ oe
]


def insertion_variants(word: str) -> list[str]:
    """
    Generate variants by inserting a missing vowel at every position.
    Single insertions only — keeps the variant set manageable.
    """
    seen: set[str] = set()
    results: list[str] = []
    for pos in range(len(word) + 1):
        for vowel in _VOWEL_INSERTIONS:
            variant = word[:pos] + vowel + word[pos:]
            if variant not in seen and variant != word:
                seen.add(variant)
                results.append(variant)
    return results

# ── DB helpers ─────────────────────────────────────────────────────────────────

async def find_unknown_words(
    session: AsyncSession,
    words: list[str],
    cache: SpellCheckCache | ThreadSafeSpellCheckCache | None = None
) -> set[str]:
    """Find words not in dictionary. Uses parameterized query (safe from SQL injection)."""
    if not words:
        return set()

    unknown = set()
    to_query = []

    # Handle both legacy dict cache and new thread-safe cache
    is_thread_safe = isinstance(cache, ThreadSafeSpellCheckCache)

    if cache is not None:
        if is_thread_safe:
            # Thread-safe cache with locking and statistics
            async with cache._locks['unknown']:
                for w in words:
                    if w in cache.unknown_words:
                        cache._stats['unknown_hits'] += 1
                        if cache.unknown_words[w]:
                            unknown.add(w)
                    else:
                        cache._stats['unknown_misses'] += 1
                        to_query.append(w)
        else:
            # Legacy TypedDict cache (backwards compatible)
            if "unknown_words" not in cache:
                cache["unknown_words"] = {}
            for w in words:
                if w in cache["unknown_words"]:
                    if cache["unknown_words"][w]:
                        unknown.add(w)
                else:
                    to_query.append(w)
    else:
        to_query = words

    if to_query:
        # Safe: words is bound as a parameter, not interpolated into SQL string
        result = await session.execute(
            text(
                "SELECT unnest(CAST(:words AS text[])) AS w "
                "EXCEPT "
                "SELECT word FROM dictionary"
            ),
            {"words": to_query},
        )
        queried_unknown = {row[0] for row in result.fetchall()}
        unknown.update(queried_unknown)

        if cache is not None:
            if is_thread_safe:
                async with cache._locks['unknown']:
                    for w in to_query:
                        cache.unknown_words[w] = (w in queried_unknown)
            else:
                for w in to_query:
                    cache["unknown_words"][w] = (w in queried_unknown)

    return unknown





async def get_ocr_corrections_batch(
    session: AsyncSession,
    unknowns: set[str],
    cache: SpellCheckCache | ThreadSafeSpellCheckCache | None = None
) -> dict[str, list[str]]:
    """
    Batch correction lookup combining substitution and insertion variants.
    Returns {unknown_word: [corrected_word, ...]} for words that have at least
    one correction found in the dictionary.
    """
    corrections: dict[str, list[str]] = {}
    to_lookup_unknowns = set()

    # Handle both legacy dict cache and new thread-safe cache
    is_thread_safe = isinstance(cache, ThreadSafeSpellCheckCache)

    if cache is not None:
        if is_thread_safe:
            async with cache._locks['ocr']:
                for w in unknowns:
                    if w in cache.ocr_corrections:
                        cache._stats['ocr_hits'] += 1
                        if cache.ocr_corrections[w]:
                            corrections[w] = cache.ocr_corrections[w]
                    else:
                        cache._stats['ocr_misses'] += 1
                        to_lookup_unknowns.add(w)
        else:
            if "ocr_corrections" not in cache:
                cache["ocr_corrections"] = {}
            for w in unknowns:
                if w in cache["ocr_corrections"]:
                    if cache["ocr_corrections"][w]:
                        corrections[w] = cache["ocr_corrections"][w]
                else:
                    to_lookup_unknowns.add(w)
    else:
        to_lookup_unknowns = unknowns

    if not to_lookup_unknowns:
        return corrections

    variant_to_originals: dict[str, list[str]] = {}
    for word in to_lookup_unknowns:
        for variant in ocr_variants(word):
            variant_to_originals.setdefault(variant, []).append(word)
        for variant in insertion_variants(word):
            variant_to_originals.setdefault(variant, []).append(word)

    if not variant_to_originals:
        # Mark all as having no corrections in cache
        if cache is not None:
            if is_thread_safe:
                async with cache._locks['ocr']:
                    for w in to_lookup_unknowns:
                        cache.ocr_corrections[w] = []
            else:
                for w in to_lookup_unknowns:
                    cache["ocr_corrections"][w] = []
        return corrections

    result = await session.execute(
        text("SELECT word FROM dictionary WHERE word = ANY(CAST(:variants AS text[]))"),
        {"variants": list(variant_to_originals.keys())},
    )
    found = {row[0] for row in result.fetchall()}

    for variant, originals in variant_to_originals.items():
        if variant in found:
            for orig in originals:
                if variant not in corrections.setdefault(orig, []):
                    corrections[orig].append(variant)

    if cache is not None:
        if is_thread_safe:
            async with cache._locks['ocr']:
                for w in to_lookup_unknowns:
                    cache.ocr_corrections[w] = corrections.get(w, [])
        else:
            for w in to_lookup_unknowns:
                cache["ocr_corrections"][w] = corrections.get(w, [])

    return corrections


# ── Core per-page function ─────────────────────────────────────────────────────

async def run_spell_check_for_page(
    session: AsyncSession,
    page: Page,
    cache: SpellCheckCache | None = None
) -> int:
    """
    Run spell check for a single page within the given session.

    Tokenizes the RAW page text so that char_offset/char_end always point
    into page.text exactly as stored in the DB and displayed on the frontend.
    The normalized word form is used only for dictionary lookup.

    UPDATED LOGIC: Only creates spell check issues for words that:
    1. Are NOT in the dictionary (unknown words)
    2. Have at least one OCR correction candidate found in the dictionary

    This ensures we only flag words that are likely OCR errors with valid
    dictionary corrections, eliminating false positives from rare/valid words.

    Replaces all existing issues for the page, sets spell_check_milestone='done',
    and returns the number of issues found.
    Does NOT commit — caller is responsible for committing.
    """
    raw_text = page.text or ""
    
    # S-NEW-AUTO: Fetch and apply global correction rules immediately
    # This prevents manual review of words we already have a solution for.
    rules_result = await session.execute(
        select(SpellCheckCorrection.misspelled_word, SpellCheckCorrection.corrected_word)
        .where(SpellCheckCorrection.auto_apply == True)
    )
    rules = {row.misspelled_word: row.corrected_word for row in rules_result.fetchall()}

    text_changed = False
    if rules:
        # Check if any rules apply (quick check before heavy regex/loop)
        applied_rules = {w: c for w, c in rules.items() if w in raw_text}
        if applied_rules:
            # Sort rules by length (desc) to avoid partial replacements of longer phrases
            sorted_rules = sorted(applied_rules.items(), key=lambda x: len(x[0]), reverse=True)
            for misspelled, corrected in sorted_rules:
                if misspelled in raw_text:
                    # Use robust regex to handle character variants (e.g. hamza seat variations)
                    from app.utils.text import generate_uyghur_regex
                    misspelled_regex = generate_uyghur_regex(misspelled)
                    
                    # Use negative lookbehind/lookahead with Uyghur character range as word boundaries
                    # \b doesn't work well with non-ASCII.
                    boundaries = r"[\u0621-\u06FF\u0750-\u077F\FB50-\uFDFF\uFE70-\uFEFF\u200C\u200D]"
                    pattern = f"(?<!{boundaries}){misspelled_regex}(?!{boundaries})"
                    
                    new_text = re.sub(pattern, corrected, raw_text)
                    if new_text != raw_text:
                        raw_text = new_text
                        text_changed = True

    if text_changed:
        page.text = raw_text
        page.last_updated = func.now()
        # The page will be updated in the DB when the caller commits.

    # Tokenize against the (possibly updated) raw_text
    tokens = tokenize(raw_text)

    if not tokens:
        await session.execute(
            update(Page)
            .where(Page.id == page.id)
            .values(spell_check_milestone="done", last_updated=func.now())
        )
        return 0

    # tokens now yields (word_normalized, word_raw, start, end)
    word_freq = Counter(word_norm for word_norm, _raw, _s, _e in tokens)
    unique_words = list(word_freq.keys())
    unknown = await find_unknown_words(session, unique_words, cache=cache)
    ocr_cache = await get_ocr_corrections_batch(session, unknown, cache=cache)

    # SIMPLIFIED LOGIC: Only create issues for words with OCR corrections
    # if a word has a valid
    # dictionary correction via OCR substitution/insertion, it's likely an error
    issues: List[PageSpellIssue] = [
        PageSpellIssue(
            page_id=page.id,
            # Store the raw word (what the editor sees) not the normalized form
            word=word_raw,
            char_offset=start,
            char_end=end,
            ocr_corrections=ocr_cache.get(word_norm, []),
            status="open",
        )
        for word_norm, word_raw, start, end in tokens
        if word_norm in ocr_cache and ocr_cache[word_norm]  # Only if corrections exist
    ]

    await session.execute(
        delete(PageSpellIssue).where(PageSpellIssue.page_id == page.id)
    )
    session.add_all(issues)

    await session.execute(
        update(Page)
        .where(Page.id == page.id)
        .values(spell_check_milestone="done", last_updated=func.now())
    )

    return len(issues)
