"""
Spell Check Scanner — claims pages ready for spell checking and dispatches SpellCheckJob.

A page is eligible when:
  - Its OCR/embedding pipeline has completed (pipeline_step='embedding', milestone='succeeded')
  - spell_check_milestone = 'idle'

This runs independently of the main OCR pipeline — spell check is a quality layer
on top of already-searchable books and does not block any other step.

Runs every 1 minute.
"""
from __future__ import annotations

import logging

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, Book
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.spell_check_scanner")


async def run_spell_check_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        if (await config_repo.get_value("spell_check_enabled", "false")) != "true":
            return
        page_limit = int(await config_repo.get_value("scanner_page_limit", "100"))

        # Atomically claim idle spell-check pages whose OCR pipeline is done.
        from sqlalchemy import or_
        id_stmt = (
            select(Page.id)
            .where(
                Page.ocr_milestone == "succeeded",
                Page.word_index_milestone == "done",
                Page.spell_check_milestone == "idle",
            )
            .with_for_update(skip_locked=True)
            .limit(page_limit)
        )
        result = await session.execute(id_stmt)
        page_ids = [row[0] for row in result.fetchall()]

        if not page_ids:
            return

        await session.execute(
            update(Page)
            .where(Page.id.in_(page_ids))
            .values(spell_check_milestone="in_progress", last_updated=func.now())
        )
        
        # Also update the Book record to show spell check is active in the Lite UI
        # Get unique book IDs from the claimed pages
        book_ids_stmt = select(Page.book_id).where(Page.id.in_(page_ids)).distinct()
        book_ids_res = await session.execute(book_ids_stmt)
        book_ids = [row[0] for row in book_ids_res.fetchall()]
        
        if book_ids:
            await session.execute(
                update(Book)
                .where(Book.id.in_(book_ids))
                .values(pipeline_step="spell_check", last_updated=func.now())
            )
            
        await session.commit()

    await redis.enqueue_job("spell_check_job", page_ids=page_ids)
    log_json(logger, logging.INFO, "spell check job dispatched", page_count=len(page_ids))
