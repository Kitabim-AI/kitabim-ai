"""
Batch LLM Spell Check Poller Scanner — periodically checks status of active
Gemini Batch API LLM spell-check jobs and applies completed corrections to
pages.text.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.batch_llm_spell_check_service import (
    poll_and_process_batch_llm_spell_check_jobs,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.batch_llm_spell_check_poller_scanner")


async def run_batch_llm_spell_check_poller_scanner(ctx) -> None:
    log_json(logger, logging.INFO, "Batch LLM Spell Check poller scanner started")
    try:
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            enabled = await config_repo.get_value(
                "llm_spell_check_batch_enabled", "false"
            )
            if enabled.strip().lower() != "true":
                log_json(
                    logger,
                    logging.INFO,
                    "Batch LLM Spell Check poller scanner skipped: feature is disabled via system_configs",
                )
                return

            processed = await poll_and_process_batch_llm_spell_check_jobs(session)

        if processed:
            log_json(
                logger,
                logging.INFO,
                "Batch LLM Spell Check poller scanner completed",
                jobs_processed=processed,
            )
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "Error running Batch LLM Spell Check poller scanner",
            error=str(exc),
        )
