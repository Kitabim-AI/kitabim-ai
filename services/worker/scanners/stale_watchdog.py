"""
Stale Watchdog — resets pages stuck in_progress back to idle.

Handles crashed jobs or pods that were killed mid-processing.
One rule covers all pipeline steps. Runs every 30 minutes.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import update, func

from app.db import session as db_session
from app.db.models import Page
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.stale_watchdog")

STALE_THRESHOLD_MINUTES = 30


async def run_stale_watchdog(ctx) -> None:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    now = func.now()

    async with db_session.async_session_factory() as session:
        from sqlalchemy import or_, case
        
        # Identify pages with ANY decoupled milestone stuck in_progress
        stmt = (
            update(Page)
            .where(
                or_(
                    Page.ocr_milestone == "in_progress",
                    Page.chunking_milestone == "in_progress",
                    Page.embedding_milestone == "in_progress",
                    Page.word_index_milestone == "in_progress",
                    Page.spell_check_milestone == "in_progress",
                    Page.milestone == "in_progress"  # Legacy support
                ),
                Page.last_updated < threshold
            )
            .values(
                ocr_milestone=case((Page.ocr_milestone == "in_progress", "idle"), else_=Page.ocr_milestone),
                chunking_milestone=case((Page.chunking_milestone == "in_progress", "idle"), else_=Page.chunking_milestone),
                embedding_milestone=case((Page.embedding_milestone == "in_progress", "idle"), else_=Page.embedding_milestone),
                word_index_milestone=case((Page.word_index_milestone == "in_progress", "idle"), else_=Page.word_index_milestone),
                spell_check_milestone=case((Page.spell_check_milestone == "in_progress", "idle"), else_=Page.spell_check_milestone),
                milestone=case((Page.milestone == "in_progress", "idle"), else_=Page.milestone),
                last_updated=now
            )
            .returning(Page.id)
        )
        
        result = await session.execute(stmt)
        reset_ids = [row[0] for row in result.fetchall()]
        await session.commit()

    if reset_ids:
        log_json(logger, logging.INFO, "stale watchdog reset pages", count=len(reset_ids))
    else:
        log_json(logger, logging.DEBUG, "stale watchdog: no stale pages found")

