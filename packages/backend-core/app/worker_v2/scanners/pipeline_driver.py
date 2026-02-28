"""
Pipeline Driver — the state machine for worker v2.

Responsibilities (runs every 1 minute):
  1. Initialize  — pages with NULL v2_pipeline_step → ocr / idle
  2. Reset       — failed pages with retries remaining → idle (same step)
  3. Promote     — ocr/succeeded → chunking/idle
                   chunking/succeeded → embedding/idle
  4. Book ready  — marks book.v2_pipeline_step = 'ready' when all pages are terminal
                   Terminal = embedding/succeeded OR failed with exhausted retries
"""
from __future__ import annotations

import logging

from sqlalchemy import update, select, func, case, or_, and_

from app.db import session as db_session
from app.db.models import Book, Page

# Books v1 considers fully done — worker v2 must not reprocess them.
_V1_READY_STATUSES = ("ready",)
from app.db.repositories.system_configs import SystemConfigsRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker_v2.pipeline_driver")


async def run_pipeline_driver(ctx) -> None:
    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        max_retries = int(await config_repo.get_value("v2_ocr_max_retry_count", "3"))

        # ── 1. Initialize ──────────────────────────────────────────────────────
        # Pages with no v2 state yet enter the pipeline at ocr/idle.
        # Skip pages belonging to books v1 already marked ready — those books
        # are fully processed and do not need reprocessing by v2.
        already_done_subq = (
            select(Book.id).where(Book.status.in_(_V1_READY_STATUSES))
        )
        init_result = await session.execute(
            update(Page)
            .where(
                Page.v2_pipeline_step.is_(None),
                Page.book_id.not_in(already_done_subq),
            )
            .values(v2_pipeline_step="ocr", v2_milestone="idle", v2_retry_count=0)
        )
        initialized = init_result.rowcount

        # ── 2. Reset failed pages that still have retries remaining ────────────
        # The scanner only claims idle pages, so failed pages must be reset here
        # before the scanner runs. Pages with exhausted retries are left as-is
        # (they are terminal and counted for book-ready detection).
        reset_result = await session.execute(
            update(Page)
            .where(
                Page.v2_milestone == "failed",
                Page.v2_retry_count < max_retries,
            )
            .values(v2_milestone="idle")
        )
        reset = reset_result.rowcount

        # ── 3. Promote succeeded pages to the next step ────────────────────────
        # Same guard as initialization: never promote pages from v1-ready books.
        # ocr/succeeded → chunking/idle
        ocr_promoted = (await session.execute(
            update(Page)
            .where(
                Page.v2_pipeline_step == "ocr",
                Page.v2_milestone == "succeeded",
                Page.book_id.not_in(already_done_subq),
            )
            .values(v2_pipeline_step="chunking", v2_milestone="idle")
        )).rowcount

        # chunking/succeeded → embedding/idle
        chunk_promoted = (await session.execute(
            update(Page)
            .where(
                Page.v2_pipeline_step == "chunking",
                Page.v2_milestone == "succeeded",
                Page.book_id.not_in(already_done_subq),
            )
            .values(v2_pipeline_step="embedding", v2_milestone="idle")
        )).rowcount

        # ── 4. Detect books where all pages are terminal ───────────────────────
        # Terminal page: embedding/succeeded  OR  failed with retry_count >= max
        terminal_case = case(
            (
                or_(
                    and_(
                        Page.v2_pipeline_step == "embedding",
                        Page.v2_milestone == "succeeded",
                    ),
                    and_(
                        Page.v2_milestone == "failed",
                        Page.v2_retry_count >= max_retries,
                    ),
                ),
                Page.id,
            ),
            else_=None,
        )

        ready_books_stmt = (
            select(Page.book_id)
            .where(Page.v2_pipeline_step.is_not(None))
            .group_by(Page.book_id)
            .having(
                # Every page is terminal
                func.count(Page.id) == func.count(terminal_case),
                # At least one page exists (exclude empty books)
                func.count(Page.id) > 0,
            )
        )
        result = await session.execute(ready_books_stmt)
        ready_book_ids = [row[0] for row in result.fetchall()]

        books_marked_ready = 0
        if ready_book_ids:
            books_marked_ready = (await session.execute(
                update(Book)
                .where(
                    Book.id.in_(ready_book_ids),
                    or_(
                        Book.v2_pipeline_step != "ready",
                        Book.v2_pipeline_step.is_(None),
                    ),
                )
                .values(v2_pipeline_step="ready")
            )).rowcount

        await session.commit()

    log_json(
        logger, logging.INFO, "V2 pipeline driver ran",
        initialized=initialized,
        failed_reset=reset,
        ocr_promoted=ocr_promoted,
        chunk_promoted=chunk_promoted,
        books_marked_ready=books_marked_ready,
    )
