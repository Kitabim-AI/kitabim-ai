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

logger = logging.getLogger("app.worker_v2.stale_watchdog")

STALE_THRESHOLD_MINUTES = 30


async def run_stale_watchdog(ctx) -> None:
    threshold = datetime.now(timezone.utc) - timedelta(minutes=STALE_THRESHOLD_MINUTES)

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            update(Page)
            .where(
                Page.v2_milestone == "in_progress",
                Page.last_updated < threshold,
            )
            .values(v2_milestone="idle", last_updated=func.now())
            .returning(Page.id)
        )
        reset_count = len(result.fetchall())
        await session.commit()

    log_json(logger, logging.INFO, "V2 stale watchdog ran", pages_reset=reset_count)
