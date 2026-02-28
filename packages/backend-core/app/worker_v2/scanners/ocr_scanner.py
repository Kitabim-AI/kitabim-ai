"""
OCR Scanner — claims idle ocr pages (grouped by book) and dispatches OcrJobs.

Groups by book because OCR needs the PDF file — one download per job.
Runs every 1 minute.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page
from app.db.repositories.system_configs import SystemConfigsRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker_v2.ocr_scanner")


async def run_ocr_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        max_books = int(await config_repo.get_value("v2_scanner_book_limit", "10"))

        # Find distinct books that have idle OCR pages
        book_ids_stmt = (
            select(Page.book_id)
            .where(
                Page.v2_pipeline_step == "ocr",
                Page.v2_milestone == "idle",
            )
            .distinct()
            .limit(max_books)
        )
        result = await session.execute(book_ids_stmt)
        book_ids = [row[0] for row in result.fetchall()]

    dispatched = 0
    for book_id in book_ids:
        async with db_session.async_session_factory() as session:
            # Atomically claim all idle ocr pages for this book.
            # FOR UPDATE SKIP LOCKED prevents double-claiming if two scanner
            # instances run simultaneously.
            id_stmt = (
                select(Page.id)
                .where(
                    Page.book_id == book_id,
                    Page.v2_pipeline_step == "ocr",
                    Page.v2_milestone == "idle",
                )
                .with_for_update(skip_locked=True)
            )
            result = await session.execute(id_stmt)
            page_ids = [row[0] for row in result.fetchall()]

            if not page_ids:
                continue

            await session.execute(
                update(Page)
                .where(Page.id.in_(page_ids))
                .values(v2_milestone="in_progress", last_updated=func.now())
            )
            await session.commit()

        await redis.enqueue_job(
            "v2_ocr_job",
            book_id=book_id,
            page_ids=page_ids,
            _job_id=f"v2_ocr:{book_id}",
        )
        log_json(logger, logging.INFO, "V2 OCR job dispatched",
                 book_id=book_id, page_count=len(page_ids))
        dispatched += 1

    if dispatched:
        log_json(logger, logging.INFO, "V2 OCR scanner finished", jobs_dispatched=dispatched)
