"""Proverbs repository"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Proverb
from app.db.repositories.base import BaseRepository


class ProverbsRepository(BaseRepository[Proverb]):
    """Repository for proverbs with random selection"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Proverb)

    async def find_by_text_pattern(self, pattern: str) -> List[Proverb]:
        """Find proverbs matching a text pattern using PostgreSQL regex"""
        stmt = select(Proverb).where(
            Proverb.text.op("~*")(pattern)  # Case-insensitive regex
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_random_proverb(self, text_pattern: Optional[str] = None) -> Optional[Proverb]:
        """
        Get a random proverb, optionally filtered by text pattern.

        Uses PostgreSQL's RANDOM() function for efficient random selection.
        """
        stmt = select(Proverb)

        if text_pattern:
            stmt = stmt.where(Proverb.text.op("~*")(text_pattern))

        # Use ORDER BY RANDOM() LIMIT 1 for efficient random selection
        stmt = stmt.order_by(func.random()).limit(1)

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_matching(self, text_pattern: str) -> int:
        """Count proverbs matching a text pattern"""
        stmt = select(func.count()).select_from(Proverb).where(
            Proverb.text.op("~*")(text_pattern)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one()


def get_proverbs_repository(session: AsyncSession) -> ProverbsRepository:
    """Factory function for dependency injection"""
    return ProverbsRepository(session)
