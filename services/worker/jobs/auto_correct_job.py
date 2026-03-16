"""
Auto-Correction Job — batch auto-correction runner for the background worker.

Receives a list of page_ids that have open spell issues matching auto-correction
rules, and applies the corrections to each page via the auto_correct_service.
"""
from __future__ import annotations

import logging
import traceback
import asyncio
from typing import List

from sqlalchemy import select

from app.db import session as db_session
from app.db.models import Page, PipelineEvent
from app.services.auto_correct_service import (
    apply_auto_corrections_to_page,
    get_correction_rules
)
from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.auto_correct_job")

# Limit concurrency to avoid overloading DB or CPU


async def auto_correct_job(ctx, page_ids: List[int]) -> None:
    """
    Apply auto-corrections to a batch of pages.

    Args:
        ctx: Worker context (contains redis, config, etc.)
        page_ids: List of page IDs to process
    """
    log_json(logger, logging.INFO, "auto-correction job started", page_count=len(page_ids))

    # Fetch all pages in one query
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    if not pages:
        log_json(logger, logging.WARNING, "no pages found for auto-correction", page_ids=page_ids)
        return

    # Pre-fetch correction rules once for the entire batch (performance optimization)
    async with db_session.async_session_factory() as session:
        correction_rules = await get_correction_rules(session, auto_apply_only=True)

    if not correction_rules:
        log_json(logger, logging.WARNING, "no auto-apply correction rules found, skipping job")
        return

    log_json(logger, logging.INFO, "loaded correction rules", rule_count=len(correction_rules))

    semaphore = asyncio.Semaphore(settings.max_parallel_auto_correct)
    results = {"succeeded": 0, "failed": 0, "total_corrections": 0}

    async def process_page(page: Page):
        async with semaphore:
            try:
                async with db_session.async_session_factory() as session:
                    corrections_applied = await apply_auto_corrections_to_page(
                        session,
                        page.id,
                        correction_rules=correction_rules
                    )

                    if corrections_applied > 0:
                        session.add(PipelineEvent(
                            page_id=page.id,
                            event_type="auto_correct_succeeded",
                            payload=f'{{"corrections": {corrections_applied}}}'
                        ))
                        await session.commit()

                        results["succeeded"] += 1
                        results["total_corrections"] += corrections_applied

                        log_json(logger, logging.DEBUG, "auto-correction page succeeded",
                                 book_id=page.book_id,
                                 page=page.page_number,
                                 corrections=corrections_applied)
                    else:
                        # No corrections applied (maybe issues were already corrected)
                        log_json(logger, logging.DEBUG, "no corrections applied to page",
                                 book_id=page.book_id,
                                 page=page.page_number)

            except Exception as exc:
                async with db_session.async_session_factory() as session:
                    error_msg = repr(exc)[:500]
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="auto_correct_failed",
                        payload=f'{{"error": "{error_msg}"}}'
                    ))
                    await session.commit()

                results["failed"] += 1
                log_json(logger, logging.WARNING, "auto-correction page failed",
                         book_id=page.book_id,
                         page=page.page_number,
                         error=repr(exc),
                         traceback=traceback.format_exc())

    # Run all pages in parallel (respecting the semaphore)
    await asyncio.gather(*(process_page(p) for p in pages))

    log_json(logger, logging.INFO, "auto-correction job completed",
             succeeded=results["succeeded"],
             failed=results["failed"],
             total_corrections=results["total_corrections"],
             pages_processed=len(pages))
