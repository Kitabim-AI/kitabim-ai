"""
Graph Scanner — backfill and retry for book knowledge graphs in Memgraph.

Catches three cases:
  1. Books that were already 'ready' before this feature was deployed
  2. Books whose knowledge_graph_job failed (no node in Memgraph)
  3. Books whose graph needs backfilling

Runs every 5 minutes. Batch size controlled by system_config 'graph_scanner_batch_size'
(default 5).
"""
from __future__ import annotations

import logging

from sqlalchemy import select

from app.db import session as db_session
from app.db.models import Book
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.repositories.graph import GraphRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.graph_scanner")


async def run_graph_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        batch_size = int(
            await SystemConfigsRepository(session).get_value("graph_scanner_batch_size", "5")
        )
        # Find books that are 'ready'
        stmt = (
            select(Book.id)
            .where(Book.status == "ready")
            .limit(batch_size * 5)  # Fetch candidates to check in Memgraph in bulk
        )
        result = await session.execute(stmt)
        book_ids = [str(row[0]) for row in result.fetchall()]

    if not book_ids:
        return

    # Check which of these books already exist in Memgraph
    graph_repo = GraphRepository()
    try:
        existing_books = await graph_repo.check_books_exist(book_ids)
    except Exception as exc:
        log_json(logger, logging.ERROR, "graph scanner failed to check existing books in Memgraph", error=str(exc))
        return
    finally:
        await graph_repo.close()

    # Books that need graph generation (not present in Memgraph)
    missing_book_ids = [bid for bid in book_ids if bid not in existing_books]

    # Limit to batch size
    to_enqueue = missing_book_ids[:batch_size]

    if not to_enqueue:
        return

    for book_id in to_enqueue:
        await redis.enqueue_job(
            "knowledge_graph_job",
            book_id=book_id,
            _job_id=f"knowledge_graph:{book_id}"
        )

    log_json(logger, logging.INFO, "graph scanner enqueued jobs", count=len(to_enqueue), book_ids=to_enqueue)
