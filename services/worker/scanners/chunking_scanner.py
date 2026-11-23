"""
Chunking Scanner — claims books ready for section-stream chunking
(`structure_milestone == 'complete'` and `chunking_milestone == 'idle'`)
and dispatches `chunking_job(book_id=...)`.

Runs every 1 minute.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
)
from app.db import session as db_session
from app.db.models import Book
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.chunking_scanner")


async def run_chunking_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        stmt = (
            select(Book.id)
            .where(
                Book.ocr_milestone == BOOK_MILESTONE_COMPLETE,
                Book.structure_milestone == BOOK_MILESTONE_COMPLETE,
                Book.chunking_milestone == BOOK_MILESTONE_IDLE,
                Book.chunking_claimed_at.is_(None),
                ~Book.status.in_(["error"]),
            )
            .with_for_update(skip_locked=True)
            .limit(20)
        )
        result = await session.execute(stmt)
        book_ids = [row[0] for row in result.fetchall()]

        if not book_ids:
            return

        await session.execute(
            update(Book)
            .where(Book.id.in_(book_ids))
            .values(
                chunking_milestone=BOOK_MILESTONE_IN_PROGRESS,
                chunking_claimed_at=func.now(),
                last_updated=func.now(),
            )
        )
        await session.commit()

    dropped_ids: list[str] = []
    dispatched = 0
    for book_id in book_ids:
        job = await redis.enqueue_job("chunking_job", book_id=book_id)
        if job is None:
            dropped_ids.append(book_id)
        else:
            dispatched += 1

    if dropped_ids:
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id.in_(dropped_ids))
                .values(
                    chunking_milestone=BOOK_MILESTONE_IDLE,
                    chunking_claimed_at=None,
                    last_updated=func.now(),
                )
            )
            await session.commit()

    log_json(
        logger,
        logging.INFO,
        "chunking jobs dispatched",
        book_count=dispatched,
    )
