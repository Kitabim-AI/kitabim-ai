"""Books repository with SQLAlchemy"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Book, Page
from app.db.repositories.base import BaseRepository


class BooksRepository(BaseRepository[Book]):
    """Repository for books with custom query methods"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Book)

    async def find_by_hash(self, content_hash: str) -> Optional[Book]:
        """Find book by content hash (for duplicate detection)"""
        result = await self.session.execute(
            select(Book).where(Book.content_hash == content_hash)
        )
        return result.scalar_one_or_none()

    async def find_many(
        self,
        status: Optional[str] = None,
        visibility: Optional[str] = None,
        categories: Optional[List[str]] = None,
        search_query: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        sort_by: str = "upload_date",
        sort_order: str = "DESC"
    ) -> List[Book]:
        """
        Find books with filtering, search, and pagination.

        Replaces the complex MongoDB-style query building in postgres_helpers.py.
        """
        stmt = select(Book)

        # Build WHERE conditions
        conditions = []

        if status:
            conditions.append(Book.status == status)

        if visibility:
            conditions.append(Book.visibility == visibility)

        if categories:
            # PostgreSQL array overlap operator &&
            # This checks if any category in the list exists in the book's categories array
            conditions.append(Book.categories.overlap(categories))

        if search_query:
            # Full-text search across title, author, categories
            search_filter = or_(
                Book.title.ilike(f"%{search_query}%"),
                Book.author.ilike(f"%{search_query}%"),
                # For array search, we need to use PostgreSQL-specific syntax
                # This is a simplified version; full-text search may need more sophistication
            )
            conditions.append(search_filter)

        if conditions:
            stmt = stmt.where(and_(*conditions))

        # Sorting
        if hasattr(Book, sort_by):
            order_col = getattr(Book, sort_by)
            if sort_order.upper() == "DESC":
                stmt = stmt.order_by(order_col.desc())
            else:
                stmt = stmt.order_by(order_col.asc())
        else:
            # Default fallback
            stmt = stmt.order_by(Book.upload_date.desc())

        # Pagination
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_page_stats(self, book_id: UUID) -> Optional[dict]:
        """
        Get book with aggregated page statistics.

        Returns book data along with page counts by status.
        """
        # First get the book
        book = await self.get(book_id)
        if not book:
            return None

        # Aggregate page stats
        stats_stmt = (
            select(
                Page.status,
                func.count(Page.id).label("count")
            )
            .where(Page.book_id == book_id)
            .group_by(Page.status)
        )

        stats_result = await self.session.execute(stats_stmt)
        stats = {row.status: row.count for row in stats_result}

        return {
            "book": book,
            "page_stats": stats,
            "completed_count": stats.get("completed", 0),
            "error_count": stats.get("error", 0),
            "pending_count": stats.get("pending", 0),
            "processing_count": stats.get("processing", 0),
        }

    async def count_by_status(self, status: str) -> int:
        """Count books by status"""
        return await self.count(status=status)

    async def count_by_visibility(self, visibility: str, status: Optional[str] = None) -> int:
        """Count books by visibility and optional status"""
        stmt = select(func.count()).select_from(Book).where(Book.visibility == visibility)

        if status:
            stmt = stmt.where(Book.status == status)

        result = await self.session.execute(stmt)
        return result.scalar_one()


def get_books_repository(session: AsyncSession) -> BooksRepository:
    """Factory function for dependency injection"""
    return BooksRepository(session)
