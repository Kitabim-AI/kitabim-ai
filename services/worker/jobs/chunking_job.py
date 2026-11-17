"""
Chunking Job — book-scoped section-stream chunking.

Loads ordered pages and leaf `book_sections` for a book, builds unprefixed section-stream
chunks (`chunking_service.chunk_book_sections`), carries over existing embedding vectors
whose `text_hash` matches (`ChunksRepository.get_embedding_hash_map` + `replace_for_book`),
and transitions `Book.chunking_milestone` and `Book.embedding_milestone`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Optional

from sqlalchemy import func, select, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_COMPLETE,
)
from app.db import session as db_session
from app.db.models import Book, Page
from app.db.repositories.book_sections_repository import BookSectionsRepository
from app.db.repositories.chunks_repository import ChunksRepository
from app.services.cache_service import cache_service
from app.services.chunking_service import chunking_service
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.chunking_job")


async def _chunk_single_book(book_id: str) -> None:
    start_time = time.perf_counter()
    try:
        completed_cleanly = False
        section_chunks = []
        unembedded_count = 0

        for _attempt in range(3):
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        pipeline_step="chunking",
                        chunking_milestone=BOOK_MILESTONE_IN_PROGRESS,
                        chunking_claimed_at=func.now(),
                        last_updated=func.now(),
                    )
                )
                await session.commit()

            async with db_session.async_session_factory() as session:
                sections_repo = BookSectionsRepository(session)
                pages_res = await session.execute(
                    select(Page)
                    .where(Page.book_id == book_id)
                    .order_by(Page.page_number.asc())
                )
                pages = list(pages_res.scalars().all())
                sections = await sections_repo.list_leaf_sections(book_id)

            section_chunks = chunking_service.chunk_book_sections(pages, sections)
            chunk_payloads = [
                {
                    "book_id": book_id,
                    "page_number": ch.page_number,
                    "end_page_number": ch.end_page_number,
                    "chunk_index": ch.chunk_index,
                    "text": ch.text,
                    "section_id": ch.section_id,
                    "text_hash": ch.text_hash,
                }
                for ch in section_chunks
            ]

            async with db_session.async_session_factory() as session:
                chunks_repo = ChunksRepository(session)
                unembedded_count = await chunks_repo.replace_for_book(
                    book_id,
                    chunk_payloads,
                )

                cur_res = await session.execute(
                    select(Book.chunking_milestone)
                    .where(Book.id == book_id)
                    .with_for_update()
                )
                cur_row = cur_res.first() if hasattr(cur_res, "first") else None
                cur_chunk_ms = (
                    cur_row[0]
                    if isinstance(cur_row, (tuple, list)) and len(cur_row) > 0
                    else getattr(cur_row, "chunking_milestone", None)
                )
                if (
                    isinstance(cur_chunk_ms, str)
                    and cur_chunk_ms == BOOK_MILESTONE_IDLE
                ):
                    await session.commit()
                    log_json(
                        logger,
                        logging.INFO,
                        "book dirtied during chunking job; re-running chunking",
                        book_id=book_id,
                    )
                    continue

                await session.execute(
                    update(Page)
                    .where(
                        Page.book_id == book_id,
                        Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
                    )
                    .values(
                        chunking_milestone="succeeded",
                        last_updated=func.now(),
                    )
                )

                if unembedded_count == 0:
                    await session.execute(
                        update(Page)
                        .where(
                            Page.book_id == book_id,
                            Page.ocr_milestone == PAGE_MILESTONE_COMPLETE,
                        )
                        .values(
                            embedding_milestone="succeeded",
                            is_indexed=True,
                            last_updated=func.now(),
                        )
                    )
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            chunking_milestone=BOOK_MILESTONE_COMPLETE,
                            chunking_retry_count=0,
                            chunking_claimed_at=None,
                            embedding_milestone=BOOK_MILESTONE_COMPLETE,
                            embedding_retry_count=0,
                            embedding_claimed_at=None,
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()
                    try:
                        await cache_service.delete_pattern(f"rag:search:{book_id}:*")
                    except Exception:
                        pass
                else:
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            chunking_milestone=BOOK_MILESTONE_COMPLETE,
                            chunking_retry_count=0,
                            chunking_claimed_at=None,
                            embedding_milestone=BOOK_MILESTONE_IDLE,
                            embedding_retry_count=0,
                            embedding_claimed_at=None,
                            pipeline_step="embedding",
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()

                completed_cleanly = True
                break

        if not completed_cleanly:
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        chunking_milestone=BOOK_MILESTONE_IDLE,
                        chunking_claimed_at=None,
                        last_updated=func.now(),
                    )
                )
                await session.commit()
            return

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        log_json(
            logger,
            logging.INFO,
            "chunking job completed for book",
            book_id=book_id,
            total_chunks=len(section_chunks),
            unembedded_chunks=unembedded_count,
            duration_ms=duration_ms,
        )

    except (Exception, asyncio.CancelledError) as exc:
        error_msg = (str(exc) or exc.__class__.__name__)[:500]
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(
                    chunking_milestone=BOOK_MILESTONE_FAILED,
                    chunking_retry_count=Book.chunking_retry_count + 1,
                    chunking_claimed_at=None,
                    last_updated=func.now(),
                )
            )
            await session.commit()

        log_json(
            logger,
            logging.ERROR,
            "chunking job failed for book",
            book_id=book_id,
            error=error_msg,
        )
        if isinstance(exc, asyncio.CancelledError):
            raise


async def chunking_job(
    ctx,
    book_id: Optional[str] = None,
    page_ids: Optional[List[int]] = None,
) -> None:
    target_book_ids: List[str] = []
    if book_id:
        target_book_ids.append(book_id)
    elif page_ids:
        async with db_session.async_session_factory() as session:
            res = await session.execute(
                select(Page.book_id).where(Page.id.in_(page_ids)).distinct()
            )
            target_book_ids = [r[0] for r in res.fetchall() if r[0]]

    if not target_book_ids:
        return

    for bid in target_book_ids:
        await _chunk_single_book(bid)
