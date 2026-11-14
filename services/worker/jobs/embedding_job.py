"""
Embedding Job — book-scoped online embedding.

Queries unembedded chunks for `book_id`, deduplicates by `text_hash`, calls
`GeminiEmbeddings.aembed_documents` (which slices into sub-batches of <= 64 texts
with `embed_gemini_timeout` default 45s), writes vectors to `chunks`, marks OCR'd
`Page` rows `embedding_milestone = 'succeeded', is_indexed = True`, marks
`Book.embedding_milestone = 'complete'`, and invalidates `rag:search:{book_id}:*`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Optional

from sqlalchemy import func, select, update

from app.core.pipeline import (
    BOOK_MILESTONE_COMPLETE,
    BOOK_MILESTONE_FAILED,
    BOOK_MILESTONE_IDLE,
    BOOK_MILESTONE_IN_PROGRESS,
    PAGE_MILESTONE_COMPLETE,
)
from app.db import session as db_session
from app.db.models import Book, Chunk, Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.llm.models import GeminiEmbeddings
from app.services.cache_service import cache_service
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.embedding_job")


async def _embed_single_book(book_id: str) -> None:
    start_time = time.perf_counter()
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            gemini_embedding_model = await config_repo.get_value("embed_gemini_model")
            if not gemini_embedding_model:
                raise RuntimeError("system_config 'embed_gemini_model' is not set")

            await session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(
                    pipeline_step="embedding",
                    embedding_milestone=BOOK_MILESTONE_IN_PROGRESS,
                    embedding_claimed_at=func.now(),
                    last_updated=func.now(),
                )
            )
            await session.commit()

        async with db_session.async_session_factory() as session:
            result = await session.execute(
                select(Chunk)
                .where(
                    Chunk.book_id == book_id,
                    Chunk.embedding.is_(None),
                )
                .order_by(Chunk.id.asc())
            )
            chunks = list(result.scalars().all())

        initial_chunk_ids = [c.id for c in chunks if getattr(c, "id", None) is not None]

        if chunks:
            embeddings_model = GeminiEmbeddings(gemini_embedding_model)
            rep_chunks: List[Chunk] = []
            hash_to_chunk_ids: Dict[str, List[int]] = {}

            for ch in chunks:
                t_hash = getattr(ch, "text_hash", None)
                if t_hash:
                    if t_hash not in hash_to_chunk_ids:
                        hash_to_chunk_ids[t_hash] = []
                        rep_chunks.append(ch)
                    hash_to_chunk_ids[t_hash].append(ch.id)
                else:
                    rep_chunks.append(ch)

            sub_batch_size = 64
            for idx in range(0, len(rep_chunks), sub_batch_size):
                batch_reps = rep_chunks[idx : idx + sub_batch_size]
                vectors = await embeddings_model.aembed_documents(
                    [c.text for c in batch_reps]
                )
                if len(vectors) != len(batch_reps) or any(v is None for v in vectors):
                    raise RuntimeError(
                        f"Incomplete embedding response for book {book_id}: "
                        f"expected {len(batch_reps)} vectors, got {len(vectors)}"
                    )
                async with db_session.async_session_factory() as session:
                    for rep_chunk, vector in zip(batch_reps, vectors):
                        t_hash = getattr(rep_chunk, "text_hash", None)
                        if t_hash and t_hash in hash_to_chunk_ids:
                            await session.execute(
                                update(Chunk)
                                .where(Chunk.id.in_(hash_to_chunk_ids[t_hash]))
                                .values(embedding=vector)
                            )
                        else:
                            await session.execute(
                                update(Chunk)
                                .where(Chunk.id == rep_chunk.id)
                                .values(embedding=vector)
                            )
                    await session.execute(
                        update(Book)
                        .where(Book.id == book_id)
                        .values(
                            embedding_claimed_at=func.now(),
                            last_updated=func.now(),
                        )
                    )
                    await session.commit()

        async with db_session.async_session_factory() as session:
            if initial_chunk_ids:
                initial_unembedded_res = await session.execute(
                    select(func.count(Chunk.id)).where(
                        Chunk.book_id == book_id,
                        Chunk.id.in_(initial_chunk_ids),
                        Chunk.embedding.is_(None),
                    )
                )
                raw_initial_rem = (
                    initial_unembedded_res.scalar()
                    if hasattr(initial_unembedded_res, "scalar")
                    else 0
                )
                initial_remaining = (
                    int(raw_initial_rem)
                    if isinstance(raw_initial_rem, (int, float))
                    and not isinstance(raw_initial_rem, bool)
                    else 0
                )
                if initial_remaining > 0:
                    raise RuntimeError(
                        f"{initial_remaining} chunk(s) in batch remained unembedded for book {book_id}"
                    )

            new_unembedded_cond = [
                Chunk.book_id == book_id,
                Chunk.embedding.is_(None),
            ]
            if initial_chunk_ids:
                new_unembedded_cond.append(~Chunk.id.in_(initial_chunk_ids))

            unembedded_res = await session.execute(
                select(func.count(Chunk.id)).where(*new_unembedded_cond)
            )
            raw_remaining = (
                unembedded_res.scalar() if hasattr(unembedded_res, "scalar") else 0
            )
            remaining_unembedded = (
                int(raw_remaining)
                if isinstance(raw_remaining, (int, float))
                and not isinstance(raw_remaining, bool)
                else 0
            )
            if remaining_unembedded > 0:
                await session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        embedding_milestone=BOOK_MILESTONE_IDLE,
                        embedding_claimed_at=None,
                        last_updated=func.now(),
                    )
                )
                await session.commit()
                log_json(
                    logger,
                    logging.INFO,
                    "embedding job found newly created unembedded chunks; resetting milestone to idle",
                    book_id=book_id,
                    remaining_unembedded=remaining_unembedded,
                )
                return

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

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        log_json(
            logger,
            logging.INFO,
            "embedding job completed for book",
            book_id=book_id,
            chunks_embedded=len(chunks),
            duration_ms=duration_ms,
        )

    except (Exception, asyncio.CancelledError) as exc:
        error_msg = (str(exc) or exc.__class__.__name__)[:500]
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book)
                .where(Book.id == book_id)
                .values(
                    embedding_milestone=BOOK_MILESTONE_FAILED,
                    embedding_retry_count=Book.embedding_retry_count + 1,
                    embedding_claimed_at=None,
                    last_updated=func.now(),
                )
            )
            await session.commit()

        log_json(
            logger,
            logging.ERROR,
            "embedding job failed for book",
            book_id=book_id,
            error=error_msg,
        )
        if isinstance(exc, asyncio.CancelledError):
            raise


async def embedding_job(
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
        await _embed_single_book(bid)
