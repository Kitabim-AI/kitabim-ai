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

        stmt = (
            select(
                Dictionary.id,
                Dictionary.word,
                Dictionary.definition,
                Dictionary.audio,
                func.similarity(Dictionary.word, term).label("score"),
            )
            .where(
                Dictionary.word.ilike(f"%{term}%")
                | (func.similarity(Dictionary.word, term) > 0.2)
            )
            .order_by(
                func.similarity(Dictionary.word, term).desc(),
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

        stmt = (
            select(
                HistoryDictionary.id,
                HistoryDictionary.term,
                HistoryDictionary.transliteration,
                HistoryDictionary.definition,
                HistoryDictionary.letter_group,
                func.similarity(HistoryDictionary.term, term).label("score"),
            )
            .where(
                HistoryDictionary.term.ilike(f"%{term}%")
                | (func.similarity(HistoryDictionary.term, term) > 0.2)
            )
            .order_by(
                func.similarity(HistoryDictionary.term, term).desc(),
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
                | (func.similarity(EnglishUyghurDictionary.english, english) > 0.2)
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

        suggestions_stmt = (
            select(Word.id, Word.word, func.similarity(Word.word, word).label("score"))
            .where(
                Word.word.ilike(f"%{word}%") | (func.similarity(Word.word, word) > 0.2)
            )
            .order_by(func.similarity(Word.word, word).desc(), func.length(Word.word))
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
        if not name:
            return []

        stmt = (
            select(
                NamesDictionary.id,
                NamesDictionary.name,
                NamesDictionary.letter_group,
                func.similarity(NamesDictionary.name, name).label("score"),
            )
            .where(
                NamesDictionary.name.ilike(f"%{name}%")
                | (func.similarity(NamesDictionary.name, name) > 0.2)
            )
            .order_by(
                func.similarity(NamesDictionary.name, name).desc(),
                func.length(NamesDictionary.name),
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
        }
