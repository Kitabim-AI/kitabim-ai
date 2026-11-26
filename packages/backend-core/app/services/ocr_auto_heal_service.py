"""
High-Precision Uyghur OCR Auto-Heal Service (`ocr_auto_heal_service.py`)
========================================================================
Automatically repairs unambiguous single-character visual OCR confusions in
Uyghur text while leaving any ambiguous token untouched for human review.

Core Safety Invariants
----------------------
1. **Known-Word Protection**: Never modifies a token that is already valid in
   the static `words` lexicon, `protected_words` (e.g. `names_dictionary` /
   `history_dictionary`), or dynamic Uyghur morphology (`uyghur_morphology.py`).
2. **Targeted Visual-Confusion Proposals**: Only proposes repairs from
   high-frequency Uyghur Arabic OCR visual pairs (`ز↔ر`, `و↔ۇ↔ۆ↔ۈ`, `گ↔ك`,
   `ف→ق`, `ە↔ھ`, nasal assimilation `نگ→ڭگ` / `نغ→ڭغ`, and impossible OCR
   suffix dot-drops `-نىك→-نىڭ`, `-لىرىكىز→-لىرىڭىز`, `-دىگى→-دىكى`,
   `-نىڭگى→-نىڭكى`, `-لىزى...→-لىرى...`). Never proposes `ن→ڭ` or `ڭ→ك`, which
   can flip 3rd-person ablative/accusative endings into 2nd-person forms.
3. **32-Letter 1-Edit Uniqueness Veto**: A general candidate `w -> fix` is
   accepted ONLY if **zero** other 1-edit-distance strings across the entire
   32-letter Uyghur alphabet (any substitution, deletion, insertion, or
   adjacent transposition) are valid words. If two plausible words compete
   (e.g., `مۇرىسىدىكى` -> `مورىسىدىكى` vs `مۈرىسىدىكى`, or `گۆچۈرۈلدى` ->
   `كۆچۈرۈلدى` vs `ئۆچۈرۈلدى`), the token is vetoed and left untouched.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    PAGE_MILESTONE_IDLE,
    PAGE_MILESTONE_SUCCEEDED,
)
from app.db.models import AutoCorrectRule, Book, Page, PageSpellIssue, PipelineEvent
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.cache_service import cache_service
from app.services.spell_check_service import (
    insertion_variants,
    ocr_variants,
    tokenize,
)
from app.services.uyghur_morphology import (
    analyze_uyghur_word,
    is_word_verified_by_lexicon,
)
from app.utils.observability import make_pipeline_event_payload
from app.utils.text import generate_uyghur_regex, normalize_uyghur_chars

UYGHUR_ALPHABET = "ئابپتجچخدرزژسشغفقكگڭلمنھوۇۆۈۋېىي"

SAFE_OCR_SUBS: tuple[tuple[str, str, str], ...] = (
    ("ز", "ر", "ز→ر"),
    ("ر", "ز", "ر→ز"),
    ("و", "ۇ", "و→ۇ"),
    ("ۇ", "و", "ۇ→و"),
    ("ۆ", "ۇ", "ۆ→ۇ"),
    ("ۇ", "ۆ", "ۇ→ۆ"),
    ("ۈ", "ۇ", "ۈ→ۇ"),
    ("ۇ", "ۈ", "ۇ→ۈ"),
    ("ۆ", "ۈ", "ۆ→ۈ"),
    ("ۈ", "ۆ", "ۈ→ۆ"),
    ("گ", "ك", "گ→ك"),
    ("ك", "گ", "ك→گ"),
    ("ف", "ق", "ف→ق"),
    ("ە", "ھ", "ە→ھ"),
    ("ھ", "ە", "ھ→ە"),
    ("نگ", "ڭگ", "نگ→ڭگ"),
    ("نغ", "ڭغ", "نغ→ڭغ"),
)

SUFFIX_DOT_FIXES: tuple[tuple[str, str, str], ...] = (
    ("نىك", "نىڭ", "-نىك→-نىڭ"),
    ("لىرىكىز", "لىرىڭىز", "-لىرىكىز→-لىرىڭىز"),
    ("دىگى", "دىكى", "-دىگى→-دىكى"),
    ("دىگىچە", "دىكىچە", "-دىگىچە→-دىكىچە"),
    ("نىڭگى", "نىڭكى", "-نىڭگى→-نىڭكى"),
)

# Plural + 3rd-person possessive `-لىرى` misread as `-لىزى` (`ز` = `ر` + 1 dot).
# Note: `-لىقى` differs from `-لىرى` at 1-edit (`ق` vs `ر`) even though `ق` and `ز`
# share zero visual similarity, so `-لىزى` uses a dedicated suffix rule vetoed only
# against visual-family (`د/ر/ز/ژ` or vowel) competitors.
_LIZI_SUFFIX_RE = re.compile(
    r"^(.{2,})لىزى(م|ڭ|مىز|ڭىز|منىڭ|ڭنىڭ|مىزنىڭ|ڭىزنىڭ|مغا|ڭغا|مىزغا|ڭىزغا|مدا|ڭدا|مىزدا|ڭىزدا|مدىن|ڭدىن|مىزدىن|ڭىزدىن|غا|دا|دىن|نى|نىڭ|چە|مۇ|لا|دەك|دىكى)?$"
)

# Honorific titles that typically follow personal given names in historical/literary
# Uyghur prose (e.g. `دۇنايى خەلىپە`). Rounded-vowel-only swaps right before these
# titles are skipped unless the healed token itself is a common salutation/title.
HONORIFIC_FOLLOWING_TITLES: frozenset[str] = frozenset(
    {
        "خەلىپە",
        "خوجا",
        "خوجام",
        "ئاخۇن",
        "ئاخۇنۇم",
        "موللا",
        "داموللا",
        "قارى",
        "قارىم",
        "ھاجى",
        "ھاجىم",
        "ئىشان",
        "تەيجى",
        "ۋاڭ",
    }
)
KNOWN_NON_NAME_TITLES: frozenset[str] = frozenset(
    {"قۇشبېگى", "بۈزرۈك", "ھەزرەت", "ھۆرمەتلىك", "مەشھۇر"}
)
ROUNDED_VOWEL_RULE_LABELS: frozenset[str] = frozenset(
    {"و→ۇ", "ۇ→و", "ۆ→ۇ", "ۇ→ۆ", "ۈ→ۇ", "ۇ→ۈ", "ۆ→ۈ", "ۈ→ۆ"}
)
_UYGHUR_WORD_BOUNDARIES = (
    r"[\u0621-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF\u200C\u200D]"
)


@dataclass(frozen=True)
class AutoHealRecord:
    """Audit record for a single auto-healed OCR token on a page."""

    line_number: int
    col_offset: int
    char_offset: int
    char_end: int
    original_word: str
    normalized_word: str
    healed_word: str
    rule_label: str
    verification_source: str  # "static" | "dynamic"
    line_context: str


def all_1edit_uyghur_neighbors(word: str) -> set[str]:
    """Generate every Levenshtein/Damerau distance-1 string over the 32 Uyghur letters."""
    out: set[str] = set()
    n = len(word)
    for i in range(n):
        out.add(word[:i] + word[i + 1 :])
    for i in range(n):
        orig = word[i]
        prefix = word[:i]
        suffix = word[i + 1 :]
        for ch in UYGHUR_ALPHABET:
            if ch != orig:
                out.add(prefix + ch + suffix)
    for i in range(n + 1):
        prefix = word[:i]
        suffix = word[i:]
        for ch in UYGHUR_ALPHABET:
            out.add(prefix + ch + suffix)
    for i in range(n - 1):
        if word[i] != word[i + 1]:
            out.add(word[:i] + word[i + 1] + word[i] + word[i + 2 :])
    out.discard(word)
    return out


def generate_safe_ocr_candidates(word: str) -> list[tuple[str, str]]:
    """Return `(candidate_word, rule_label)` pairs from targeted visual OCR confusions."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    for s_wrong, s_right, label in SUFFIX_DOT_FIXES:
        if word.endswith(s_wrong) and len(word) > len(s_wrong) + 1:
            cand = word[: -len(s_wrong)] + s_right
            if cand not in seen and cand != word:
                seen.add(cand)
                out.append((cand, label))

    for wrong, right, label in SAFE_OCR_SUBS:
        idx = 0
        while (pos := word.find(wrong, idx)) != -1:
            cand = word[:pos] + right + word[pos + len(wrong) :]
            if cand not in seen and cand != word:
                seen.add(cand)
                out.append((cand, label))
            idx = pos + 1

    return out


