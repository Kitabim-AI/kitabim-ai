"""
Embedding Scanner — claims books ready for embedding
(`chunking_milestone == 'complete'` and `embedding_milestone == 'idle'`).

Hybrid routing:
- 0 unembedded chunks -> marks `Book.embedding_milestone = 'complete'` immediately.
- <= 16 unembedded chunks or `embed_batch_enabled == 'false'` -> dispatches `embedding_job(book_id=...)`.
- > 16 unembedded chunks and `embed_batch_enabled == 'true'` -> submits book-scoped Gemini Batch API job.

Runs every 1 minute.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_COMPLETE,
)
from app.db import session as db_session
from app.db.models import Book, Chunk, Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.batch_embedding_service import submit_batch_embedding_job
from app.services.cache_service import cache_service
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.embedding_scanner")

ONLINE_EMBED_FAST_PATH_MAX_CHUNKS = 16


async def run_embedding_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        batch_enabled = (
            await config_repo.get_value("embed_batch_enabled", "false")
        ).lower() == "true"

        stmt = (
            select(Book.id)
            .where(
                Book.chunking_milestone == BOOK_MILESTONE_COMPLETE,
                Book.embedding_milestone == BOOK_MILESTONE_IDLE,
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
                embedding_milestone=BOOK_MILESTONE_IN_PROGRESS,
                embedding_claimed_at=func.now(),
                last_updated=func.now(),
            )
        )
        await session.commit()

    for book_id in book_ids:
        try:
            async with db_session.async_session_factory() as session:
                count_res = await session.execute(
                    select(func.count(Chunk.id)).where(
                        Chunk.book_id == book_id,
                        Chunk.embedding.is_(None),
                    )
                )
                unembedded_count = int(count_res.scalar() or 0)

                if unembedded_count == 0:
                    await session.execute(
                        update(Page)
                        .where(
                            Page.book_id == book_id,
                            Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
                        )
                        .values(
                            embedding_milestone="succeeded",
                            is_indexed=True,
                            last_updated=func.now(),
                        )
                    )
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            embedding_milestone=BOOK_MILESTONE_COMPLETE,
                            embedding_retry_count=0,
                            embedding_claimed_at=None,
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()
                    try:
                        await cache_service.delete_pattern(f"rag:search:{book_id}:*")
                    except Exception:
                        pass
                    continue

                if (
                    not batch_enabled
                    or unembedded_count <= ONLINE_EMBED_FAST_PATH_MAX_CHUNKS
                ):
                    job = await redis.enqueue_job(
                        "embedding_job",
                        book_id=book_id,
                    )
                    if job is None:
                        await session.execute(
                            update(Book)
                            .where(Book.id == book_id)
                            .values(
                                embedding_milestone=BOOK_MILESTONE_IDLE,
                                embedding_claimed_at=None,
                                last_updated=func.now(),
                            )
                        )
                        await session.commit()
                        continue
                    log_json(
                        logger,
                        logging.INFO,
                        "online embedding job dispatched",
                        book_id=book_id,
                        unembedded_chunks=unembedded_count,
                    )
                else:
                    await submit_batch_embedding_job(session, book_id)
                    log_json(
                        logger,
                        logging.INFO,
                        "batch embedding job submitted",
                        book_id=book_id,
                        unembedded_chunks=unembedded_count,
                    )
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "failed to dispatch embedding for claimed book",
                book_id=book_id,
                error=str(exc)[:500],
            )
            async with db_session.async_session_factory() as fail_session:
                await fail_session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        embedding_milestone=BOOK_MILESTONE_FAILED,
                        embedding_retry_count=Book.embedding_retry_count + 1,
                        embedding_claimed_at=None,
                        last_updated=func.now(),
                    )
                )
                await fail_session.commit()
