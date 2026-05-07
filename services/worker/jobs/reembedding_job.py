"""
Reembedding Job — re-embeds all chunks for one book into embedding_v2 (3072-dim)
using Gemini Embedding 2, then re-embeds the book's summary.

Only processes chunks where embedding IS NOT NULL (v1 exists) AND embedding_v2 IS NULL,
so it is safe to retry and resume partial progress.

Triggered by reembedding_scanner. Book-level job — re-raises on failure so arq
records it and retries.

Remove this file (and its registration in worker.py) after migration 037 is applied.
"""
from __future__ import annotations

import logging
from typing import List

from sqlalchemy import select, update

from app.core.config import settings
from app.db import session as db_session
from app.db.models import BookSummary, Chunk
from app.db.repositories.system_configs import SystemConfigsRepository
from app.langchain.models import GeminiEmbeddings
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.reembedding_job")


async def reembedding_job(ctx, book_id: str) -> None:
    log_json(logger, logging.INFO, "reembedding job started", book_id=book_id)

    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            model_name = await config_repo.get_value("gemini_embedding_model_v2")
            if not model_name:
                raise RuntimeError("system_config 'gemini_embedding_model_v2' is not set")

        embeddings_model = GeminiEmbeddings(model_name)

        # ── Re-embed chunks ───────────────────────────────────────────────────
        total_chunks = 0

        async with db_session.async_session_factory() as session:
            result = await session.execute(
                select(Chunk.id, Chunk.text)
                .where(
                    Chunk.book_id == book_id,
                    Chunk.embedding.isnot(None),
                    Chunk.embedding_v2.is_(None),
                )
                .order_by(Chunk.id)
            )
            pending = result.fetchall()

        for i in range(0, len(pending), settings.embed_batch_size):
            batch = pending[i : i + settings.embed_batch_size]
            chunk_ids = [row.id for row in batch]
            texts = [row.text for row in batch]

            vectors: List[List[float]] = await embeddings_model.aembed_documents(texts)

            async with db_session.async_session_factory() as session:
                for chunk_id, vector in zip(chunk_ids, vectors):
                    await session.execute(
                        update(Chunk)
                        .where(Chunk.id == chunk_id)
                        .values(embedding_v2=vector)
                    )
                await session.commit()

            total_chunks += len(batch)

        log_json(
            logger, logging.INFO, "reembedding job: chunks done",
            book_id=book_id, chunks=total_chunks,
        )

        # ── Re-embed book summary ─────────────────────────────────────────────
        async with db_session.async_session_factory() as session:
            result = await session.execute(
                select(BookSummary.summary)
                .where(
                    BookSummary.book_id == book_id,
                    BookSummary.embedding_v2.is_(None),
                )
            )
            row = result.one_or_none()

        if row:
            vectors = await embeddings_model.aembed_documents([row.summary])
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(BookSummary)
                    .where(BookSummary.book_id == book_id)
                    .values(embedding_v2=vectors[0])
                )
                await session.commit()
            log_json(logger, logging.INFO, "reembedding job: summary done", book_id=book_id)

        log_json(
            logger, logging.INFO, "reembedding job completed",
            book_id=book_id, chunks=total_chunks,
        )

    except Exception as exc:
        log_json(logger, logging.ERROR, "reembedding job failed", book_id=book_id, error=str(exc))
        raise
