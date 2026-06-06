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

from sqlalchemy import select, or_, update

from app.db import session as db_session
from app.db.models import Book
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.graph_scanner")


async def run_graph_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)

        # Check if Knowledge Graph is enabled
        kg_enabled_val = await config_repo.get_value("knowledge_graph_enabled", "false")
        if kg_enabled_val != "true":
            log_json(logger, logging.DEBUG, "graph scanner: knowledge graph generation is disabled via system_configs")
            return

        batch_size = int(
            await config_repo.get_value("graph_scanner_batch_size", "5")
        )
        # Find books that are 'ready' but have 'idle' or 'failed' graph milestone
        stmt = (
            select(Book.id)
            .where(
                Book.status == "ready",
                or_(
                    Book.graph_milestone == "idle",
                    Book.graph_milestone == "failed",
                )
            )
            .with_for_update(skip_locked=True)
            .limit(batch_size)
        )
        result = await session.execute(stmt)
        book_ids = [str(row[0]) for row in result.fetchall()]

        if not book_ids:
            return

        # Atomically update milestone to 'in_progress' to prevent subsequent runs from enqueuing duplicate jobs
        update_stmt = (
            update(Book)
            .where(Book.id.in_(book_ids))
            .values(graph_milestone="in_progress")
        )
        await session.execute(update_stmt)
        await session.commit()

    # Enqueue jobs via Redis outside the session scope
    newly_enqueued = []
    for book_id in book_ids:
        job = await redis.enqueue_job(
            "knowledge_graph_job",
            book_id=book_id,
            _job_id=f"knowledge_graph:{book_id}"
        )
        if job is not None:
            newly_enqueued.append(book_id)
        else:
            log_json(logger, logging.DEBUG, "graph scanner: job already queued or running", book_id=book_id)

    if newly_enqueued:
        log_json(logger, logging.INFO, "graph scanner enqueued jobs", count=len(newly_enqueued), book_ids=newly_enqueued)
