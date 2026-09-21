"""Repository for per-user, per-book silent reading progress (resume position)"""

from typing import List, Optional
import uuid
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import func, select
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
        """Create or update this user's saved page for a book atomically"""
        stmt = pg_insert(ReadingProgress).values(
            id=str(uuid.uuid4()),
            user_id=user_id,
            book_id=book_id,
            page_number=page_number,
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_reading_progress_user_book",
            set_={
                "page_number": stmt.excluded.page_number,
                "updated_at": func.now(),
            },
        ).returning(ReadingProgress)
        result = await self.session.execute(stmt)
        progress = result.scalar_one()
        await self.session.commit()
        return progress

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
