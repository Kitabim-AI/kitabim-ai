"""
Chunking Job — splits each page's OCR text into chunks and saves them to the DB.

Each page is processed in its own session scope for error isolation.
Pages with no text (empty or auto-skipped) are marked succeeded with zero chunks.

Receives: page_ids (list of Page.id already set to in_progress by scanner).
"""
from __future__ import annotations

import time
import logging
from typing import List

from sqlalchemy import select, update, delete, func

from app.db import session as db_session
from app.db.models import Book, Chunk, Page, PipelineEvent
from app.services.chunking_service import chunking_service
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json, make_pipeline_event_payload
from app.utils.text import clean_uyghur_text

logger = logging.getLogger("app.worker.chunking_job")


async def chunking_job(ctx, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "chunking job started", page_count=len(page_ids))

    from app.utils.redis_lock import MultiPageLock
    from app.utils.circuit_breaker import get_redis

    redis_client = ctx.get("redis") or get_redis()
    lock_manager = MultiPageLock(redis_client, page_ids)
    locked_page_ids = await lock_manager.__aenter__()

    try:
        if not locked_page_ids:
            log_json(logger, logging.WARNING, "No page locks acquired, exiting job")
            return

        # Update worker_id and claimed_at to current executing worker
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Page)
                .where(Page.id.in_(locked_page_ids))
                .values(
                    worker_id=ctx.get("worker_id", "unknown"),
                    claimed_at=func.now(),
                    last_updated=func.now()
                )
            )
            await session.commit()

        # Load page records
        async with db_session.async_session_factory() as session:
            result = await session.execute(select(Page).where(Page.id.in_(locked_page_ids)))
            pages = list(result.scalars().all())

        # Update book pipeline steps for all unique books in this batch
        book_ids = list({p.book_id for p in pages})
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id.in_(book_ids))
                .values(pipeline_step="chunking")
            )
            await session.commit()

        succeeded = 0
        failed = 0

        for page in pages:
            start_time = time.perf_counter()
            try:
                async with db_session.async_session_factory() as session:
                    # Skip chunking if it's a Table of Contents (already marked by OCR job)
                    if page.is_toc:
                        chunks = []
                    else:
                        text = clean_uyghur_text(page.text or "")
                        chunks = chunking_service.split_text(text)

                    # Delete any chunks that exceed the new chunk count (to clean up shrinking pages)
                    await session.execute(
                        delete(Chunk).where(
                            Chunk.book_id == page.book_id,
                            Chunk.page_number == page.page_number,
                            Chunk.chunk_index >= len(chunks)
                        )
                    )

                    if chunks:
                        from sqlalchemy.dialects.postgresql import insert
                        stmt = insert(Chunk).values([
                            {
                                "book_id": page.book_id,
                                "page_number": page.page_number,
                                "chunk_index": idx,
                                "text": chunk_text,
                            }
                            for idx, chunk_text in enumerate(chunks)
                        ])
                        stmt = stmt.on_conflict_do_update(
                            index_elements=["book_id", "page_number", "chunk_index"],
                            set_={
                                "text": stmt.excluded.text,
                                "embedding": None,
                            }
                        )
                        await session.execute(stmt)

                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(chunking_milestone="succeeded", last_updated=func.now())
                    )
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="chunking_succeeded",
                        payload=make_pipeline_event_payload(duration_ms=duration_ms)
                    ))
                    await session.commit()

                succeeded += 1
                log_json(logger, logging.DEBUG, "chunking page succeeded",
                         book_id=page.book_id, page=page.page_number,
                         chunks=len(chunks))

            except Exception as exc:
                duration_ms = int((time.perf_counter() - start_time) * 1000)
                async with db_session.async_session_factory() as session:
                    error_msg = str(exc)[:500]
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(
                            chunking_milestone="failed",
                            retry_count=Page.retry_count + 1,
                            error=error_msg,
                            last_updated=func.now(),
                        )
                    )
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="chunking_failed",
                        payload=make_pipeline_event_payload(
                            duration_ms=duration_ms,
                            extra_fields={"error": error_msg}
                        )
                    ))
                    await session.commit()

                failed += 1
                log_json(logger, logging.WARNING, "chunking page failed",
                         book_id=page.book_id, page=page.page_number, error=str(exc))

        # Update book-level chunking milestone after processing batch
        # Get book_id from first page
        if pages:
            book_id = pages[0].book_id
            async with db_session.async_session_factory() as session:
                await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'chunking')
                await session.commit()

        log_json(logger, logging.INFO, "chunking job completed",
                 succeeded=succeeded, failed=failed)
    finally:
        await lock_manager.__aexit__(None, None, None)
