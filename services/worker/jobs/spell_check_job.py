"""
Spell Check Job — batch spell check runner for the background worker.

Receives a list of page_ids (already set to in_progress by the scanner)
and runs spell check on each via the shared spell_check_service.
"""
from __future__ import annotations

import logging
import traceback
import asyncio
from typing import List

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, PipelineEvent, Book
from app.services.spell_check_service import run_spell_check_for_page, ThreadSafeSpellCheckCache
from app.services.book_milestone_service import BookMilestoneService
from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.spell_check_job")

# Limit concurrency to stay safely within DB connection limits.

async def spell_check_job(ctx, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "spell check job started", page_count=len(page_ids))

    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    cache = ThreadSafeSpellCheckCache()
    semaphore = asyncio.Semaphore(settings.max_parallel_spell_check)

    results = {"succeeded": 0, "failed": 0}

    async def process_page(page: Page):
        async with semaphore:
            try:
                async with db_session.async_session_factory() as session:
                    issue_count = await run_spell_check_for_page(session, page, cache=cache)
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="spell_check_succeeded",
                        payload=f'{{"issues": {issue_count}}}'
                    ))
                    await session.commit()

                results["succeeded"] += 1
                log_json(logger, logging.DEBUG, "spell check page succeeded",
                         book_id=page.book_id, page=page.page_number, ocr_issues=issue_count)

            except Exception as exc:
                async with db_session.async_session_factory() as session:
                    error_msg = repr(exc)[:500]
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(
                            spell_check_milestone="failed",
                            retry_count=Page.retry_count + 1,
                            last_updated=func.now()
                        )
                    )
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="spell_check_failed",
                        payload=f'{{"error": "{error_msg}"}}'
                    ))
                    await session.commit()
                results["failed"] += 1
                log_json(logger, logging.WARNING, "spell check page failed",
                         book_id=page.book_id, page=page.page_number,
                         error=repr(exc), traceback=traceback.format_exc())

    # Run all pages in parallel (respecting the semaphore)
    await asyncio.gather(*(process_page(p) for p in pages))

    # Cleanup: If a book has no more pages in 'idle' or 'in_progress' for spell check,
    # reset its pipeline_step to 'ready' so the UI pulsar stops.
    book_ids = list(set(p.book_id for p in pages))
    if book_ids:
        async with db_session.async_session_factory() as session:
            for bid in book_ids:
                remain_stmt = select(func.count(Page.id)).where(
                    Page.book_id == bid,
                    Page.spell_check_milestone.in_(["idle", "in_progress"])
                )
                res = await session.execute(remain_stmt)
                if (res.scalar() or 0) == 0:
                    await session.execute(
                        update(Book)
                        .where(Book.id == bid)
                        .values(pipeline_step="ready", last_updated=func.now())
                    )
            await session.commit()

    # Update book-level spell_check milestone after processing batch
    # Get unique book IDs from processed pages
    if pages:
        book_ids = {page.book_id for page in pages}
        for book_id in book_ids:
            async with db_session.async_session_factory() as session:
                await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'spell_check')

    # Get cache statistics for performance monitoring
    cache_stats = cache.get_stats()

    log_json(logger, logging.INFO, "spell check job completed",
             succeeded=results["succeeded"],
             failed=results["failed"],
             cache_overall_hit_rate=cache_stats["overall_hit_rate"],
             cache_total_lookups=cache_stats["total_lookups"],
             cache_unknown_hit_rate=cache_stats["unknown_words"]["hit_rate"],
             cache_ocr_hit_rate=cache_stats["ocr_corrections"]["hit_rate"])
