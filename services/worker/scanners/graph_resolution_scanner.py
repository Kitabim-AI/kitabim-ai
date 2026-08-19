"""
Graph Resolution Scanner — claims idle `graph_resolution_queue` rows and dispatches
`graph_resolution_job` to run the global entity resolution pass (design v2 §4).

Runs every 5 minutes. Claims rows oldest-generation-first (`scope, sort_year ASC NULLS
LAST`) so a parent is resolved before its children — "same father" evidence is checked
against an already-resolved father, not a still-ambiguous one.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.graph_resolution_repository import (
    GraphResolutionQueueRepository,
)
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.graph_resolution_scanner")


async def run_graph_resolution_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        kg_enabled_val = await config_repo.get_value("kg_enabled", "false")
        if kg_enabled_val != "true":
            log_json(
                logger,
                logging.DEBUG,
                "graph resolution scanner: knowledge graph feature is disabled via system_configs",
            )
            return

        batch_size = int(await config_repo.get_value("resolution_batch_size", "20"))
        queue_repo = GraphResolutionQueueRepository(session)
        claimed = await queue_repo.claim_batch(batch_size)

    if not claimed:
        return

    by_scope: dict[str, list[str]] = {}
    for row in claimed:
        by_scope.setdefault(row.scope, []).append(str(row.entity_id))

    enqueued_count = 0
    for scope, entity_ids in by_scope.items():
        job = await redis.enqueue_job(
            "graph_resolution_job",
            entity_ids=entity_ids,
            _job_id=f"graph_resolution:{scope}:batch",
        )
        if job is not None:
            enqueued_count += len(entity_ids)
        else:
            log_json(
                logger,
                logging.DEBUG,
                "graph resolution scanner: batch job already queued or running",
                scope=scope,
            )

    if enqueued_count:
        log_json(
            logger,
            logging.INFO,
            "graph resolution scanner enqueued batch",
            count=enqueued_count,
        )
