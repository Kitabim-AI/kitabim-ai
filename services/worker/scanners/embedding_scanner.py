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
from app.db.models import Page
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.embedding_scanner")


async def run_embedding_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        page_limit = int(await config_repo.get_value("scanner_page_limit", "100"))

        # Atomically claim idle embedding pages across all books.
        id_stmt = (
            select(Page.id)
            .where(
                Page.chunking_milestone == "succeeded",
                Page.embedding_milestone == "idle",
            )
            .with_for_update(skip_locked=True)
            .limit(page_limit)
        )
        result = await session.execute(
            id_stmt.add_columns(Page.book_id)
        )
        rows = result.fetchall()
        page_ids = [row[0] for row in rows]
        book_ids = list(set(row[1] for row in rows))
        

        if not page_ids:
            return

        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(embedding_milestone="in_progress", last_updated=func.now())
        )
        await session.commit()
        
        # Update book-level embedding milestones
        for book_id in book_ids:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'embedding')

    await redis.enqueue_job("embedding_job", page_ids=page_ids)
    log_json(logger, logging.INFO, "embedding job dispatched", page_count=len(page_ids))
