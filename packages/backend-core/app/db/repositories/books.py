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

    async def get_with_page_stats(self, book_id: str, step: Optional[str] = None) -> Optional[dict]:
        """
        Get book with aggregated page statistics.

        Args:
            book_id: The book ID to query
            step: Optional pipeline step to query (ocr, chunking, embedding, word_index, spell_check, summary)
                  If provided, only queries that specific step for performance optimization.

        Returns book data along with page counts by status.
        """
        # First get the book
        book = await self.get(book_id)
        if not book:
            return None

        # Optimization: If book is ready, we can return 100% stats for core steps
        if book.status == "ready":
            tp = book.total_pages or 0
            summary_stmt = select(func.count(BookSummary.book_id)).where(BookSummary.book_id == book_id)
            summary_res = await self.session.execute(summary_stmt)
            has_summary = (summary_res.scalar() or 0) > 0
            
            # For ready books, we still need to check if background spell check is running
            sc_stmt = (
                select(
                    func.count(case((Page.spell_check_milestone == "done", 1))).label("done"),
                    func.count(case((Page.spell_check_milestone.in_(["failed", "error"]), 1))).label("failed"),
                    func.count(case((Page.spell_check_milestone == "in_progress", 1))).label("active")
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
            sc_res = await self.session.execute(sc_stmt)
            sc_row = sc_res.fetchone()
            
            sc_done = sc_row.done if sc_row else tp
            sc_failed = sc_row.failed if sc_row else 0
            sc_active = sc_row.active if sc_row else 0

            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    "ocr": tp, "ocr_failed": 0, "ocr_active": 0,
                    "chunking": tp, "chunking_failed": 0, "chunking_active": 0,
                    "embedding": tp, "embedding_failed": 0, "embedding_active": 0,
                    "word_index": tp, "word_index_failed": 0, "word_index_active": 0,
                    "spell_check": sc_done, 
                    "spell_check_failed": sc_failed, 
                    "spell_check_active": sc_active,
                },
                "has_summary": has_summary,
                "ocr_done_count": tp,
                "error_count": sc_failed,
                "pending_count": tp - sc_done - sc_active - sc_failed,
                "ocr_processing_count": 0,
            }

        # Build query based on which step(s) to fetch
        # If step is provided, only query that specific step for performance
        if step and step != 'summary':
            # Single-step query optimization
            milestone_field_map = {
                'ocr': Page.ocr_milestone,
                'chunking': Page.chunking_milestone,
                'embedding': Page.embedding_milestone,
                'word_index': Page.word_index_milestone,
                'spell_check': Page.spell_check_milestone,
            }

            milestone_field = milestone_field_map.get(step)
            if not milestone_field:
                # Invalid step, return empty stats
                return {
                    "book": book,
                    "page_stats": {},
                    "pipeline_stats": {},
                    "has_summary": False,
                    "ocr_done_count": 0,
                    "error_count": 0,
                    "pending_count": 0,
                    "ocr_processing_count": 0,
                }

            # Query only the specific step
            done_value = "done" if step == 'word_index' or step == 'spell_check' else "succeeded"
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(case((milestone_field == done_value, 1))).label(f"{step}_done"),
                    func.count(case((milestone_field.in_(["failed", "error"]), 1))).label(f"{step}_failed"),
                    func.count(case((milestone_field == "in_progress", 1))).label(f"{step}_active"),
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
        else:
            # Query all steps (original behavior)
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(case((Page.ocr_milestone == "succeeded", 1))).label("ocr_done"),
                    func.count(case((Page.ocr_milestone.in_(["failed", "error"]), 1))).label("ocr_failed"),
                    func.count(case((Page.ocr_milestone == "in_progress", 1))).label("ocr_active"),
                    func.count(case((Page.chunking_milestone == "succeeded", 1))).label("chunking_done"),
                    func.count(case((Page.chunking_milestone.in_(["failed", "error"]), 1))).label("chunking_failed"),
                    func.count(case((Page.chunking_milestone == "in_progress", 1))).label("chunking_active"),
                    func.count(case((Page.embedding_milestone == "succeeded", 1))).label("embedding_done"),
                    func.count(case((Page.embedding_milestone.in_(["failed", "error"]), 1))).label("embedding_failed"),
                    func.count(case((Page.embedding_milestone == "in_progress", 1))).label("embedding_active"),
                    func.count(case((Page.word_index_milestone == "done", 1))).label("word_index_done"),
                    func.count(case((Page.word_index_milestone.in_(["failed", "error"]), 1))).label("word_index_failed"),
                    func.count(case((Page.word_index_milestone == "in_progress", 1))).label("word_index_active"),
                    func.count(case((Page.spell_check_milestone == "done", 1))).label("spell_check_done"),
                    func.count(case((Page.spell_check_milestone.in_(["failed", "error"]), 1))).label("spell_check_failed"),
                    func.count(case((Page.spell_check_milestone == "in_progress", 1))).label("spell_check_active"),
                    func.count(case((Page.milestone == "idle", 1))).label("pending_count"),
                    func.count(case((Page.milestone == "in_progress", 1))).label("processing_count")
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )

        stats_result = await self.session.execute(stats_stmt)
        row = stats_result.fetchone()

        # Determine if summary exists (only if requested or querying all)
        has_summary = False
        if not step or step == 'summary':
            summary_stmt = select(func.count(BookSummary.book_id)).where(BookSummary.book_id == book_id)
            summary_res = await self.session.execute(summary_stmt)
            has_summary = (summary_res.scalar() or 0) > 0

        # Handle single-step response
        if step and step != 'summary':
            if not row:
                return {
                    "book": book,
                    "page_stats": {},
                    "pipeline_stats": {
                        step: 0,
                        f"{step}_failed": 0,
                        f"{step}_active": 0,
                    },
                    "has_summary": False,
                    "ocr_done_count": 0,
                    "error_count": 0,
                    "pending_count": 0,
                    "ocr_processing_count": 0,
                }

            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    step: getattr(row, f"{step}_done", 0) or 0,
                    f"{step}_failed": getattr(row, f"{step}_failed", 0) or 0,
                    f"{step}_active": getattr(row, f"{step}_active", 0) or 0,
                },
                "has_summary": False,
                "ocr_done_count": 0,
                "error_count": 0,
                "pending_count": 0,
                "ocr_processing_count": 0,
            }

        # Handle all-steps response (original behavior)
        # If no pages exist yet
        if not row:
            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    "ocr": 0, "ocr_failed": 0, "ocr_active": 0,
                    "chunking": 0, "chunking_failed": 0, "chunking_active": 0,
                    "embedding": 0, "embedding_failed": 0, "embedding_active": 0,
                    "word_index": 0, "word_index_failed": 0, "word_index_active": 0,
                    "spell_check": 0, "spell_check_failed": 0, "spell_check_active": 0,
                },
                "has_summary": has_summary,
                "ocr_done_count": 0,
                "error_count": 0,
                "pending_count": 0,
                "ocr_processing_count": 0,
            }

        return {
            "book": book,
            "page_stats": {}, # Removed detailed_stats to avoid DB errors; use pipeline_stats instead
            "pipeline_stats": {
                "ocr": row.ocr_done or 0,
                "ocr_failed": row.ocr_failed or 0,
                "ocr_active": row.ocr_active or 0,
                "chunking": row.chunking_done or 0,
                "chunking_failed": row.chunking_failed or 0,
                "chunking_active": row.chunking_active or 0,
                "embedding": row.embedding_done or 0,
                "embedding_failed": row.embedding_failed or 0,
                "embedding_active": row.embedding_active or 0,
                "word_index": row.word_index_done or 0,
                "word_index_failed": row.word_index_failed or 0,
                "word_index_active": row.word_index_active or 0,
                "spell_check": row.spell_check_done or 0,
                "spell_check_failed": row.spell_check_failed or 0,
                "spell_check_active": row.spell_check_active or 0,
            },
            "has_summary": has_summary,
            "ocr_done_count": row.ocr_done or 0,
            "error_count": (row.ocr_failed or 0) + (row.chunking_failed or 0) + (row.embedding_failed or 0) + (row.word_index_failed or 0) + (row.spell_check_failed or 0),
            "pending_count": row.pending_count or 0,
            "ocr_processing_count": row.processing_count or 0,
        }

    async def get_batch_stats(self, book_ids: List[str]) -> dict[str, dict]:
        """
        Fetch pipeline statistics and summary status for multiple books in batch.
        Replaces N+1 calls to get_with_page_stats for much better performance.
        """
        if not book_ids:
            return {}

        # Use a short-lived cache for batch stats to avoid hitting the pages table 
        # on every admin page refresh/poll (books don't change that fast)
        # Note: We use a simple in-memory cache for now
        
        # 0. Optimization: Identify which books are 'ready' vs 'processing'
        # For 'ready' books, we can assume 100% stats and skip scanning pages
        books_stmt = select(Book.id, Book.status, Book.total_pages).where(Book.id.in_(book_ids))
        books_res = await self.session.execute(books_stmt)
        books_info = {str(row.id): {"status": row.status, "total_pages": row.total_pages} for row in books_res.fetchall()}
        
        processing_ids = [bid for bid, info in books_info.items() if info["status"] != "ready"]
        
        results = {}
        
        # 1. Fetch milestone stats for processing books ONLY
        if processing_ids:
            milestone_stats_stmt = (
                select(
                    Page.book_id,
                    func.count(case((Page.ocr_milestone == "succeeded", 1))).label("ocr"),
                    func.count(case((Page.ocr_milestone.in_(["failed", "error"]), 1))).label("ocr_failed"),
                    func.count(case((Page.ocr_milestone == "in_progress", 1))).label("ocr_active"),
                    func.count(case((Page.chunking_milestone == "succeeded", 1))).label("chunking"),
                    func.count(case((Page.chunking_milestone.in_(["failed", "error"]), 1))).label("chunking_failed"),
                    func.count(case((Page.chunking_milestone == "in_progress", 1))).label("chunking_active"),
                    func.count(case((Page.embedding_milestone == "succeeded", 1))).label("embedding"),
                    func.count(case((Page.embedding_milestone.in_(["failed", "error"]), 1))).label("embedding_failed"),
                    func.count(case((Page.embedding_milestone == "in_progress", 1))).label("embedding_active"),
                    func.count(case((Page.word_index_milestone == "done", 1))).label("word_index"),
                    func.count(case((Page.word_index_milestone.in_(["failed", "error"]), 1))).label("word_index_failed"),
                    func.count(case((Page.word_index_milestone == "in_progress", 1))).label("word_index_active"),
                    func.count(case((Page.spell_check_milestone == "done", 1))).label("spell_check"),
                    func.count(case((Page.spell_check_milestone.in_(["failed", "error"]), 1))).label("spell_check_failed"),
                    func.count(case((Page.spell_check_milestone == "in_progress", 1))).label("spell_check_active"),
                )
                .where(Page.book_id.in_(processing_ids))
                .group_by(Page.book_id)
            )
            m_result = await self.session.execute(milestone_stats_stmt)
            for row in m_result.fetchall():
                bid = str(row.book_id)
                results[bid] = {
                    "pipeline_stats": {
                        "ocr": row.ocr,
                        "ocr_failed": row.ocr_failed,
                        "ocr_active": row.ocr_active,
                        "chunking": row.chunking,
                        "chunking_failed": row.chunking_failed,
                        "chunking_active": row.chunking_active,
                        "embedding": row.embedding,
                        "embedding_failed": row.embedding_failed,
                        "embedding_active": row.embedding_active,
                        "word_index": row.word_index,
                        "word_index_failed": row.word_index_failed,
                        "word_index_active": row.word_index_active,
                        "spell_check": row.spell_check,
                        "spell_check_failed": row.spell_check_failed,
                        "spell_check_active": row.spell_check_active,
                    }
                }
        
        # 2. Determine which books have summaries in one query
        summary_stmt = select(BookSummary.book_id).where(BookSummary.book_id.in_(book_ids))
        summary_res = await self.session.execute(summary_stmt)
        books_with_summary = {row[0] for row in summary_res.fetchall()}

        # 3. Assemble final results
        final_results = {}
        for bid in book_ids:
            # Get stats (either from DB for processing or 100% for ready)
            if bid in results:
                # Stats from DB scan (processing)
                stats = results[bid]["pipeline_stats"]
            else:
                # Assume 100% for ready books OR default 0 for missing ones
                info = books_info.get(bid, {})
                status = info.get("status")
                tp = info.get("total_pages") or 0
                
                if status == "ready":
                    stats = {
                        "ocr": tp, "ocr_failed": 0, "ocr_active": 0,
                        "chunking": tp, "chunking_failed": 0, "chunking_active": 0,
                        "embedding": tp, "embedding_failed": 0, "embedding_active": 0,
                        "word_index": tp, "word_index_failed": 0, "word_index_active": 0,
                        "spell_check": tp, "spell_check_failed": 0, "spell_check_active": 0,
                    }
                else:
                    stats = {}
            
            final_results[bid] = {
                "pipeline_stats": stats,
                "has_summary": bid in books_with_summary
            }

        return final_results

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
