"""Repository for per-user, per-book silent reading progress (resume position)"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ReadingProgress
from app.db.repositories.base_repository import BaseRepository


class ReadingProgressRepository(BaseRepository[ReadingProgress]):
    """Repository for reading_progress rows"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ReadingProgress)

    async def upsert(
        self, user_id: str, book_id: str, page_number: int
    ) -> ReadingProgress:
        """Create or update this user's saved page for a book"""
        existing = await self.get_for_book(user_id, book_id)
        if existing:
            existing.page_number = page_number
        else:
            existing = ReadingProgress(
                user_id=user_id, book_id=book_id, page_number=page_number
            )
            self.session.add(existing)
        await self.session.commit()
        await self.session.refresh(existing)
        return existing

    async def get_for_book(
        self, user_id: str, book_id: str
    ) -> Optional[ReadingProgress]:
        """Fetch this user's saved progress for a single book, if any"""
        stmt = select(ReadingProgress).where(
            ReadingProgress.user_id == user_id, ReadingProgress.book_id == book_id
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, user_id: str, limit: int = 50) -> List[ReadingProgress]:
        """List this user's books with progress, most recently updated first"""
        stmt = (
            select(ReadingProgress)
            .where(ReadingProgress.user_id == user_id)
            .order_by(ReadingProgress.updated_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def get_reading_progress_repository(session: AsyncSession) -> ReadingProgressRepository:
    """Factory helper for ReadingProgressRepository"""
    return ReadingProgressRepository(session)
