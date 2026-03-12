"""Books repository with SQLAlchemy"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func, or_, and_, case, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Book, Page, BookSummary
from app.db.repositories.base import BaseRepository


PIPELINE_ORDER = ["ocr", "chunking", "embedding", "word_index", "spell_check"]


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

    async def find_by_filename(self, file_name: str) -> Optional[Book]:
        """Find book by file name"""
        result = await self.session.execute(
            select(Book).where(Book.file_name == file_name)
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
        if sort_by == "upload_date":
            # Enhanced sorting: Group by (title, author) but sort groups by latest arrival,
            # and then sort volumes within each group.
            # This uses a window function to find the max upload date for each 'Work' (Series)
            series_latest = func.max(Book.upload_date).over(partition_by=[Book.title, Book.author])
            
            if sort_order.upper() == "DESC":
                stmt = stmt.order_by(
                    series_latest.desc(), 
                    Book.title.asc(), 
                    Book.author.asc(),
                    Book.volume.asc().nulls_first()
                )
            else:
                stmt = stmt.order_by(
                    series_latest.asc(), 
                    Book.title.asc(), 
                    Book.author.asc(),
                    Book.volume.asc().nulls_first()
                )
        elif hasattr(Book, sort_by):
            order_col = getattr(Book, sort_by)
            if sort_order.upper() == "DESC":
                stmt = stmt.order_by(order_col.desc())
            else:
                stmt = stmt.order_by(order_col.asc())
        else:
            # Default fallback (same as upload_date enhanced)
            series_latest = func.max(Book.upload_date).over(partition_by=[Book.title, Book.author])
            stmt = stmt.order_by(series_latest.desc(), Book.title.asc(), Book.author.asc(), Book.volume.asc().nulls_first())

        # Pagination
        stmt = stmt.offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_page_stats(self, book_id: str) -> Optional[dict]:
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
                Page.pipeline_step,
                Page.milestone,
                func.count(Page.id).label("count")
            )
            .where(Page.book_id == book_id)
            .group_by(Page.pipeline_step, Page.milestone)
        )

        stats_result = await self.session.execute(stats_stmt)
        # Stats is a dict of {(pipeline_step, milestone): count}
        stats_data = {(row.pipeline_step, row.milestone): row.count for row in stats_result}
        
        # Add new milestone counts to stats_data for decoupled columns
        milestone_stats_stmt = (
            select(
                func.count(Page.id).label("total"),
                func.count(case((Page.ocr_milestone == "succeeded", Page.id), else_=None)).label("ocr_done"),
                func.count(case((Page.ocr_milestone.in_(["failed", "error"]), Page.id), else_=None)).label("ocr_failed"),
                func.count(case((Page.ocr_milestone == "in_progress", Page.id), else_=None)).label("ocr_active"),
                func.count(case((Page.chunking_milestone == "succeeded", Page.id), else_=None)).label("chunking_done"),
                func.count(case((Page.chunking_milestone.in_(["failed", "error"]), Page.id), else_=None)).label("chunking_failed"),
                func.count(case((Page.chunking_milestone == "in_progress", Page.id), else_=None)).label("chunking_active"),
                func.count(case((Page.embedding_milestone == "succeeded", Page.id), else_=None)).label("embedding_done"),
                func.count(case((Page.embedding_milestone.in_(["failed", "error"]), Page.id), else_=None)).label("embedding_failed"),
                func.count(case((Page.embedding_milestone == "in_progress", Page.id), else_=None)).label("embedding_active"),
                func.count(case((Page.word_index_milestone == "done", Page.id), else_=None)).label("word_index_done"),
                func.count(case((Page.word_index_milestone.in_(["failed", "error"]), Page.id), else_=None)).label("word_index_failed"),
                func.count(case((Page.word_index_milestone == "in_progress", Page.id), else_=None)).label("word_index_active"),
                func.count(case((Page.spell_check_milestone == "done", Page.id), else_=None)).label("spell_check_done"),
                func.count(case((Page.spell_check_milestone.in_(["failed", "error"]), Page.id), else_=None)).label("spell_check_failed"),
                func.count(case((Page.spell_check_milestone == "in_progress", Page.id), else_=None)).label("spell_check_active"),
            )
            .where(Page.book_id == book_id)
        )
        m_result = await self.session.execute(milestone_stats_stmt)
        m_row = m_result.fetchone()
        
        # Determine if summary exists
        summary_stmt = select(func.count(BookSummary.book_id)).where(BookSummary.book_id == book_id)
        summary_res = await self.session.execute(summary_stmt)
        has_summary = (summary_res.scalar() or 0) > 0

        # Calculate cumulative pipeline stats
        pipeline_stats = {}

        for i, step in enumerate(PIPELINE_ORDER):
            # A page is "done" with 'step' if:
            # 1. Its pipeline_step is further in the PIPELINE_ORDER than 'step'
            # 2. Its pipeline_step is 'step' AND its milestone is 'succeeded'
            # 3. Its pipeline_step is "ready" (terminal state for the whole book)
            
            done_count = 0
            for (p_step, p_milestone), count in stats_data.items():
                if p_step == "ready":
                    done_count += count
                    continue
                
                if p_step is None:
                    continue
                
                try:
                    p_step_idx = PIPELINE_ORDER.index(p_step)
                    if p_step_idx > i:
                        done_count += count
                    elif p_step_idx == i and p_milestone == "succeeded":
                        done_count += count
                except ValueError:
                    # Unknown step, ignore for specific pipeline stats
                    pass
            
            pipeline_stats[step] = done_count

        return {
            "book": book,
            "page_stats": {f"{s or 'none'}_{m or 'none'}": c for (s, m), c in stats_data.items()},
            "pipeline_stats": {
                "ocr": m_row.ocr_done if m_row else 0,
                "ocr_failed": m_row.ocr_failed if m_row else 0,
                "ocr_active": m_row.ocr_active if m_row else 0,
                "chunking": m_row.chunking_done if m_row else 0,
                "chunking_failed": m_row.chunking_failed if m_row else 0,
                "chunking_active": m_row.chunking_active if m_row else 0,
                "embedding": m_row.embedding_done if m_row else 0,
                "embedding_failed": m_row.embedding_failed if m_row else 0,
                "embedding_active": m_row.embedding_active if m_row else 0,
                "word_index": m_row.word_index_done if m_row else 0,
                "word_index_failed": m_row.word_index_failed if m_row else 0,
                "word_index_active": m_row.word_index_active if m_row else 0,
                "spell_check": m_row.spell_check_done if m_row else 0,
                "spell_check_failed": m_row.spell_check_failed if m_row else 0,
                "spell_check_active": m_row.spell_check_active if m_row else 0,
            },
            "has_summary": has_summary,
            "ocr_done_count": m_row.ocr_done if m_row else 0,
            "error_count": sum(count for (s, m), count in stats_data.items() if m == "failed"),
            "pending_count": sum(count for (s, m), count in stats_data.items() if m == "idle"),
            "ocr_processing_count": sum(count for (s, m), count in stats_data.items() if m == "in_progress"),
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

    async def find_stale_processing_books(self, cutoff_time: datetime) -> List[Book]:
        """Find books stuck in processing state since before cutoff_time"""
        stmt = select(Book).where(
            and_(
                Book.status == 'ocr_processing',
                Book.last_updated < cutoff_time
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_stale_pending_books(self, cutoff_time: datetime) -> List[Book]:
        """Find books stuck in pending state since before cutoff_time"""
        stmt = select(Book).where(
            and_(
                Book.status == 'pending',
                Book.last_updated < cutoff_time
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_stale_ocr_done_books(self, cutoff_time: datetime) -> List[Book]:
        """Find books stuck in ocr_done state since before cutoff_time.
        These have finished OCR but indexing/embedding never started."""
        stmt = select(Book).where(
            and_(
                Book.status == 'ocr_done',
                Book.last_updated < cutoff_time
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_stale_indexing_books(self, cutoff_time: datetime) -> List[Book]:
        """Find books stuck in indexing state since before cutoff_time.
        These started embedding but never finished (e.g. process crashed mid-embedding)."""
        stmt = select(Book).where(
            and_(
                Book.status == 'indexing',
                Book.last_updated < cutoff_time
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def get_books_repository(session: AsyncSession) -> BooksRepository:
    """Factory function for dependency injection"""
    return BooksRepository(session)
