"""
Embedding Scanner — claims idle embedding pages and dispatches one EmbeddingJob.

Pages from any book can be grouped together since embedding only needs
chunk text already stored in the database.
Runs every 1 minute.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, Book
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.embedding_scanner")


async def run_embedding_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        page_limit = int(await config_repo.get_value("scanner_page_limit", "100"))
        batch_enabled = (
            await config_repo.get_value("gemini_batch_embedding_enabled", "false")
        ).lower() == "true"

        # Atomically claim idle embedding pages across all books.
        # Note: we do NOT filter by book status. auto_correct_service resets
        # embedding_milestone='idle' on corrected pages (even for ready books) so
        # the corrected text gets re-indexed. Excluding ready books would leave
        # those pages permanently stuck at idle.
        id_stmt = (
            select(Page.id)
            .join(Book, Page.book_id == Book.id)
            .where(
                Page.chunking_milestone == "succeeded",
                Page.embedding_milestone == "idle",
                ~Book.status.in_(["error"]),
            )
            .with_for_update(skip_locked=True)
            .limit(page_limit)
        )
        result = await session.execute(id_stmt.add_columns(Page.book_id))
        rows = result.fetchall()
        page_ids = [row[0] for row in rows]
        book_ids = list(set(row[1] for row in rows))

        if not page_ids:
            return

        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(
                embedding_milestone="in_progress",
                worker_id=ctx.get("worker_id", "unknown"),
                claimed_at=func.now(),
                last_updated=func.now(),
            )
        )
        # Update book-level embedding milestones
        for book_id in book_ids:
            await BookMilestoneService.update_book_milestone_for_step(
                session, book_id, "embedding"
            )
        await session.commit()

    if batch_enabled:
        from app.services.batch_embedding_service import (
            submit_batch_embedding_job,
        )

        async with db_session.async_session_factory() as submit_session:
            await submit_batch_embedding_job(submit_session, page_ids)

        log_json(
            logger,
            logging.INFO,
            "batch embedding job submitted",
            page_count=len(page_ids),
        )
    else:
        await redis.enqueue_job("embedding_job", page_ids=page_ids)
        log_json(
            logger,
            logging.INFO,
            "embedding job dispatched",
            page_count=len(page_ids),
        )
