"""
Pipeline Driver — the state machine for the decoupled worker.

Responsibilities (runs every 1 minute):
  1. Initialize  — pages with status='pending' and ocr_milestone='idle' (if needed)
  2. Reset       — failed milestones with retries remaining → idle
  3. Book ready  — marks book.pipeline_step = 'ready' when all mandatory 
                   milestones (OCR, Chunking, Embedding) are terminal.
                   Terminal = succeeded OR failed with exhausted retries.
                   If any pages failed (exhausted retries) → book.status='error'
                   Only marks book.status='ready' when ALL pages are ocr/chunking/embedding/succeeded.
"""
from __future__ import annotations

import logging

from sqlalchemy import update, select, func, case, or_, and_

from app.db import session as db_session
from app.db.models import Book, Page
from app.db.repositories.system_configs import SystemConfigsRepository
from app.utils.observability import log_json

# Books already marked ready or failed — do not reprocess them.
_V1_READY_STATUSES = ("ready", "error")

logger = logging.getLogger("app.worker.pipeline_driver")


async def run_pipeline_driver(ctx) -> None:
    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        max_retries = int(await config_repo.get_value("ocr_max_retry_count", "3"))

        # ── 1. Initialize ──────────────────────────────────────────────────────
        # Ensure ocr_milestone is 'idle' for pages that need processing.
        # This is the entry point for the pipeline.
        already_done_subq = (
            select(Book.id).where(
                Book.status.in_(_V1_READY_STATUSES),
                or_(
                    Book.pipeline_step.is_(None),
                    Book.pipeline_step == "ready",
                    Book.pipeline_step == "failed",
                ),
            )
        )
        
        # We also keep pipeline_step = 'ocr' for legacy/internal tracking if useful,
        # but the logic now drives via ocr_milestone.
        init_result = await session.execute(
            update(Page)
            .where(
                Page.ocr_milestone == "idle",
                Page.milestone != "succeeded",
                Page.book_id.not_in(already_done_subq),
            )
            .values(
                retry_count=0,
                pipeline_step=case((Page.pipeline_step.is_(None), "ocr"), else_=Page.pipeline_step)
            )
        )
        initialized = init_result.rowcount

        # ── 2. Reset failed milestones that still have retries remaining ───────
        # If any milestone failed but we have retries left, reset ALL milestones 
        # to ensure a clean retry of the whole page (or just the failing ones).
        # Typically OCR is the most critical to reset.
        reset_result = await session.execute(
            update(Page)
            .where(
                or_(
                    Page.ocr_milestone.in_(["failed", "error"]),
                    Page.chunking_milestone.in_(["failed", "error"]),
                    Page.embedding_milestone.in_(["failed", "error"]),
                    Page.word_index_milestone.in_(["failed", "error"]),
                    Page.spell_check_milestone.in_(["failed", "error"]),
                ),
                Page.retry_count < max_retries,
            )
            .values(
                ocr_milestone=case(
                    (Page.ocr_milestone.in_(["failed", "error"]), "idle"), else_=Page.ocr_milestone
                ),
                chunking_milestone=case(
                    (Page.chunking_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.chunking_milestone,
                ),
                embedding_milestone=case(
                    (Page.embedding_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.embedding_milestone,
                ),
                word_index_milestone=case(
                    (Page.word_index_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.word_index_milestone,
                ),
                spell_check_milestone=case(
                    (Page.spell_check_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.spell_check_milestone,
                ),
            )
        )
        reset = reset_result.rowcount

        # ── 3. (REMOVED) Sequential Promotion ──────────────────────────────────
        # Scanners now look for their own work based on dependencies:
        # - OCR: ocr_milestone == 'idle'
        # - Chunking: ocr_milestone == 'succeeded' AND chunking_milestone == 'idle'
        # - Embedding: chunking_milestone == 'succeeded' AND embedding_milestone == 'idle'
        ocr_promoted = 0
        chunk_promoted = 0

        # ── 4. Detect books where all pages are terminal ───────────────────────
        # Terminal page: embedding_milestone/succeeded  OR any mandatory step failed with exhausted retries
        terminal_case = case(
            (
                or_(
                    Page.embedding_milestone == "succeeded",
                    and_(
                        or_(
                            Page.ocr_milestone.in_(["failed", "error"]),
                            Page.chunking_milestone.in_(["failed", "error"]),
                            Page.embedding_milestone.in_(["failed", "error"])
                        ),
                        Page.retry_count >= max_retries,
                    ),
                ),
                Page.id,
            ),
            else_=None,
        )

        # Count pages that completed successfully (embedding/succeeded)
        success_case = case(
            (
                Page.embedding_milestone == "succeeded",
                Page.id,
            ),
            else_=None,
        )

        # Count pages that failed with exhausted retries
        failed_case = case(
            (
                and_(
                    or_(
                        Page.ocr_milestone.in_(["failed", "error"]),
                        Page.chunking_milestone.in_(["failed", "error"]),
                        Page.embedding_milestone.in_(["failed", "error"])
                    ),
                    Page.retry_count >= max_retries,
                ),
                Page.id,
            ),
            else_=None,
        )

        terminal_books_stmt = (
            select(
                Page.book_id,
                func.count(Page.id).label("total"),
                func.count(terminal_case).label("terminal"),
                func.count(success_case).label("succeeded"),
                func.count(failed_case).label("failed_exhausted"),
            )
            .join(Book, Page.book_id == Book.id)
            .where(
                or_(
                    Book.pipeline_step != "ready",
                    Book.pipeline_step.is_(None),
                )
            )
            .group_by(Page.book_id)
            .having(
                func.count(Page.id) == func.count(terminal_case),
                func.count(Page.id) > 0,
            )
        )
        result = await session.execute(terminal_books_stmt)
        rows = result.fetchall()

        # Split into fully-succeeded vs. any-failed groups
        fully_ready_ids = [row.book_id for row in rows if row.failed_exhausted == 0]
        has_failures_ids = [row.book_id for row in rows if row.failed_exhausted > 0]

        # Identify books about to transition to ready (not already ready).
        # Captured before the UPDATE so we enqueue summary jobs only for
        # truly newly-ready books, avoiding duplicates on re-runs.
        newly_ready_ids: list = []
        if fully_ready_ids:
            nr_result = await session.execute(
                select(Book.id).where(
                    Book.id.in_(fully_ready_ids),
                    or_(
                        Book.pipeline_step != "ready",
                        Book.pipeline_step.is_(None),
                    ),
                )
            )
            newly_ready_ids = [row[0] for row in nr_result.fetchall()]

        books_marked_ready = 0
        if fully_ready_ids:
            books_marked_ready = (await session.execute(
                update(Book)
                .where(
                    Book.id.in_(fully_ready_ids),
                    or_(
                        Book.pipeline_step != "ready",
                        Book.pipeline_step.is_(None),
                    ),
                )
                .values(pipeline_step="ready", status="ready")
            )).rowcount

        books_marked_error = 0
        if has_failures_ids:
            books_marked_error = (await session.execute(
                update(Book)
                .where(
                    Book.id.in_(has_failures_ids),
                    Book.pipeline_step != "failed",
                )
                .values(pipeline_step="failed", status="error")
            )).rowcount

        await session.commit()

    # Enqueue summary jobs for books that just became ready (outside the session).
    # summary_job generates and stores a semantic summary for hierarchical RAG.
    redis = ctx["redis"]
    for book_id in newly_ready_ids:
        await redis.enqueue_job("summary_job", book_id=book_id)

    log_json(
        logger, logging.INFO, "pipeline driver ran",
        initialized=initialized,
        failed_reset=reset,
        ocr_promoted=ocr_promoted,
        chunk_promoted=chunk_promoted,
        books_marked_ready=books_marked_ready,
        books_marked_error=books_marked_error,
        summary_jobs_enqueued=len(newly_ready_ids),
    )
