"""
Chunking Scanner — claims idle chunking pages and dispatches one ChunkingJob.

Pages from any book can be grouped together since chunking only needs the
text already stored in the database.

When spell_check is enabled, a page must also have spell_check_milestone in
('succeeded', 'failed') before it's eligible — spell check can rewrite
page.text via auto-correct rules, and chunking on text that's about to be
corrected would build chunks from stale content with no re-chunk trigger.
Runs every 1 minute.
"""

from __future__ import annotations

import logging

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.chunking_scanner")


async def run_chunking_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        page_limit = int(await config_repo.get_value("scanner_page_limit", "100"))
        spell_check_enabled = (
            await config_repo.get_value("spell_check_enabled", "false")
        ) == "true"

        # Atomically claim idle chunking pages across all books.
        # Note: we do NOT filter by book status. auto_correct_service resets
        # chunking_milestone='idle' on corrected pages (even for ready books) so
        # the corrected text gets re-indexed. Excluding ready books would leave
        # those pages permanently stuck at idle.
        from app.db.models import Book

        where_conditions = [
            Page.ocr_milestone == "succeeded",
            Page.chunking_milestone == "idle",
            ~Book.status.in_(["error"]),
        ]
        if spell_check_enabled:
            # Wait for spell check to finish (or fail) on this page first —
            # see module docstring for why order matters here.
            where_conditions.append(
                Page.spell_check_milestone.in_(["succeeded", "failed"])
            )

        id_stmt = (
            select(Page.id)
            .join(Book, Page.book_id == Book.id)
            .where(*where_conditions)
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
                chunking_milestone="in_progress",
                worker_id=ctx.get("worker_id", "unknown"),
                claimed_at=func.now(),
                last_updated=func.now(),
            )
        )
        # Update book-level chunking milestones
        for book_id in book_ids:
            await BookMilestoneService.update_book_milestone_for_step(
                session, book_id, "chunking"
            )
        await session.commit()

    await redis.enqueue_job("chunking_job", page_ids=page_ids)
    log_json(logger, logging.INFO, "chunking job dispatched", page_count=len(page_ids))
