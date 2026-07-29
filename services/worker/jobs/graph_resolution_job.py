"""
Graph Resolution Job — resolves a batch of claimed `graph_resolution_queue` entities
(design v2 §4). One entity per Postgres session, error-isolated — a failure on one
entity marks its own queue row `failed` and never aborts the rest of the batch.

All resolution logic (candidate selection, hard-constraint/graded-signal/gray-zone
decision, merge execution, re-propagation) lives in
`app.services.entity_resolution_service.resolve_entity` so it's shared with the
admin-triggered merge/split endpoints.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.graph_resolution_repository import (
    GraphResolutionQueueRepository,
)
from app.services.entity_resolution_service import resolve_entity
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.graph_resolution_job")


async def graph_resolution_job(ctx, entity_ids: list[str]) -> None:
    log_json(
        logger, logging.INFO, "graph resolution job started", count=len(entity_ids)
    )

    graph_repo = GraphRepository()
    succeeded = 0
    failed = 0
    try:
        for entity_id in entity_ids:
            try:
                async with db_session.async_session_factory() as session:
                    await resolve_entity(session, graph_repo, entity_id)
                succeeded += 1
            except Exception as exc:
                failed += 1
                log_json(
                    logger,
                    logging.ERROR,
                    "graph resolution failed for entity",
                    entity_id=entity_id,
                    error=str(exc),
                )
                try:
                    async with db_session.async_session_factory() as session:
                        queue_repo = GraphResolutionQueueRepository(session)
                        await queue_repo.mark_status(entity_id, "failed")
                except Exception as db_exc:
                    log_json(
                        logger,
                        logging.ERROR,
                        "failed to mark entity resolution row as failed",
                        entity_id=entity_id,
                        error=str(db_exc),
                    )
    finally:
        await graph_repo.close()

    log_json(
        logger,
        logging.INFO,
        "graph resolution job completed",
        succeeded=succeeded,
        failed=failed,
    )
