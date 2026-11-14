"""
Structure Job — runs deterministic printed-page alignment and two-tier section extraction
for a single book, then triggers book-scoped section-stream chunking.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
import logging
import time

from sqlalchemy import func, select, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
)
from app.db import session as db_session
from app.db.models import Book
from app.services.book_structure_service import BookStructureService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.structure_job")


async def structure_job(ctx, book_id: str) -> None:
    start_time = time.perf_counter()
    log_json(logger, logging.INFO, "structure job started", book_id=book_id)
    redis = ctx.get("redis")

    try:
        async with db_session.async_session_factory() as session:
            book_res = await session.execute(
                select(Book.ocr_milestone).where(Book.id == book_id)
            )
            book_row = book_res.first() if hasattr(book_res, "first") else None
            ocr_ms = (
                book_row[0]
                if isinstance(book_row, (tuple, list)) and len(book_row) > 0
                else getattr(book_row, "ocr_milestone", None)
            )
            if isinstance(ocr_ms, str) and ocr_ms != BOOK_MILESTONE_COMPLETE:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        structure_milestone=BOOK_MILESTONE_IDLE,
                        structure_claimed_at=None,
                        last_updated=func.now(),
                    )
                )
                await session.commit()
                log_json(
                    logger,
                    logging.INFO,
                    "structure job deferred until OCR is complete",
                    book_id=book_id,
                    ocr_milestone=ocr_ms,
                )
                return

        stats = {}
        completed_cleanly = False
        should_enqueue_chunking = False
        for _attempt in range(3):
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        pipeline_step="structure",
                        structure_milestone=BOOK_MILESTONE_IN_PROGRESS,
                        structure_claimed_at=func.now(),
                        last_updated=func.now(),
                    )
                )
                await session.commit()

            async with db_session.async_session_factory() as session:
                stats = await BookStructureService.analyze_and_persist_book_structure(
                    session, book_id
                )
                cur_res = await session.execute(
                    select(
                        Book.structure_milestone,
                        Book.chunking_milestone,
                        Book.chunking_claimed_at,
                    )
                    .where(Book.id == book_id)
                    .with_for_update()
                )
                cur_row = cur_res.first() if hasattr(cur_res, "first") else None
                cur_struct_ms = (
                    cur_row[0]
                    if isinstance(cur_row, (tuple, list)) and len(cur_row) > 0
                    else getattr(cur_row, "structure_milestone", None)
                )
                if (
                    isinstance(cur_struct_ms, str)
                    and cur_struct_ms == BOOK_MILESTONE_IDLE
                ):
                    await session.commit()
                    log_json(
                        logger,
                        logging.INFO,
                        "book dirtied during structure job; re-running structure analysis",
                        book_id=book_id,
                    )
                    continue

                cur_chunk_ms = (
                    cur_row[1]
                    if isinstance(cur_row, (tuple, list)) and len(cur_row) > 1
                    else getattr(cur_row, "chunking_milestone", None)
                )
                cur_chunk_claimed = (
                    cur_row[2]
                    if isinstance(cur_row, (tuple, list)) and len(cur_row) > 2
                    else getattr(cur_row, "chunking_claimed_at", None)
                )
                chunking_already_running = (
                    cur_chunk_ms == BOOK_MILESTONE_IN_PROGRESS
                    or isinstance(cur_chunk_claimed, datetime)
                )

                if chunking_already_running:
                    next_chunking_milestone = BOOK_MILESTONE_IDLE
                    next_chunking_claimed_at = cur_chunk_claimed
                    should_enqueue_chunking = False
                elif redis is not None:
                    next_chunking_milestone = BOOK_MILESTONE_IN_PROGRESS
                    next_chunking_claimed_at = func.now()
                    should_enqueue_chunking = True
                else:
                    next_chunking_milestone = BOOK_MILESTONE_IDLE
                    next_chunking_claimed_at = None
                    should_enqueue_chunking = False

                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        structure_milestone=BOOK_MILESTONE_COMPLETE,
                        structure_retry_count=0,
                        structure_claimed_at=None,
                        chunking_milestone=next_chunking_milestone,
                        chunking_retry_count=0,
                        chunking_claimed_at=next_chunking_claimed_at,
                        pipeline_step="chunking",
                        last_updated=func.now(),
                    )
                )
                await session.commit()
                completed_cleanly = True
                break

        if not completed_cleanly:
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        structure_milestone=BOOK_MILESTONE_IDLE,
                        structure_claimed_at=None,
                        last_updated=func.now(),
                    )
                )
                await session.commit()
            return

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        log_json(
            logger,
            logging.INFO,
            "structure job completed",
            book_id=book_id,
            duration_ms=duration_ms,
            **stats,
        )

        if redis is not None and should_enqueue_chunking:
            job = await redis.enqueue_job("chunking_job", book_id=book_id)
            if job is None:
                async with db_session.async_session_factory() as session:
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            chunking_milestone=BOOK_MILESTONE_IDLE,
                            chunking_claimed_at=None,
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()

    except (Exception, asyncio.CancelledError) as exc:
        error_msg = (str(exc) or exc.__class__.__name__)[:500]
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(
                    structure_milestone=BOOK_MILESTONE_FAILED,
                    structure_retry_count=Book.structure_retry_count + 1,
                    structure_claimed_at=None,
                    last_updated=func.now(),
                )
            )
            await session.commit()

        log_json(
            logger,
            logging.ERROR,
            "structure job failed",
            book_id=book_id,
            error=error_msg,
        )
        if isinstance(exc, asyncio.CancelledError):
            raise
