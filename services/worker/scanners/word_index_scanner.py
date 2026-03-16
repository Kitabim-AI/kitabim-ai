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

BATCH_SIZE = 500


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

    # Load all pages in the batch
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(Page).where(Page.id.in_(page_ids))
        )
        pages = result.scalars().all()

    # Group pages by book_id
    book_to_pages = {}
    for p in pages:
        book_to_pages.setdefault(p.book_id, []).append(p)

    succeeded = 0
    failed = 0
    processed_book_ids = set()

    for book_id, book_pages in book_to_pages.items():
        try:
            # Aggregate word frequencies for all pages of this book in the batch
            aggregated_freq = Counter()
            for page in book_pages:
                tokens = tokenize(page.text or "")
                page_freq = Counter(word_norm for word_norm, _raw, _s, _e in tokens)
                aggregated_freq.update(page_freq)

            async with db_session.async_session_factory() as session:
                # Perform one aggregated upsert for the book
                await index_book_words(session, book_id, aggregated_freq)

                # Mark all pages in this book-batch as done
                page_ids_in_batch = [p.id for p in book_pages]
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(page_ids_in_batch))
                    .values(word_index_milestone="done", last_updated=func.now())
                )

                # Record events
                for pid in page_ids_in_batch:
                    session.add(PipelineEvent(
                        page_id=pid,
                        event_type="word_index_succeeded"
                    ))

                await session.commit()
                processed_book_ids.add(book_id)
                succeeded += len(book_pages)

        except Exception as exc:
            # If the aggregated update fails, try to mark pages as failed
            # Note: This is rare as tokenize is CPU-only.
            async with db_session.async_session_factory() as session:
                page_ids_in_batch = [p.id for p in book_pages]
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(page_ids_in_batch))
                    .values(
                        word_index_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        last_updated=func.now()
                    )
                )
                await session.commit()
            processed_book_ids.add(book_id)
            failed += len(book_pages)
            log_json(logger, logging.WARNING, "word index book-batch failed",
                     book_id=book_id, page_count=len(book_pages),
                     error=repr(exc), traceback=traceback.format_exc())

    # Update book-level word_index milestone after processing batch
    for book_id in processed_book_ids:
        async with db_session.async_session_factory() as session:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'word_index')

    log_json(logger, logging.INFO, "word index scanner run complete",
             batch=len(page_ids), succeeded=succeeded, failed=failed)
