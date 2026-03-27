"""Books repository with SQLAlchemy"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func, or_, and_, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.pipeline import (
    FAILED_PAGE_MILESTONES,
    PAGE_MILESTONE_ATTR_BY_STEP,
    PAGE_MILESTONE_DONE,
    PAGE_MILESTONE_IDLE,
    PAGE_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_SUCCEEDED,
    PIPELINE_STEP_SUMMARY,
    STEP_DONE_MILESTONE_BY_STEP,
)
from app.db.models import Book, Page, BookSummary
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
            # Check if the query ends with a volume number (e.g. "لېيىغان بۇلاق 7")
            import re
            volume_match = re.search(r'\s+(\d+)\s*$', search_query)
            if volume_match:
                title_part = search_query[:volume_match.start()].strip()
                volume_num = int(volume_match.group(1))
                if title_part:
                    search_filter = or_(
                        Book.title.ilike(f"%{title_part}%"),
                        Book.author.ilike(f"%{title_part}%"),
                    )
                    conditions.append(search_filter)
                    conditions.append(Book.volume == volume_num)
                else:
                    # Only a number was typed — fall back to normal search
                    conditions.append(or_(
                        Book.title.ilike(f"%{search_query}%"),
                        Book.author.ilike(f"%{search_query}%"),
                    ))
            else:
                # Full-text search across title and author
                conditions.append(or_(
                    Book.title.ilike(f"%{search_query}%"),
                    Book.author.ilike(f"%{search_query}%"),
                ))

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
            step: Optional pipeline step to query (ocr, chunking, embedding, spell_check, summary)
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
                    func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_DONE, 1))).label("done"),
                    func.count(case((Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("failed"),
                    func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("active")
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
            sc_res = await self.session.execute(sc_stmt)
            sc_row = sc_res.fetchone()
            
            sc_done = sc_row.done if sc_row else 0
            sc_failed = sc_row.failed if sc_row else 0
            sc_active = sc_row.active if sc_row else 0

            return {
                "book": book,
                "page_stats": {},
                "pipeline_stats": {
                    "ocr": tp, "ocr_failed": 0, "ocr_active": 0,
                    "chunking": tp, "chunking_failed": 0, "chunking_active": 0,
                    "embedding": tp, "embedding_failed": 0, "embedding_active": 0,
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
        if step and step != PIPELINE_STEP_SUMMARY:
            # Single-step query optimization
            milestone_field_map = {
                step_name: getattr(Page, field_name)
                for step_name, field_name in PAGE_MILESTONE_ATTR_BY_STEP.items()
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
            done_value = STEP_DONE_MILESTONE_BY_STEP[step]
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(case((milestone_field == done_value, 1))).label(f"{step}_done"),
                    func.count(case((milestone_field.in_(FAILED_PAGE_MILESTONES), 1))).label(f"{step}_failed"),
                    func.count(case((milestone_field == PAGE_MILESTONE_IN_PROGRESS, 1))).label(f"{step}_active"),
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )
        else:
            # Query all steps (original behavior)
            stats_stmt = (
                select(
                    func.count(Page.id).label("total"),
                    func.count(case((Page.ocr_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("ocr_done"),
                    func.count(case((Page.ocr_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("ocr_failed"),
                    func.count(case((Page.ocr_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("ocr_active"),
                    func.count(case((Page.chunking_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("chunking_done"),
                    func.count(case((Page.chunking_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("chunking_failed"),
                    func.count(case((Page.chunking_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("chunking_active"),
                    func.count(case((Page.embedding_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("embedding_done"),
                    func.count(case((Page.embedding_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("embedding_failed"),
                    func.count(case((Page.embedding_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("embedding_active"),
                    func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_DONE, 1))).label("spell_check_done"),
                    func.count(case((Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("spell_check_failed"),
                    func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("spell_check_active"),
                    func.count(case((Page.milestone == PAGE_MILESTONE_IDLE, 1))).label("pending_count"),
                    func.count(case((Page.milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("processing_count")
                )
                .where(Page.book_id == book_id)
                .group_by(Page.book_id)
            )

        stats_result = await self.session.execute(stats_stmt)
        row = stats_result.fetchone()

        # Determine if summary exists (only if requested or querying all)
        has_summary = False
        if not step or step == PIPELINE_STEP_SUMMARY:
            summary_stmt = select(func.count(BookSummary.book_id)).where(BookSummary.book_id == book_id)
            summary_res = await self.session.execute(summary_stmt)
            has_summary = (summary_res.scalar() or 0) > 0

        # Handle single-step response
        if step and step != PIPELINE_STEP_SUMMARY:
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
                "spell_check": row.spell_check_done or 0,
                "spell_check_failed": row.spell_check_failed or 0,
                "spell_check_active": row.spell_check_active or 0,
            },
            "has_summary": has_summary,
            "ocr_done_count": row.ocr_done or 0,
            "error_count": (row.ocr_failed or 0) + (row.chunking_failed or 0) + (row.embedding_failed or 0) + (row.spell_check_failed or 0),
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
        
        # 1. Fetch milestone stats for ALL requested books
        # Note: We must scan all books because 'ready' books may still have background 
        # spell-check or word-indexing tasks running (or reset to idle).
        milestone_stats_stmt = (
            select(
                Page.book_id,
                func.count(case((Page.ocr_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("ocr"),
                func.count(case((Page.ocr_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("ocr_failed"),
                func.count(case((Page.ocr_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("ocr_active"),
                func.count(case((Page.chunking_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("chunking"),
                func.count(case((Page.chunking_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("chunking_failed"),
                func.count(case((Page.chunking_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("chunking_active"),
                func.count(case((Page.embedding_milestone == PAGE_MILESTONE_SUCCEEDED, 1))).label("embedding"),
                func.count(case((Page.embedding_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("embedding_failed"),
                func.count(case((Page.embedding_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("embedding_active"),
                func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_DONE, 1))).label("spell_check"),
                func.count(case((Page.spell_check_milestone.in_(FAILED_PAGE_MILESTONES), 1))).label("spell_check_failed"),
                func.count(case((Page.spell_check_milestone == PAGE_MILESTONE_IN_PROGRESS, 1))).label("spell_check_active"),
            )
            .where(Page.book_id.in_(book_ids))
            .group_by(Page.book_id)
        )
        results = {}
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
            info = books_info.get(bid, {})
            status = info.get("status")
            tp = info.get("total_pages") or 0

            # Get stats (either from DB for processing or 100% for ready)
            if bid in results:
                # Stats from DB scan
                stats = results[bid]["pipeline_stats"]
            else:
                # Default fallback for missing books (should not happen if pages exist)
                # If a book is 'ready' but has no page records found (orphaned book record)
                # we still assume 0 to be safe
                stats = {
                    "ocr": tp if status == "ready" else 0,
                    "ocr_failed": 0, "ocr_active": 0,
                    "chunking": tp if status == "ready" else 0,
                    "chunking_failed": 0, "chunking_active": 0,
                    "embedding": tp if status == "ready" else 0,
                    "embedding_failed": 0, "embedding_active": 0,
                    "spell_check": 0, "spell_check_failed": 0, "spell_check_active": 0,
                }

            
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

    # ------------------------------------------------------------------
    # RAG catalog lookup helpers (used by modular RAG handlers)
    # ------------------------------------------------------------------

    async def find_author_by_title_in_question(
        self,
        question: str,
        categories: Optional[List[str]] = None,
    ) -> Optional[tuple[str, str]]:
        """Return (title, author) if a known book title is word-prefix matched in question.

        Uses the same Uyghur agglutinative suffix matching as the RAG pipeline.
        Returns None when no title is matched.
        """
        stmt = select(Book.title, Book.author).where(
            Book.status != "error", Book.author.isnot(None)
        )
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))

        result = await self.session.execute(stmt)
        rows = [(row[0], row[1]) for row in result.fetchall() if row[0] and row[1]]

        import re
        q = question.strip()

        # Exact match when the question contains a «quoted» title
        quoted = re.findall(r'«([^»]+)»', q)
        if quoted:
            for candidate in quoted:
                candidate_norm = _normalize_uyghur(candidate.strip())
                for title, author in rows:
                    if _normalize_uyghur(title.strip()) == candidate_norm:
                        return title, author
            return None  # quoted title present but not found — don't fuzzy-match

        for title, author in rows:
            if _entity_matches_question(title, q):
                return title, author
        return None

    async def find_books_by_author_in_question(
        self,
        question: str,
        categories: Optional[List[str]] = None,
    ) -> List[Book]:
        """Return all books by an author whose name is word-prefix matched in question.

        Returns an empty list when no author is matched.
        """
        stmt = (
            select(Book.author)
            .where(Book.author.isnot(None), Book.status != "error")
            .distinct()
        )
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))

        result = await self.session.execute(stmt)
        authors = [row[0] for row in result.fetchall() if row[0]]

        q = question.strip()
        matched_author = next(
            (a for a in authors if _entity_matches_question(a, q)), None
        )
        if not matched_author:
            return []

        stmt = (
            select(Book)
            .where(Book.status != "error", Book.author == matched_author)
            .order_by(Book.volume.asc().nulls_first(), Book.title.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_volume_info_by_title_in_question(
        self,
        question: str,
        categories: Optional[List[str]] = None,
    ) -> List[dict]:
        """Return [{title, volume, total_pages}] for a book title matched in question.

        Returns an empty list when no title is matched.
        """
        stmt = select(Book.title).where(Book.status != "error")
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))

        result = await self.session.execute(stmt)
        titles = [row[0] for row in result.fetchall() if row[0]]

        import re
        q = question.strip()

        # Exact match when the question contains a «quoted» title
        quoted = re.findall(r'«([^»]+)»', q)
        matched_title = None
        if quoted:
            for candidate in quoted:
                candidate_norm = _normalize_uyghur(candidate.strip())
                matched_title = next(
                    (t for t in titles if _normalize_uyghur(t.strip()) == candidate_norm), None
                )
                if matched_title:
                    break
        if not matched_title:
            matched_title = next(
                (t for t in titles if _entity_matches_question(t, q)), None
            )
        if not matched_title:
            return []

        stmt = (
            select(Book.title, Book.volume, Book.total_pages)
            .where(Book.status != "error", Book.title == matched_title)
            .order_by(Book.volume.asc().nulls_first())
        )
        result = await self.session.execute(stmt)
        return [
            {"title": row[0], "volume": row[1], "total_pages": row[2]}
            for row in result.fetchall()
        ]


# ---------------------------------------------------------------------------
# Module-level helpers for Uyghur entity matching (used by catalog methods)
# ---------------------------------------------------------------------------

def _normalize_uyghur(text: str) -> str:
    return (
        text
        .replace("\u06D0", "\u06CC")
        .replace("\u0649", "\u06CC")
        .replace("\u064A", "\u06CC")
    )


_PUNCT = "«»،؟!()[]{}\"""''"


def _entity_matches_question(entity: str, question: str) -> bool:
    """Word-prefix match handling Uyghur agglutinative suffixes.

    Single-word entities are allowed when at least 4 characters long.
    Leading/trailing punctuation (e.g. «») is stripped from question tokens
    so that quoted titles are matched correctly.
    """
    entity_words = _normalize_uyghur(entity.strip()).split()
    if not entity_words:
        return False
    if len(entity_words) == 1 and len(entity_words[0]) < 4:
        return False
    q_words = [
        _normalize_uyghur(w).strip(_PUNCT)
        for w in question.strip().split()
    ]
    return all(
        any(q_word.startswith(e_word) for q_word in q_words)
        for e_word in entity_words
    )


def get_books_repository(session: AsyncSession) -> BooksRepository:
    """Factory function for dependency injection"""
    return BooksRepository(session)