class UyghurOcrAutoHealer:
    """
    Stateful, memoized high-precision Uyghur OCR auto-healer.

    Memoizes both lexical/morphological validity and per-word heal decisions
    across pages so an entire 400-page book runs in a few seconds on CPU.
    """

    def __init__(
        self,
        lexicon: set[str],
        protected_words: set[str] | None = None,
        min_word_len: int = 6,
    ) -> None:
        self.lexicon = lexicon
        self.protected_words = protected_words or set()
        self.min_word_len = min_word_len
        self._valid_cache: dict[str, str | None] = {}
        self._decision_cache: dict[str, tuple[str, str, str] | None] = {}

    def check_word_valid(self, word_norm: str) -> str | None:
        """Return `'static'`, `'protected'`, `'dynamic'`, or `None` if invalid/unknown."""
        if word_norm in self._valid_cache:
            return self._valid_cache[word_norm]

        if word_norm in self.lexicon:
            self._valid_cache[word_norm] = "static"
            return "static"
        if word_norm in self.protected_words:
            self._valid_cache[word_norm] = "protected"
            return "protected"

        reqs = analyze_uyghur_word(word_norm)
        if reqs and is_word_verified_by_lexicon(reqs, self.lexicon):
            self._valid_cache[word_norm] = "dynamic"
            return "dynamic"

        self._valid_cache[word_norm] = None
        return None

    def resolve_token(self, word_norm: str) -> tuple[str, str, str] | None:
        """
        Decide whether `word_norm` can be unambiguously auto-healed.
        Returns `(healed_word, rule_label, verification_source)` or `None`.
        """
        if len(word_norm) < self.min_word_len:
            return None

        if word_norm in self._decision_cache:
            return self._decision_cache[word_norm]

        if self.check_word_valid(word_norm) is not None:
            self._decision_cache[word_norm] = None
            return None

        # 1. Check dedicated plural+possessive `-لىزى... -> -لىرى...` dot-drop rule
        m_lizi = _LIZI_SUFFIX_RE.match(word_norm)
        if m_lizi:
            stem, tail = m_lizi.group(1), m_lizi.group(2) or ""
            liri_cand = f"{stem}لىرى{tail}"
            src = self.check_word_valid(liri_cand)
            if src in ("static", "dynamic"):
                # Veto only if another `د/ر/ز/ژ` swap or deletion produces a different word
                z_idx = len(stem) + 2
                competing = False
                for alt in ("د", "ژ"):
                    alt_w = word_norm[:z_idx] + alt + word_norm[z_idx + 1 :]
                    if self.check_word_valid(alt_w) is not None:
                        competing = True
                        break
                if not competing:
                    res = (liri_cand, "-لىزى→-لىرى", src)
                    self._decision_cache[word_norm] = res
                    return res

        # 2. General targeted visual OCR candidates + 32-letter 1-edit uniqueness veto
        valid_cands: list[tuple[str, str, str]] = []
        for cand, label in generate_safe_ocr_candidates(word_norm):
            src = self.check_word_valid(cand)
            if src in ("static", "dynamic"):
                valid_cands.append((cand, label, src))

        if len(valid_cands) != 1:
            self._decision_cache[word_norm] = None
            return None

        cand, label, src = valid_cands[0]
        ignored_acc_trunc = word_norm[:-1] if label == "-نىك→-نىڭ" else None

        for nb in all_1edit_uyghur_neighbors(word_norm):
            if nb == cand or nb == ignored_acc_trunc:
                continue
            if self.check_word_valid(nb) is not None:
                self._decision_cache[word_norm] = None
                return None

        res = (cand, label, src)
        self._decision_cache[word_norm] = res
        return res

    def heal_page_text(
        self, page_text: str, *, skip_toc_pipe_rows: bool = True
    ) -> tuple[str, list[AutoHealRecord]]:
        """
        Scan `page_text` line-by-line, apply unambiguous auto-heals, and return
        `(healed_text, records)` with exact 1-based `line_number` and character offsets.
        """
        if not page_text:
            return page_text, []

        lines = page_text.split("\n")
        healed_lines: list[str] = []
        records: list[AutoHealRecord] = []
        page_char_cursor = 0

        for line_idx, raw_line in enumerate(lines, start=1):
            if (
                skip_toc_pipe_rows
                and raw_line.lstrip().startswith("|")
                and "|" in raw_line.lstrip()[1:]
            ):
                healed_lines.append(raw_line)
                page_char_cursor += len(raw_line) + 1
                continue

            line_tokens = tokenize(raw_line)
            line_edits: list[tuple[int, int, str, AutoHealRecord]] = []

            for tok_idx, (word_norm, word_raw, col_start, col_end) in enumerate(
                line_tokens
            ):
                decision = self.resolve_token(word_norm)
                if decision is None:
                    continue
                healed_word, rule_label, src = decision
                if (
                    rule_label in ROUNDED_VOWEL_RULE_LABELS
                    and healed_word not in KNOWN_NON_NAME_TITLES
                    and tok_idx + 1 < len(line_tokens)
                    and line_tokens[tok_idx + 1][0] in HONORIFIC_FOLLOWING_TITLES
                ):
                    continue
                # Build readable line context around the token
                ctx_s = max(0, col_start - 40)
                ctx_e = min(len(raw_line), col_end + 40)
                prefix_ellipsis = "..." if ctx_s > 0 else ""
                suffix_ellipsis = "..." if ctx_e < len(raw_line) else ""
                highlighted_ctx = (
                    f"{prefix_ellipsis}{raw_line[ctx_s:col_start]}"
                    f"[{word_raw} → {healed_word}]"
                    f"{raw_line[col_end:ctx_e]}{suffix_ellipsis}"
                )
                rec = AutoHealRecord(
                    line_number=line_idx,
                    col_offset=col_start,
                    char_offset=page_char_cursor + col_start,
                    char_end=page_char_cursor + col_end,
                    original_word=word_raw,
                    normalized_word=normalize_uyghur_chars(word_raw),
                    healed_word=healed_word,
                    rule_label=rule_label,
                    verification_source=src,
                    line_context=highlighted_ctx,
                )
                line_edits.append((col_start, col_end, healed_word, rec))

            if not line_edits:
                healed_lines.append(raw_line)
            else:
                updated_line = raw_line
                for col_start, col_end, healed_word, _rec in reversed(line_edits):
                    updated_line = (
                        updated_line[:col_start] + healed_word + updated_line[col_end:]
                    )
                healed_lines.append(updated_line)
                records.extend(rec for _cs, _ce, _hw, rec in line_edits)

            page_char_cursor += len(raw_line) + 1

        return "\n".join(healed_lines), records


