"""
Summary Scanner — backfill and retry for book_summaries.

Catches two cases the pipeline_driver hook misses:
  1. Books that were already 'ready' before this feature was deployed
  2. Books whose summary_job failed (no row in book_summaries)

Runs every 5 minutes. Processes up to 5 books per run to avoid thundering-herd
on fresh deploys with many existing ready books.
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import session as db_session
from app.db.models import Book, BookSummary
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.summary_scanner")


async def run_summary_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        # Find ready books that have no summary yet
        stmt = (
            select(Book.id)
            .outerjoin(BookSummary, Book.id == BookSummary.book_id)
            .where(Book.status == "ready")
            .where(BookSummary.book_id.is_(None))
            .limit(5)
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
