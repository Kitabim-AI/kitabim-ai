"""Dictionary lookup repository for chat/RAG retrieval."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Dictionary,
    EnglishUyghurDictionary,
    HistoryDictionary,
    HistoryDictionaryStaging,
    NamesDictionary,
    Word,
)
from app.services.rag.utils import normalize_uyghur_spelling, is_who_is_query


def _sql_normalize_uyghur(column):
    # Standard replacement: ې (\u06d0) -> ى (\u06cc), ى arabic (\u0649) -> ى (\u06cc), ي (\u064a) -> ى (\u06cc)
    normalized = func.replace(column, "\u06d0", "\u06cc")
    normalized = func.replace(normalized, "\u0649", "\u06cc")
    normalized = func.replace(normalized, "\u064a", "\u06cc")
    # Collapse double-y: ىى -> ى
    normalized = func.replace(normalized, "\u06cc\u06cc", "\u06cc")
    return normalized


def _build_fuzzy_term_where(column, norm_term: str):
    words = [w for w in norm_term.split() if len(w) > 1]
    norm_col = _sql_normalize_uyghur(column)
    if len(words) > 1:
        main_word = words[0]
        return (
            norm_col.ilike(f"%{norm_term}%")
            | (
                norm_col.ilike(f"%{main_word}%")
                & (func.similarity(norm_col, norm_term) > 0.4)
            )
            | (func.similarity(norm_col, norm_term) >= 0.65)
        )
    return norm_col.ilike(f"%{norm_term}%") | (
        func.similarity(norm_col, norm_term) > 0.4
    )


def _build_strict_term_where(column, norm_term: str):
    """Stricter than _build_fuzzy_term_where — for extraction-dedup safety
    checks only (find_matching_history_term / find_matching_staging_term),
    where a false match silently discards legitimate new content rather than
    just ranking lower in a search result list.

    _build_fuzzy_term_where's "shares one common word + similarity > 0.4"
    branch is tuned for tolerant search/RAG lookup and caused a 2026-08-03
    production incident: it matched "تارىخى رەشىدى" (a book) against "رىم
    تارىخى" ("History of Rome", similarity 0.47, shared word "تارىخى") and
    "سۇلتان سەئىدخان" (a person) against the bare word "سۇلتان" (similarity
    0.5) — silently skipping every extracted entity as if it already existed.
    This never matches on a single shared common word; it requires either a
    full substring containment or a high overall similarity."""
    norm_col = _sql_normalize_uyghur(column)
    return norm_col.ilike(f"%{norm_term}%") | (
        func.similarity(norm_col, norm_term) >= 0.7
    )


class DictionaryRepository:
    """Read-only lookup helpers across language dictionary tables."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def lookup_uyghur_definition(
        self, term: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        term = term.strip()
        if not term:
            return []

        exact_stmt = (
            select(
                Dictionary.id,
                Dictionary.word,
                Dictionary.definition,
                Dictionary.audio,
                literal(1.0).label("score"),
            )
            .where(Dictionary.word == term)
            .limit(limit)
        )
        exact = await self.session.execute(exact_stmt)
        rows = [dict(r._mapping) for r in exact.all()]
        if rows:
            return rows

        norm_term = normalize_uyghur_spelling(term)
        stmt = (
            select(
                Dictionary.id,
                Dictionary.word,
                Dictionary.definition,
                Dictionary.audio,
                func.similarity(
                    _sql_normalize_uyghur(Dictionary.word), norm_term
                ).label("score"),
            )
            .where(_build_fuzzy_term_where(Dictionary.word, norm_term))
            .order_by(
                func.similarity(
                    _sql_normalize_uyghur(Dictionary.word), norm_term
                ).desc(),
                func.length(Dictionary.word),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def lookup_history_term(
        self, term: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        term = term.strip()
        if not term:
            return []

        exact_stmt = (
            select(
                HistoryDictionary.id,
                HistoryDictionary.term,
                HistoryDictionary.transliteration,
                HistoryDictionary.definition,
                HistoryDictionary.letter_group,
                literal(1.0).label("score"),
            )
            .where(HistoryDictionary.term == term)
            .limit(limit)
        )
        exact = await self.session.execute(exact_stmt)
        rows = [dict(r._mapping) for r in exact.all()]
        if rows:
            return rows

        norm_term = normalize_uyghur_spelling(term)
        stmt = (
            select(
                HistoryDictionary.id,
                HistoryDictionary.term,
                HistoryDictionary.transliteration,
                HistoryDictionary.definition,
                HistoryDictionary.letter_group,
                func.similarity(
                    _sql_normalize_uyghur(HistoryDictionary.term), norm_term
                ).label("score"),
            )
            .where(_build_fuzzy_term_where(HistoryDictionary.term, norm_term))
            .order_by(
                func.similarity(
                    _sql_normalize_uyghur(HistoryDictionary.term), norm_term
                ).desc(),
                func.length(HistoryDictionary.term),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def translate_english_to_uyghur(
        self, english: str, limit: int = 5
    ) -> list[dict[str, Any]]:
        english = english.strip()
        if not english:
            return []

        normalized = english.lower()
        exact_stmt = (
            select(
                EnglishUyghurDictionary.id,
                EnglishUyghurDictionary.english,
                EnglishUyghurDictionary.uyghur,
                EnglishUyghurDictionary.letter_group,
                literal(1.0).label("score"),
            )
            .where(func.lower(EnglishUyghurDictionary.english) == normalized)
            .limit(limit)
        )
        exact = await self.session.execute(exact_stmt)
        rows = [dict(r._mapping) for r in exact.all()]
        if rows:
            return rows

        stmt = (
            select(
                EnglishUyghurDictionary.id,
                EnglishUyghurDictionary.english,
                EnglishUyghurDictionary.uyghur,
                EnglishUyghurDictionary.letter_group,
                func.similarity(EnglishUyghurDictionary.english, english).label(
                    "score"
                ),
            )
            .where(
                EnglishUyghurDictionary.english.ilike(f"%{english}%")
                | (func.similarity(EnglishUyghurDictionary.english, english) > 0.4)
            )
            .order_by(
                func.similarity(EnglishUyghurDictionary.english, english).desc(),
                func.length(EnglishUyghurDictionary.english),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def check_word_spelling(self, word: str, limit: int = 5) -> dict[str, Any]:
        word = word.strip()
        if not word:
            return {"is_known": False, "suggestions": []}

        exact_stmt = select(Word.id, Word.word).where(Word.word == word).limit(1)
        exact = await self.session.execute(exact_stmt)
        exact_row = exact.first()
        if exact_row:
            return {
                "is_known": True,
                "word": exact_row._mapping["word"],
                "suggestions": [],
            }

        norm_word = normalize_uyghur_spelling(word)
        suggestions_stmt = (
            select(
                Word.id,
                Word.word,
                func.similarity(_sql_normalize_uyghur(Word.word), norm_word).label(
                    "score"
                ),
            )
            .where(
                _sql_normalize_uyghur(Word.word).ilike(f"%{norm_word}%")
                | (func.similarity(_sql_normalize_uyghur(Word.word), norm_word) > 0.3)
            )
            .order_by(
                func.similarity(_sql_normalize_uyghur(Word.word), norm_word).desc(),
                func.length(Word.word),
            )
            .limit(limit)
        )
        suggestions = await self.session.execute(suggestions_stmt)
        return {
            "is_known": False,
            "word": word,
            "suggestions": [dict(r._mapping) for r in suggestions.all()],
        }

    async def lookup_name(self, name: str, limit: int = 5) -> list[dict[str, Any]]:
        name = name.strip()
        if not name or is_who_is_query(name):
            return []

        norm_name = normalize_uyghur_spelling(name)
        stmt = (
            select(
                NamesDictionary.id,
                NamesDictionary.name,
                NamesDictionary.letter_group,
                func.similarity(
                    _sql_normalize_uyghur(NamesDictionary.name), norm_name
                ).label("score"),
            )
            .where(_build_fuzzy_term_where(NamesDictionary.name, norm_name))
            .order_by(
                func.similarity(
                    _sql_normalize_uyghur(NamesDictionary.name), norm_name
                ).desc(),
                func.length(NamesDictionary.name),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def lookup_proverbs(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        from app.db.models import Proverb

        query = query.strip()
        if not query:
            return []
        stmt = (
            select(
                Proverb.id,
                Proverb.text,
                Proverb.volume,
                Proverb.page_number,
            )
            .where(Proverb.text.op("~*")(query))
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def lookup_synonyms(self, query: str, limit: int = 3) -> list[dict[str, Any]]:
        from app.db.models import Synonym

        query = query.strip()
        if not query:
            return []

        norm_query = normalize_uyghur_spelling(query)
        stmt = (
            select(
                Synonym.id,
                Synonym.word,
                Synonym.letter_group,
                Synonym.synonyms,
                func.similarity(_sql_normalize_uyghur(Synonym.word), norm_query).label(
                    "score"
                ),
            )
            .where(_build_fuzzy_term_where(Synonym.word, norm_query))
            .order_by(
                func.similarity(_sql_normalize_uyghur(Synonym.word), norm_query).desc(),
                func.length(Synonym.word),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return [dict(r._mapping) for r in res.all()]

    async def search_language_sources(
        self, query: str, limit_per_source: int = 3
    ) -> dict[str, list[dict[str, Any]]]:
        """Search all phase-1 dictionary sources with exact/fuzzy term matching."""
        return {
            "dictionary": await self.lookup_uyghur_definition(query, limit_per_source),
            "history_dictionary": await self.lookup_history_term(
                query, limit_per_source
            ),
            "english_uyghur_dictionary": await self.translate_english_to_uyghur(
                query, limit_per_source
            ),
            "names_dictionary": await self.lookup_name(query, limit_per_source),
            "proverbs": await self.lookup_proverbs(query, limit_per_source),
            "synonyms_dictionary": await self.lookup_synonyms(query, limit_per_source),
        }

    async def create_staging_term(
        self,
        book_id: str,
        term: str,
        letter_group: str,
        definition: str | None = None,
        transliteration: str | None = None,
        original_definition: str | None = None,
        category: str = "general",
        significance_score: int = 5,
        significance_reason: str | None = None,
        is_ai_generated: bool = True,
        entry_type: str = "new",
        existing_dictionary_id: int | None = None,
        facts: list[dict[str, Any]] | None = None,
    ) -> HistoryDictionaryStaging:
        """Create a new staging candidate entry."""
        staging = HistoryDictionaryStaging(
            book_id=book_id,
            term=term.strip(),
            transliteration=transliteration.strip() if transliteration else None,
            definition=definition.strip() if definition else None,
            original_definition=original_definition.strip()
            if original_definition
            else None,
            category=category,
            significance_score=significance_score,
            significance_reason=significance_reason,
            is_ai_generated=is_ai_generated,
            entry_type=entry_type,
            existing_dictionary_id=existing_dictionary_id,
            letter_group=letter_group,
            facts=facts or [],
            status="pending",
        )
        self.session.add(staging)
        await self.session.flush()
        return staging

    async def get_staging_terms(
        self,
        status: str = "pending",
        category: str | None = None,
        min_significance: int | None = None,
        book_id: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Fetch paginated staging terms ordered by significance_score DESC."""
        from app.models.schemas import HistoryStagingItem

        stmt = select(HistoryDictionaryStaging).where(
            HistoryDictionaryStaging.status == status
        )
        if category:
            stmt = stmt.where(HistoryDictionaryStaging.category == category)
        if min_significance is not None:
            stmt = stmt.where(
                HistoryDictionaryStaging.significance_score >= min_significance
            )
        if book_id:
            stmt = stmt.where(HistoryDictionaryStaging.book_id == book_id)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        # Order by significance_score DESC, then created_at DESC
        stmt = (
            stmt.order_by(
                HistoryDictionaryStaging.significance_score.desc(),
                HistoryDictionaryStaging.created_at.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )

        res = await self.session.execute(stmt)
        rows = res.scalars().all()
        items = [
            HistoryStagingItem.model_validate(r).model_dump(by_alias=True) for r in rows
        ]

        return {
            "items": items,
            "total": total,
            "page": page,
            "pageSize": page_size,
        }

    async def get_staging_term_by_id(
        self, staging_id: int
    ) -> HistoryDictionaryStaging | None:
        stmt = select(HistoryDictionaryStaging).where(
            HistoryDictionaryStaging.id == staging_id
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_matching_history_term(self, term: str) -> HistoryDictionary | None:
        """Find an existing published HistoryDictionary entry using normalized spelling and similarity.

        Uses the strict matcher, not the search-tolerant one — a false match
        here silently discards legitimate extraction output (see
        _build_strict_term_where)."""
        norm_term = normalize_uyghur_spelling(term)
        stmt = (
            select(HistoryDictionary)
            .where(_build_strict_term_where(HistoryDictionary.term, norm_term))
            .order_by(
                func.similarity(
                    _sql_normalize_uyghur(HistoryDictionary.term), norm_term
                ).desc()
            )
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def find_matching_staging_term(
        self, term: str
    ) -> HistoryDictionaryStaging | None:
        """Find an existing pending staging term using normalized spelling and similarity.

        Uses the strict matcher, not the search-tolerant one — see
        _build_strict_term_where."""
        norm_term = normalize_uyghur_spelling(term)
        stmt = (
            select(HistoryDictionaryStaging)
            .where(
                HistoryDictionaryStaging.status == "pending",
                _build_strict_term_where(HistoryDictionaryStaging.term, norm_term),
            )
            .order_by(
                func.similarity(
                    _sql_normalize_uyghur(HistoryDictionaryStaging.term), norm_term
                ).desc()
            )
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_history_dictionary_by_id(
        self, entry_id: int
    ) -> HistoryDictionary | None:
        stmt = select(HistoryDictionary).where(HistoryDictionary.id == entry_id)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_history_dictionary_by_term(
        self, term: str
    ) -> HistoryDictionary | None:
        stmt = select(HistoryDictionary).where(HistoryDictionary.term == term)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def create_history_dictionary_entry(self, **fields: Any) -> HistoryDictionary:
        """Insert a new live history_dictionary record. Caller owns the transaction."""
        entry = HistoryDictionary(**fields)
        self.session.add(entry)
        await self.session.flush()
        return entry

    async def update_history_dictionary_entry(
        self, entry: HistoryDictionary, **fields: Any
    ) -> HistoryDictionary:
        """Apply field updates to an existing live history_dictionary record."""
        for key, value in fields.items():
            setattr(entry, key, value)
        await self.session.flush()
        return entry

    async def update_staging_term(
        self, staging: HistoryDictionaryStaging, **fields: Any
    ) -> HistoryDictionaryStaging:
        """Apply field updates to an existing pending staging record."""
        for key, value in fields.items():
            setattr(staging, key, value)
        await self.session.flush()
        return staging

    async def set_staging_status(
        self, staging: HistoryDictionaryStaging, status: str
    ) -> None:
        staging.status = status
        await self.session.flush()
