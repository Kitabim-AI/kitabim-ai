"""
Reembedding Scanner — finds books with chunks missing embedding_v2 and dispatches
one reembedding_job per book.

Only processes books whose chunks already have a v1 embedding (embedding IS NOT NULL),
so it never races with the normal embedding pipeline.

Runs every 1 minute. Processes up to 10 books per run to keep Gemini API pressure
manageable. Stops naturally once all chunks have embedding_v2 populated.

Disable this scanner (remove from worker.py cron_jobs) after migration 037 is applied.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, exists

from app.db import session as db_session
from app.db.models import Book, Chunk
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.reembedding_scanner")

_BOOKS_PER_RUN = 10


async def run_reembedding_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        stmt = (
            select(Book.id)
            .where(
                exists(
                    select(Chunk.id).where(
                        Chunk.book_id == Book.id,
                        Chunk.embedding.isnot(None),
                        Chunk.embedding_v2.is_(None),
                    )
                )
            )
            .limit(_BOOKS_PER_RUN)
        )
        result = await session.execute(stmt)
        book_ids = [row[0] for row in result.fetchall()]

    if not book_ids:
        return

    for book_id in book_ids:
        await redis.enqueue_job(
            "reembedding_job",
            book_id=book_id,
            _job_id=f"reembedding:{book_id}",
        )

    log_json(logger, logging.INFO, "reembedding scanner enqueued jobs", count=len(book_ids))
