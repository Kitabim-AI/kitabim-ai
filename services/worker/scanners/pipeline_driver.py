"""
Pipeline Driver — the state machine for the decoupled worker.

Responsibilities (runs every 1 minute):
  1. Initialize  — pages with status='pending' and ocr_milestone='idle' (if needed)
  2. Reset       — failed page milestones (OCR / spell_check) and failed book-scoped
                   milestones (`structure_milestone`, `chunking_milestone`, `embedding_milestone`)
                   with retries remaining → idle
  3. Book ready  — marks `book.pipeline_step = 'ready'` and `book.status = 'ready'` when
                   all pages have `Page.ocr_milestone == 'complete'` AND `Book.structure_milestone == 'complete'`
                   AND `Book.chunking_milestone == 'complete'` AND `Book.embedding_milestone == 'complete'`.
                   If any mandatory page or book milestone failed with exhausted retries → `book.status = 'error'`.
  4. Summary refresh — enqueues `summary_job` for newly-ready books OR ready books whose
                   `BookSummary.generated_at < Book.ocr_backfill_at`.
"""

from __future__ import annotations

import logging

from sqlalchemy import and_, case, func, or_, select, union_all, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    PAGE_MILESTONE_COMPLETE,
)
from app.db import session as db_session
from app.db.models import Book, BookSummary, Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

_V1_READY_STATUSES = ("ready", "error")

logger = logging.getLogger("app.worker.pipeline_driver")