# ── Process-level lexicon cache & per-book orchestration ──────────────────────

_LEXICON_TTL_SECONDS = 300.0
_LEXICON_LOCK = asyncio.Lock()
_CACHED_WORDS: set[str] | None = None
_CACHED_PROTECTED: set[str] | None = None
_CACHED_AT: float = 0.0


def clear_auto_heal_lexicon_cache() -> None:
    """Clear the in-process lexicon cache (used in unit tests or after bulk dict edits)."""
    global _CACHED_WORDS, _CACHED_PROTECTED, _CACHED_AT
    _CACHED_WORDS = None
    _CACHED_PROTECTED = None
    _CACHED_AT = 0.0


async def get_cached_auto_heal_lexicons(
    session: AsyncSession,
) -> tuple[set[str], set[str]]:
    """Load `(words_set, protected_names_and_terms_set)` with a 5-minute process TTL."""
    global _CACHED_WORDS, _CACHED_PROTECTED, _CACHED_AT

    now = time.monotonic()
    if (
        _CACHED_WORDS is not None
        and _CACHED_PROTECTED is not None
        and (now - _CACHED_AT) < _LEXICON_TTL_SECONDS
    ):
        return _CACHED_WORDS, _CACHED_PROTECTED

    async with _LEXICON_LOCK:
        now = time.monotonic()
        if (
            _CACHED_WORDS is not None
            and _CACHED_PROTECTED is not None
            and (now - _CACHED_AT) < _LEXICON_TTL_SECONDS
        ):
            return _CACHED_WORDS, _CACHED_PROTECTED

        w_res = await session.execute(text("SELECT word FROM words"))
        words = {
            normalize_uyghur_chars(r[0].strip())
            for r in w_res.fetchall()
            if r[0] and r[0].strip()
        }

        protected: set[str] = set()
        for query in (
            "SELECT name FROM names_dictionary",
            "SELECT term FROM history_dictionary",
        ):
            p_res = await session.execute(text(query))
            for (val,) in p_res.fetchall():
                if val and val.strip():
                    norm = normalize_uyghur_chars(val.strip())
                    protected.add(norm)
                    for part in norm.split():
                        if len(part) >= 5:
                            protected.add(part)

        _CACHED_WORDS = words
        _CACHED_PROTECTED = protected
        _CACHED_AT = time.monotonic()
        return words, protected


