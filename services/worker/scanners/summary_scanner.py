"""
Summary Scanner — backfill and retry for book_summaries.

Catches three cases the pipeline_driver hook misses:
  1. Books that were already 'ready' before this feature was deployed
  2. Books whose summary_job failed (no row in book_summaries)
  3. Books whose summary was cleared for regeneration (summary IS NULL, migration 039)

Runs every 5 minutes. Batch size controlled by system_config 'summary_scanner_batch_size'
(default 5). Increase temporarily to speed up bulk regeneration, then reset to 5.
"""
from __future__ import annotations

import logging

from sqlalchemy import or_, select

from app.db import session as db_session
from app.db.models import Book, BookSummary
from app.db.repositories.system_configs import SystemConfigsRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.summary_scanner")


async def run_summary_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        batch_size = int(
            await SystemConfigsRepository(session).get_value("summary_scanner_batch_size", "5")
        )
        stmt = (
            select(Book.id)
            .outerjoin(BookSummary, Book.id == BookSummary.book_id)
            .where(Book.status == "ready")
            .where(
                or_(
                    BookSummary.book_id.is_(None),
                    BookSummary.summary.is_(None),
                )
            )
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        book_ids = [row[0] for row in result.fetchall()]

    if not book_ids:
        return

    for book_id in book_ids:
        await redis.enqueue_job(
            "summary_job",
            book_id=book_id,
            _job_id=f"summary:{book_id}"
        )

    log_json(logger, logging.INFO, "summary scanner enqueued jobs", count=len(book_ids))
