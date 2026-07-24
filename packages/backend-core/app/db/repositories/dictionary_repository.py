"""Dictionary lookup repository for chat/RAG retrieval."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Dictionary,
    EnglishUyghurDictionary,
    HistoryDictionary,
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
