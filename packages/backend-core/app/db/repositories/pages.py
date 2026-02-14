"""Pages repository with upsert operations"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Page
from app.db.repositories.base import BaseRepository


class PagesRepository(BaseRepository[Page]):
    """Repository for pages with upsert operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Page)

    async def find_by_book(
        self,
        book_id: str,
        skip: int = 0,
        limit: int = 10000
    ) -> List[Page]:
        """Find all pages for a book, ordered by page number"""
        stmt = (
            select(Page)
            .where(Page.book_id == book_id)
            .order_by(Page.page_number)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_one(
        self,
        book_id: str,
        page_number: int
    ) -> Optional[Page]:
        """Find a specific page by book ID and page number"""
        stmt = select(Page).where(
            Page.book_id == book_id,
            Page.page_number == page_number
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, page_data: dict) -> Page:
        """
        Upsert a page using PostgreSQL INSERT ... ON CONFLICT.

        Replaces the manual SQL with SQLAlchemy's insert().on_conflict_do_update().
        This is critical for OCR processing where pages may be reprocessed.
        """
        stmt = insert(Page).values(**page_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["book_id", "page_number"],
            set_={
                "text": stmt.excluded.text,
                "status": stmt.excluded.status,
                "embedding": stmt.excluded.embedding,
                "is_verified": stmt.excluded.is_verified,
                "error": stmt.excluded.error,
                "ocr_provider": stmt.excluded.ocr_provider,
                "updated_by": stmt.excluded.updated_by,
                "last_updated": func.now(),
            }
        )
        stmt = stmt.returning(Page)

        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

    async def update_status(
        self,
        book_id: str,
        page_number: int,
        status: str,
        error: Optional[str] = None
    ) -> Optional[Page]:
        """Update page status and optional error message"""
        from sqlalchemy import update

        values = {"status": status, "last_updated": func.now()}
        if error is not None:
            values["error"] = error

        stmt = (
            update(Page)
            .where(
                Page.book_id == book_id,
                Page.page_number == page_number
            )
            .values(**values)
            .returning(Page)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def update_many_status(
        self,
        book_id: str,
        page_numbers: List[int],
        status: str
    ) -> int:
        """Update status for multiple pages"""
        from sqlalchemy import update

        stmt = (
            update(Page)
            .where(
                Page.book_id == book_id,
                Page.page_number.in_(page_numbers)
            )
            .values(status=status, last_updated=func.now())
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_by_book(self, book_id: str) -> int:
        """Delete all pages for a book"""
        stmt = delete(Page).where(Page.book_id == book_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_by_book(self, book_id: str, status: Optional[str] = None) -> int:
        """Count pages for a book, optionally filtered by status"""
        stmt = select(func.count()).select_from(Page).where(Page.book_id == book_id)

        if status:
            stmt = stmt.where(Page.status == status)

        result = await self.session.execute(stmt)
        return result.scalar_one()


def get_pages_repository(session: AsyncSession) -> PagesRepository:
    """Factory function for dependency injection"""
    return PagesRepository(session)
