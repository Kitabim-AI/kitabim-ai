"""
Batch History Poller Scanner — Periodically checks status of active Gemini Batch API history extraction jobs
and ingests completed results into the staging database.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.batch_history_extraction_service import (
    poll_and_process_batch_history_jobs,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.batch_history_poller_scanner")


async def run_batch_history_poller_scanner(ctx) -> None:
    log_json(logger, logging.INFO, "Batch History poller scanner started")
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            enabled = await config_repo.get_value("history_extraction_enabled", "true")
            if enabled.strip().lower() != "true":
                log_json(
                    logger,
                    logging.INFO,
                    "Batch History poller scanner skipped: feature is disabled via system_configs",
                )
                return

            processed = await poll_and_process_batch_history_jobs(session)

        if processed:
            log_json(
                logger,
                logging.INFO,
                "Batch History poller scanner completed",
                jobs_processed=processed,
            )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "Error running Batch History poller scanner",
            error=str(exc),
        )