def apply_active_rules_to_text(text_val: str, rules: dict[str, str]) -> tuple[str, int]:
    """Apply active `AutoCorrectRule` word replacements to `text_val`, returning `(new_text, count)`."""
    if not text_val or not rules:
        return text_val, 0

    applicable = {w: c for w, c in rules.items() if w and w in text_val}
    if not applicable:
        return text_val, 0

    updated = text_val
    total_count = 0
    for misspelled, corrected in sorted(
        applicable.items(), key=lambda x: len(x[0]), reverse=True
    ):
        if misspelled not in updated:
            continue
        misspelled_regex = generate_uyghur_regex(misspelled)
        pattern = (
            f"(?<!{_UYGHUR_WORD_BOUNDARIES})"
            f"{misspelled_regex}"
            f"(?!{_UYGHUR_WORD_BOUNDARIES})"
        )
        updated, n_subs = re.subn(pattern, corrected, updated)
        total_count += n_subs

    return updated, total_count


@dataclass(frozen=True)
class BookAutoHealResult:
    """Summary returned after running per-book OCR auto-correction."""

    book_id: str
    pages_scanned: int
    pages_modified: int
    rule_replacements: int
    ocr_heals: int
    total_replacements: int
    issues_marked_corrected: int = 0
    false_positives_cleared: int = 0


