"""
Auto-Correction Scanner — finds pages with auto-correctable issues and dispatches AutoCorrectJob.

A page is eligible when:
  - It has open spell check issues
  - Those issues match correction rules with auto_apply=True
  - The issues have valid char_offset and char_end (required for text replacement)

Runs every 5 minutes (configurable via system_configs).
"""
from __future__ import annotations

import logging
import traceback

from app.db import session as db_session
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.auto_correct_service import (
    find_pages_with_auto_correctable_issues,
    cleanup_stale_auto_corrections
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.auto_correct_scanner")


async def run_auto_correct_scanner(ctx) -> None:
    """
    Find pages with auto-correctable issues and dispatch auto-correction jobs.

    Args:
        ctx: Worker context (contains redis, config, etc.)
    """
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)

        # Check if auto-correction is enabled
        if (await config_repo.get_value("auto_correct_enabled", "false")) != "true":
            return
            
        # Cleanup stale jobs first
        reverted = await cleanup_stale_auto_corrections(session)
        if reverted > 0:
            log_json(logger, logging.INFO, "cleaned up stale auto-corrections", count=reverted)

        # Get batch size from config
        batch_size = int(await config_repo.get_value("auto_correct_batch_size", "50"))

        # Find pages with auto-correctable issues
        page_ids = await find_pages_with_auto_correctable_issues(session, limit=batch_size)

        if not page_ids:
            return

    # Enqueue the auto-correction job
    await redis.enqueue_job("auto_correct_job", page_ids=page_ids)
    log_json(logger, logging.INFO, "auto-correction job dispatched", page_count=len(page_ids))
