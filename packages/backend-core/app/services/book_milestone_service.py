"""Service for maintaining book-level milestone status based on page milestones."""
from sqlalchemy import select, func, case
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Book, Page
from app.core.config import settings


class BookMilestoneService:
    """Manages book-level milestone computation and updates."""

    @staticmethod
    def compute_milestone_status(done: int, failed: int, active: int, total: int) -> str:
        """
        Compute milestone status from page counts.

        Args:
            done: Count of successfully completed pages
            failed: Count of failed pages
            active: Count of in-progress pages
            total: Total number of pages

        Returns:
            One of: 'idle', 'in_progress', 'complete', 'partial_failure', 'failed'
        """
        if total == 0:
            return 'idle'

        # All pages succeeded
        if done == total:
            return 'complete'

        # All pages finished (some failed, some succeeded)
        if done + failed == total:
            if failed > 0:
                return 'partial_failure'
            return 'complete'

        # All pages failed
        if failed == total:
            return 'failed'

        # Mixed state (some done, some pending/active)
        if done > 0 or active > 0 or failed > 0:
            return 'in_progress'

        # Default: idle
        return 'idle'

    @staticmethod
    async def update_book_milestones(db: AsyncSession, book_id: str) -> None:
        """
        Update all milestone fields for a book based on its pages.

        Args:
            db: Database session
            book_id: ID of the book to update
        """
        # Query page milestone counts
        stmt = (
            select(
                func.count(Page.id).label("total"),
                # OCR
                func.count(case((Page.ocr_milestone == "succeeded", 1))).label("ocr_done"),
                func.count(case((Page.ocr_milestone.in_(["failed", "error"]), 1))).label("ocr_failed"),
                func.count(case((Page.ocr_milestone == "in_progress", 1))).label("ocr_active"),
                # Chunking
                func.count(case((Page.chunking_milestone == "succeeded", 1))).label("chunking_done"),
                func.count(case((Page.chunking_milestone.in_(["failed", "error"]), 1))).label("chunking_failed"),
                func.count(case((Page.chunking_milestone == "in_progress", 1))).label("chunking_active"),
                # Embedding
                func.count(case((Page.embedding_milestone == "succeeded", 1))).label("embedding_done"),
                func.count(case((Page.embedding_milestone.in_(["failed", "error"]), 1))).label("embedding_failed"),
                func.count(case((Page.embedding_milestone == "in_progress", 1))).label("embedding_active"),
                # Word Index
                func.count(case((Page.word_index_milestone == "done", 1))).label("word_index_done"),
                func.count(case((Page.word_index_milestone.in_(["failed", "error"]), 1))).label("word_index_failed"),
                func.count(case((Page.word_index_milestone == "in_progress", 1))).label("word_index_active"),
                # Spell Check
                func.count(case((Page.spell_check_milestone == "done", 1))).label("spell_check_done"),
                func.count(case((Page.spell_check_milestone.in_(["failed", "error"]), 1))).label("spell_check_failed"),
                func.count(case((Page.spell_check_milestone == "in_progress", 1))).label("spell_check_active"),
            )
            .where(Page.book_id == book_id)
        )

        result = await db.execute(stmt)
        stats = result.one_or_none()

        if not stats:
            return

        total = stats.total

        # Compute milestone status for each step
        ocr_milestone = BookMilestoneService.compute_milestone_status(
            stats.ocr_done, stats.ocr_failed, stats.ocr_active, total
        )
        chunking_milestone = BookMilestoneService.compute_milestone_status(
            stats.chunking_done, stats.chunking_failed, stats.chunking_active, total
        )
        embedding_milestone = BookMilestoneService.compute_milestone_status(
            stats.embedding_done, stats.embedding_failed, stats.embedding_active, total
        )
        word_index_milestone = BookMilestoneService.compute_milestone_status(
            stats.word_index_done, stats.word_index_failed, stats.word_index_active, total
        )
        spell_check_milestone = BookMilestoneService.compute_milestone_status(
            stats.spell_check_done, stats.spell_check_failed, stats.spell_check_active, total
        )

        # Update book record
        book_stmt = select(Book).where(Book.id == book_id)
        book_result = await db.execute(book_stmt)
        book = book_result.scalar_one_or_none()

        if book:
            book.ocr_milestone = ocr_milestone
            book.chunking_milestone = chunking_milestone
            book.embedding_milestone = embedding_milestone
            if settings.enable_word_index:
                book.word_index_milestone = word_index_milestone
            book.spell_check_milestone = spell_check_milestone

            await db.commit()

    @staticmethod
    async def update_book_milestone_for_step(
        db: AsyncSession,
        book_id: str,
        step: str
    ) -> None:
        """
        Update a specific milestone for a book (more efficient than updating all).

        Args:
            db: Database session
            book_id: ID of the book to update
            step: One of 'ocr', 'chunking', 'embedding', 'word_index', 'spell_check'
        """
        # Map step to page milestone field and count expressions
        step_configs = {
            'ocr': {
                'done_field': Page.ocr_milestone == "succeeded",
                'failed_field': Page.ocr_milestone.in_(["failed", "error"]),
                'active_field': Page.ocr_milestone == "in_progress",
                'book_field': 'ocr_milestone'
            },
            'chunking': {
                'done_field': Page.chunking_milestone == "succeeded",
                'failed_field': Page.chunking_milestone.in_(["failed", "error"]),
                'active_field': Page.chunking_milestone == "in_progress",
                'book_field': 'chunking_milestone'
            },
            'embedding': {
                'done_field': Page.embedding_milestone == "succeeded",
                'failed_field': Page.embedding_milestone.in_(["failed", "error"]),
                'active_field': Page.embedding_milestone == "in_progress",
                'book_field': 'embedding_milestone'
            },
            'word_index': {
                'done_field': Page.word_index_milestone == "done",
                'failed_field': Page.word_index_milestone.in_(["failed", "error"]),
                'active_field': Page.word_index_milestone == "in_progress",
                'book_field': 'word_index_milestone'
            },
            'spell_check': {
                'done_field': Page.spell_check_milestone == "done",
                'failed_field': Page.spell_check_milestone.in_(["failed", "error"]),
                'active_field': Page.spell_check_milestone == "in_progress",
                'book_field': 'spell_check_milestone'
            },
        }

        if step not in step_configs:
            raise ValueError(f"Unknown step: {step}")

        config = step_configs[step]

        # Query page counts for this specific step
        stmt = (
            select(
                func.count(Page.id).label("total"),
                func.count(case((config['done_field'], 1))).label("done"),
                func.count(case((config['failed_field'], 1))).label("failed"),
                func.count(case((config['active_field'], 1))).label("active"),
            )
            .where(Page.book_id == book_id)
        )

        result = await db.execute(stmt)
        stats = result.one_or_none()

        if not stats:
            return

        # Compute milestone status
        milestone_status = BookMilestoneService.compute_milestone_status(
            stats.done, stats.failed, stats.active, stats.total
        )

        # Update book record
        book_stmt = select(Book).where(Book.id == book_id)
        book_result = await db.execute(book_stmt)
        book = book_result.scalar_one_or_none()

        if book:
            setattr(book, config['book_field'], milestone_status)
            await db.commit()