def _compute_inline_ocr_corrections(
    word_norm: str,
    healer: UyghurOcrAutoHealer,
    memo: dict[str, list[str]],
) -> list[str]:
    """Compute OCR correction candidates in-memory matching `get_ocr_corrections_batch`."""
    if word_norm in memo:
        return memo[word_norm]

    variants = ocr_variants(word_norm) + insertion_variants(word_norm)
    static_hits: list[str] = []
    seen: set[str] = set()
    for v in variants:
        if v not in seen and v in healer.lexicon:
            seen.add(v)
            static_hits.append(v)

    if static_hits:
        memo[word_norm] = static_hits
        return static_hits

    dyn_hits: list[str] = []
    for v in variants:
        if v not in seen and healer.check_word_valid(v) == "dynamic":
            seen.add(v)
            dyn_hits.append(v)

    memo[word_norm] = dyn_hits
    return dyn_hits


async def auto_heal_book_pages(
    session: AsyncSession,
    book_id: str,
    *,
    updated_by: str | None = None,
    lexicon_override: tuple[set[str], set[str]] | None = None,
) -> BookAutoHealResult:
    """
    Run active `AutoCorrectRule`s + `UyghurOcrAutoHealer` across all non-ToC pages
    of `book_id`, synchronize `page_spell_issues` inline inside the same transaction
    (marking healed issues `corrected`, preserving `ignored` words, recomputing
    offsets on modified pages, and clearing dynamic-morphology false positives on
    unmodified pages), set `Book.auto_correct_milestone = 'complete'`, and
    invalidate Redis caches.
    """
    t0 = time.perf_counter()

    book_res = await session.execute(select(Book).where(Book.id == book_id))
    book = book_res.scalar_one_or_none()
    if book is None:
        raise ValueError(f"Book not found: {book_id}")

    configs_repo = SystemConfigsRepository(session)
    sc_val = await configs_repo.get_value("spell_check_enabled", "false")
    spell_check_enabled = str(sc_val).strip().lower() == "true"

    rules_res = await session.execute(
        select(AutoCorrectRule.misspelled_word, AutoCorrectRule.corrected_word).where(
            AutoCorrectRule.is_active
        )
    )
    active_rules = {
        row.misspelled_word: row.corrected_word for row in rules_res.fetchall()
    }

    if lexicon_override is not None:
        words_set, protected_set = lexicon_override
    else:
        words_set, protected_set = await get_cached_auto_heal_lexicons(session)

    healer = UyghurOcrAutoHealer(words_set, protected_words=protected_set)

    pages_res = await session.execute(
        select(Page).where(Page.book_id == book_id).order_by(Page.page_number)
    )
    pages = list(pages_res.scalars().all())

    # Load existing spell issues for this book to preserve `ignored`, mark healed
    # issues `corrected`, and prune pre-morphology false positives on untouched pages.
    issues_res = await session.execute(
        select(PageSpellIssue)
        .join(Page, PageSpellIssue.page_id == Page.id)
        .where(Page.book_id == book_id)
    )
    existing_issues = list(issues_res.scalars().all())
    ignored_norms_by_page: dict[int, set[str]] = {}
    open_issues_by_page: dict[int, list[PageSpellIssue]] = {}
    for iss in existing_issues:
        if iss.status == "ignored" and iss.word:
            ignored_norms_by_page.setdefault(iss.page_id, set()).add(
                normalize_uyghur_chars(iss.word)
            )
        elif iss.status in ("open", "processing"):
            open_issues_by_page.setdefault(iss.page_id, []).append(iss)

    now = datetime.now(timezone.utc)
    pages_scanned = 0
    pages_modified = 0
    total_rule_replacements = 0
    total_ocr_heals = 0
    corrected_issue_ids: list[int] = []
    stale_issue_ids_to_delete: list[int] = []
    false_positives_cleared = 0
    ocr_corr_memo: dict[str, list[str]] = {}
    new_open_issues: list[PageSpellIssue] = []

    for page in pages:
        orig_text = page.text or ""
        if not orig_text or page.is_toc:
            continue
        pages_scanned += 1

        after_rules, n_rule_subs = apply_active_rules_to_text(orig_text, active_rules)
        healed_text, heal_records = healer.heal_page_text(after_rules)

        if healed_text == orig_text:
            # Prune any pre-morphology false positives on unmodified pages
            for iss in open_issues_by_page.get(page.id, ()):
                if (
                    iss.word
                    and healer.check_word_valid(normalize_uyghur_chars(iss.word))
                    is not None
                ):
                    stale_issue_ids_to_delete.append(iss.id)
                    false_positives_cleared += 1
            continue

        pages_modified += 1
        total_rule_replacements += n_rule_subs
        total_ocr_heals += len(heal_records)

        healed_norms = {r.normalized_word for r in heal_records} | {
            normalize_uyghur_chars(k) for k in active_rules if k and k in orig_text
        }
        for iss in open_issues_by_page.get(page.id, ()):
            if iss.word and normalize_uyghur_chars(iss.word) in healed_norms:
                corrected_issue_ids.append(iss.id)
            else:
                stale_issue_ids_to_delete.append(iss.id)

        if spell_check_enabled:
            ignored_set = ignored_norms_by_page.get(page.id, set())
            for w_norm, w_raw, start, end in tokenize(healed_text):
                if w_norm in ignored_set or healer.check_word_valid(w_norm) is not None:
                    continue
                cands = _compute_inline_ocr_corrections(w_norm, healer, ocr_corr_memo)
                if cands:
                    new_open_issues.append(
                        PageSpellIssue(
                            page_id=page.id,
                            word=w_raw,
                            char_offset=start,
                            char_end=end,
                            ocr_corrections=cands,
                            status="open",
                        )
                    )

        page_update: dict[str, Any] = {
            "text": healed_text,
            "chunking_milestone": PAGE_MILESTONE_IDLE,
            "embedding_milestone": PAGE_MILESTONE_IDLE,
            "is_indexed": False,
            "last_updated": now,
        }
        if spell_check_enabled:
            page_update["spell_check_milestone"] = PAGE_MILESTONE_SUCCEEDED
        if updated_by:
            page_update["updated_by"] = updated_by

        await session.execute(
            update(Page).where(Page.id == page.id).values(**page_update)
        )

        session.add(
            PipelineEvent(
                page_id=page.id,
                event_type="book_auto_correct_succeeded",
                payload=make_pipeline_event_payload(
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                    extra_fields={
                        "book_id": book_id,
                        "page_number": page.page_number,
                        "rule_replacements": n_rule_subs,
                        "ocr_heals": len(heal_records),
                        "records": [
                            {
                                "line": r.line_number,
                                "original": r.original_word,
                                "healed": r.healed_word,
                                "rule": r.rule_label,
                                "source": r.verification_source,
                            }
                            for r in heal_records[:50]
                        ],
                    },
                ),
            )
        )

    if corrected_issue_ids:
        await session.execute(
            update(PageSpellIssue)
            .where(PageSpellIssue.id.in_(corrected_issue_ids))
            .values(status="corrected", auto_corrected_at=now)
        )

    if stale_issue_ids_to_delete:
        await session.execute(
            delete(PageSpellIssue).where(
                PageSpellIssue.id.in_(stale_issue_ids_to_delete)
            )
        )

    if new_open_issues:
        session.add_all(new_open_issues)

    book_updates: dict[str, Any] = {
        "auto_correct_milestone": BOOK_MILESTONE_COMPLETE,
        "last_updated": now,
    }
    if updated_by:
        book_updates["updated_by"] = updated_by

    if pages_modified > 0:
        from app.services.book_structure_service import structure_dirty_values

        await session.execute(
            update(Book)
            .where(Book.id == book_id)
            .values(**structure_dirty_values(**book_updates))
        )
    else:
        await session.execute(
            update(Book).where(Book.id == book_id).values(**book_updates)
        )

    await session.commit()

    await cache_service.delete(f"book:{book_id}")
    await cache_service.delete_pattern(f"book:{book_id}:*")
    if pages_modified > 0:
        await cache_service.delete_pattern(f"rag:search:{book_id}:*")
    await cache_service.bump_namespace_version("books:list")

    return BookAutoHealResult(
        book_id=book_id,
        pages_scanned=pages_scanned,
        pages_modified=pages_modified,
        rule_replacements=total_rule_replacements,
        ocr_heals=total_ocr_heals,
        total_replacements=total_rule_replacements + total_ocr_heals,
        issues_marked_corrected=len(corrected_issue_ids),
        false_positives_cleared=false_positives_cleared,
    )