async def run_pipeline_driver(ctx) -> None:
    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        max_retries = int(await config_repo.get_value("ocr_max_retry_count", "3"))

        # ── 1. Initialize ──────────────────────────────────────────────────────
        init_ids_stmt = (
            select(Page.id)
            .join(Book, Page.book_id == Book.id)
            .where(Page.ocr_milestone == "idle", ~Book.status.in_(_V1_READY_STATUSES))
            .limit(5000)
        )
        init_ids_result = await session.execute(init_ids_stmt)
        init_page_ids = [row[0] for row in init_ids_result.fetchall()]

        initialized = 0
        if init_page_ids:
            init_update_stmt = (
                update(Page)
                .where(Page.id.in_(init_page_ids))
                .values(
                    retry_count=case(
                        (Page.pipeline_step.is_(None), 0), else_=Page.retry_count
                    ),
                    pipeline_step=case(
                        (Page.pipeline_step.is_(None), "ocr"), else_=Page.pipeline_step
                    ),
                )
            )
            init_exec = await session.execute(init_update_stmt)
            initialized = init_exec.rowcount

        # ── 2a. Reset failed page milestones (OCR & spell_check) with retries remaining
        reset_queries = [
            select(Page.id)
            .join(Book, Page.book_id == Book.id)
            .where(
                Page.ocr_milestone.in_(["failed", "error"]),
                Page.retry_count < max_retries,
                ~Book.status.in_(_V1_READY_STATUSES),
            )
            .limit(5000),
            select(Page.id)
            .join(Book, Page.book_id == Book.id)
            .where(
                Page.spell_check_milestone.in_(["failed", "error"]),
                Page.retry_count < max_retries,
                ~Book.status.in_(_V1_READY_STATUSES),
            )
            .limit(5000),
        ]

        reset_ids_stmt = union_all(*reset_queries).limit(5000)
        reset_ids_result = await session.execute(reset_ids_stmt)
        reset_page_ids = [row[0] for row in reset_ids_result.fetchall()]

        reset = 0
        if reset_page_ids:
            update_values = {
                "ocr_milestone": case(
                    (Page.ocr_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.ocr_milestone,
                ),
                "spell_check_milestone": case(
                    (Page.spell_check_milestone.in_(["failed", "error"]), "idle"),
                    else_=Page.spell_check_milestone,
                ),
            }
            reset_update_stmt = (
                update(Page).where(Page.id.in_(reset_page_ids)).values(**update_values)
            )
            reset_exec = await session.execute(reset_update_stmt)
            reset = reset_exec.rowcount

        # ── 2b. Reset failed book-scoped milestones (structure, chunking, embedding) with retries remaining
        _book_fail_states = ["failed", "error", "partial_failure"]
        book_reset_stmt = (
            update(Book)
            .where(
                ~Book.status.in_(["error"]),
                or_(
                    and_(
                        Book.structure_milestone.in_(_book_fail_states),
                        Book.structure_retry_count < max_retries,
                    ),
                    and_(
                        Book.chunking_milestone.in_(_book_fail_states),
                        Book.chunking_retry_count < max_retries,
                    ),
                    and_(
                        Book.embedding_milestone.in_(_book_fail_states),
                        Book.embedding_retry_count < max_retries,
                    ),
                ),
            )
            .values(
                structure_milestone=case(
                    (
                        and_(
                            Book.structure_milestone.in_(_book_fail_states),
                            Book.structure_retry_count < max_retries,
                        ),
                        BOOK_MILESTONE_IDLE,
                    ),
                    else_=Book.structure_milestone,
                ),
                chunking_milestone=case(
                    (
                        and_(
                            Book.chunking_milestone.in_(_book_fail_states),
                            Book.chunking_retry_count < max_retries,
                        ),
                        BOOK_MILESTONE_IDLE,
                    ),
                    else_=Book.chunking_milestone,
                ),
                embedding_milestone=case(
                    (
                        and_(
                            Book.embedding_milestone.in_(_book_fail_states),
                            Book.embedding_retry_count < max_retries,
                        ),
                        BOOK_MILESTONE_IDLE,
                    ),
                    else_=Book.embedding_milestone,
                ),
            )
        )
        book_reset_exec = await session.execute(book_reset_stmt)
        reset += book_reset_exec.rowcount or 0

        ocr_promoted = 0
        chunk_promoted = 0

        # ── 3. Detect books where OCR is terminal and book-scoped milestones are terminal
        ocr_terminal_case = case(
            (
                or_(
                    Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
                    and_(
                        Page.ocr_milestone.in_(["failed", "error"]),
                        Page.retry_count >= max_retries,
                    ),
                ),
                Page.id,
            ),
            else_=None,
        )
        ocr_failed_case = case(
            (
                and_(
                    Page.ocr_milestone.in_(["failed", "error"]),
                    Page.retry_count >= max_retries,
                ),
                Page.id,
            ),
            else_=None,
        )

        terminal_books_stmt = (
            select(
                Book.id.label("book_id"),
                Book.structure_milestone,
                Book.structure_retry_count,
                Book.chunking_milestone,
                Book.chunking_retry_count,
                Book.embedding_milestone,
                Book.embedding_retry_count,
                func.count(Page.id).label("total"),
                func.count(ocr_terminal_case).label("ocr_terminal"),
                func.count(ocr_failed_case).label("ocr_failed_exhausted"),
            )
            .join(Page, Page.book_id == Book.id)
            .where(~Book.status.in_(_V1_READY_STATUSES))
            .group_by(
                Book.id,
                Book.structure_milestone,
                Book.structure_retry_count,
                Book.chunking_milestone,
                Book.chunking_retry_count,
                Book.embedding_milestone,
                Book.embedding_retry_count,
            )
            .having(
                func.count(Page.id) == func.count(ocr_terminal_case),
                func.count(Page.id) > 0,
            )
        )
        result = await session.execute(terminal_books_stmt)
        rows = result.fetchall()

        fully_ready_ids: list[str] = []
        has_failures_ids: list[str] = []

        for row in rows:
            book_failed_exhausted = (
                (
                    row.structure_milestone
                    in (BOOK_MILESTONE_FAILED, "error", "partial_failure")
                    and (row.structure_retry_count or 0) >= max_retries
                )
                or (
                    row.chunking_milestone
                    in (BOOK_MILESTONE_FAILED, "error", "partial_failure")
                    and (row.chunking_retry_count or 0) >= max_retries
                )
                or (
                    row.embedding_milestone
                    in (BOOK_MILESTONE_FAILED, "error", "partial_failure")
                    and (row.embedding_retry_count or 0) >= max_retries
                )
            )
            if row.ocr_failed_exhausted > 0 or book_failed_exhausted:
                has_failures_ids.append(row.book_id)
            elif (
                row.structure_milestone == BOOK_MILESTONE_COMPLETE
                and row.chunking_milestone == BOOK_MILESTONE_COMPLETE
                and row.embedding_milestone == BOOK_MILESTONE_COMPLETE
            ):
                fully_ready_ids.append(row.book_id)

        newly_ready_ids: list[str] = []
        if fully_ready_ids:
            nr_result = await session.execute(
                select(Book.id)
                .outerjoin(BookSummary, Book.id == BookSummary.book_id)
                .where(
                    Book.id.in_(fully_ready_ids),
                    or_(
                        Book.pipeline_step != "ready",
                        Book.pipeline_step.is_(None),
                        Book.status != "ready",
                    ),
                    or_(
                        BookSummary.book_id.is_(None),
                        BookSummary.summary.is_(None),
                        and_(
                            Book.ocr_backfill_at.isnot(None),
                            BookSummary.generated_at < Book.ocr_backfill_at,
                        ),
                    ),
                )
            )
            newly_ready_ids = [row[0] for row in nr_result.fetchall()]

        books_marked_ready = 0
        if fully_ready_ids:
            books_marked_ready = (
                await session.execute(
                    update(Book)
                    .where(
                        Book.id.in_(fully_ready_ids),
                        or_(
                            Book.pipeline_step != "ready",
                            Book.pipeline_step.is_(None),
                            Book.status != "ready",
                        ),
                    )
                    .values(
                        pipeline_step="ready", status="ready", graph_milestone="idle"
                    )
                )
            ).rowcount

            for book_id in fully_ready_ids:
                await BookMilestoneService.update_book_milestones(session, book_id)

        books_marked_error = 0
        if has_failures_ids:
            books_marked_error = (
                await session.execute(
                    update(Book)
                    .where(
                        Book.id.in_(has_failures_ids),
                        or_(
                            Book.pipeline_step != "failed",
                            Book.status != "error",
                        ),
                    )
                    .values(pipeline_step="failed", status="error")
                )
            ).rowcount

            for book_id in has_failures_ids:
                await BookMilestoneService.update_book_milestones(session, book_id)

        await session.commit()

    redis = ctx["redis"]
    for book_id in newly_ready_ids:
        await redis.enqueue_job(
            "summary_job", book_id=book_id, _job_id=f"summary:{book_id}"
        )

    log_json(
        logger,
        logging.INFO,
        "pipeline driver ran",
        initialized=initialized,
        failed_reset=reset,
        ocr_promoted=ocr_promoted,
        chunk_promoted=chunk_promoted,
        books_marked_ready=books_marked_ready,
        books_marked_error=books_marked_error,
        summary_jobs_enqueued=len(newly_ready_ids),
    )
