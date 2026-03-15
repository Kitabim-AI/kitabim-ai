"""
Word Index Scanner — builds book_word_index for cross-book spell check lookups.

Processes up to BATCH_SIZE un-indexed pages per run. Each page is committed
independently so a failure marks only that page as 'error' and does not affect
others. Pages with word_index_milestone='error' are skipped on future runs.

Runs every 1 minute.
"""
from __future__ import annotations

import logging
import traceback
from collections import Counter

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Page, PipelineEvent
from app.services.spell_check_service import index_book_words, tokenize
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.word_index_scanner")

BATCH_SIZE = 1000


async def run_word_index_scanner(ctx) -> None:
    # Fetch a batch of pages that still need indexing.
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(Page.id)
            .where(
                Page.ocr_milestone == "succeeded",
                Page.text.isnot(None),
                Page.word_index_milestone == "idle",
            )
            .with_for_update(skip_locked=True)
            .limit(BATCH_SIZE)
        )
        page_ids = [row[0] for row in result.fetchall()]

    if not page_ids:
        return

    succeeded = 0
    failed = 0
    processed_book_ids = set()

    for page_id in page_ids:
        try:
            async with db_session.async_session_factory() as session:
                # Reload page within the processing transaction
                res = await session.execute(select(Page).where(Page.id == page_id))
                page = res.scalar_one()
                tokens = tokenize(page.text or "")
                word_freq = Counter(word_norm for word_norm, _raw, _s, _e in tokens)
                await index_book_words(session, page.book_id, word_freq)
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(word_index_milestone="done", last_updated=func.now())
                )
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="word_index_succeeded"
                ))
                await session.commit()
                processed_book_ids.add(page.book_id)
            succeeded += 1

        except Exception as exc:
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(
                        word_index_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        last_updated=func.now()
                    )
                )
                await session.commit()
            processed_book_ids.add(page.book_id)
            failed += 1
            log_json(logger, logging.WARNING, "word index page failed",
                     book_id=page.book_id, page=page.page_number,
                     error=repr(exc), traceback=traceback.format_exc())

    # Update book-level word_index milestone after processing batch
    for book_id in processed_book_ids:
        async with db_session.async_session_factory() as session:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'word_index')

    log_json(logger, logging.INFO, "word index scanner run complete",
             batch=len(page_ids), succeeded=succeeded, failed=failed)
