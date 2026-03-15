"""
Embedding Job — generates and stores 768-dim embeddings for each page's chunks.

Processes chunks in batches of EMBED_BATCH_SIZE to stay within API limits.
Pages with no chunks (empty text) are marked succeeded immediately.
Each page is processed in its own session scope for error isolation.

Receives: page_ids (list of Page.id already set to in_progress by scanner).
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import select, update, func

from app.db import session as db_session
from app.db.models import Book, Chunk, Page, PipelineEvent
from app.langchain.models import GeminiEmbeddings
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.embedding_job")

# Increased from 20 to 50 for 2.5x fewer API calls (safe: Gemini supports up to 100)
EMBED_BATCH_SIZE = 50


async def embedding_job(ctx, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "embedding job started", page_count=len(page_ids))

    # Load page records
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    # Update book pipeline steps for all unique books in this batch
    book_ids = list({p.book_id for p in pages})
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(Book)
            .where(Book.id.in_(book_ids))
            .values(pipeline_step="embedding")
        )
        await session.commit()

    embeddings_model = GeminiEmbeddings()
    succeeded = 0
    failed = 0

    for page in pages:
        try:
            async with db_session.async_session_factory() as session:
                # Load unembedded chunks for this page
                result = await session.execute(
                    select(Chunk)
                    .where(
                        Chunk.book_id == page.book_id,
                        Chunk.page_number == page.page_number,
                        Chunk.embedding.is_(None),
                    )
                    .order_by(Chunk.chunk_index)
                )
                chunks = list(result.scalars().all())

                if not chunks:
                    # No chunks to embed (empty page) — mark succeeded and move on
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(
                            embedding_milestone="succeeded",
                            is_indexed=True,
                            last_updated=func.now(),
                        )
                    )
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="embedding_succeeded"
                    ))
                    await session.commit()
                    succeeded += 1
                    continue

                # Embed in batches to respect API limits
                all_vectors: List[List[float]] = []
                for i in range(0, len(chunks), EMBED_BATCH_SIZE):
                    batch = chunks[i : i + EMBED_BATCH_SIZE]
                    vectors = await embeddings_model.aembed_documents(
                        [c.text for c in batch]
                    )
                    all_vectors.extend(vectors)

                # Persist embeddings
                for chunk, vector in zip(chunks, all_vectors):
                    await session.execute(
                        update(Chunk)
                        .where(Chunk.id == chunk.id)
                        .values(embedding=vector)
                    )

                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(
                        embedding_milestone="succeeded",
                        is_indexed=True,
                        last_updated=func.now(),
                    )
                )
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="embedding_succeeded"
                ))
                await session.commit()

            succeeded += 1
            log_json(logger, logging.DEBUG, "embedding page succeeded",
                     book_id=page.book_id, page=page.page_number,
                     chunks=len(chunks))

        except Exception as exc:
            async with db_session.async_session_factory() as session:
                error_msg = str(exc)[:500]
                await session.execute(
                    update(Page)
                    .where(Page.id == page.id)
                    .values(
                        embedding_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        error=error_msg,
                        last_updated=func.now(),
                    )
                )
                session.add(PipelineEvent(
                    page_id=page.id,
                    event_type="embedding_failed",
                    payload=f'{{"error": "{error_msg}"}}'
                ))
                await session.commit()

            failed += 1
            log_json(logger, logging.WARNING, "embedding page failed",
                     book_id=page.book_id, page=page.page_number, error=str(exc))

    # Update book-level embedding milestone after processing batch
    if pages:
        book_id = pages[0].book_id
        async with db_session.async_session_factory() as session:
            await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'embedding')

    log_json(logger, logging.INFO, "embedding job completed",
             succeeded=succeeded, failed=failed)
