"""
Batch Embedding Poller Scanner — Periodically checks status of active Gemini Batch API embedding jobs
and ingests completed vectors into the database.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.services.batch_embedding_service import poll_and_process_batch_embedding_jobs
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.batch_embedding_poller_scanner")


async def run_batch_embedding_poller_scanner(ctx) -> None:
    log_json(logger, logging.INFO, "Batch embedding poller scanner started")
    try:
        async with db_session.async_session_factory() as session:
            processed = await poll_and_process_batch_embedding_jobs(session)

        if processed:
            log_json(
                logger,
                logging.INFO,
                "Batch embedding poller scanner completed",
                jobs_processed=processed,
            )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "Error running Batch embedding poller scanner",
            error=str(exc),
        )
