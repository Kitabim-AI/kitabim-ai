"""Synonyms repository — Uyghur synonym dictionary lookup."""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Synonym
from app.db.repositories.base_repository import BaseRepository
from app.db.repositories.dictionary_repository import _sql_normalize_uyghur
from app.services.rag.utils import normalize_uyghur_spelling


class SynonymsRepository(BaseRepository[Synonym]):
    """Repository for the Uyghur synonym dictionary (word -> synonym list)."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Synonym)

    async def lookup_word(self, word: str) -> Optional[Synonym]:
        """Exact headword lookup."""
        word = word.strip()
        if not word:
            return None
        stmt = select(Synonym).where(Synonym.word == word)
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def search_fuzzy(self, term: str, limit: int = 5) -> List[Synonym]:
        """Fuzzy headword search — trigram similarity, same pattern as
        DictionaryRepository.lookup_uyghur_definition/lookup_name."""
        term = term.strip()
        if not term:
            return []

        norm_term = normalize_uyghur_spelling(term)
        stmt = (
            select(Synonym)
            .where(
                _sql_normalize_uyghur(Synonym.word).ilike(f"%{norm_term}%")
                | (
                    func.similarity(_sql_normalize_uyghur(Synonym.word), norm_term)
                    > 0.3
                )
            )
            .order_by(
                func.similarity(_sql_normalize_uyghur(Synonym.word), norm_term).desc(),
                func.length(Synonym.word),
            )
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_by_letter_group(
        self, letter_group: str, limit: int = 100
    ) -> List[Synonym]:
        """List headwords in a given letter group, e.g. for 'words starting with ب'."""
        stmt = (
            select(Synonym)
            .where(Synonym.letter_group == letter_group)
            .order_by(Synonym.word)
            .limit(limit)
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())


def get_synonyms_repository(session: AsyncSession) -> SynonymsRepository:
    """Factory function for dependency injection"""
    return SynonymsRepository(session)
