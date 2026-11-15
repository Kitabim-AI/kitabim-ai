"""
Structure Scanner — claims books ready for deterministic structure analysis
and dispatches `structure_job(book_id=...)`.

Runs every 1 minute.
"""

from __future__ import annotations

import logging

from app.db import session as db_session
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.book_structure_service import (
    claim_books_for_structure,
    enqueue_claimed_structure_jobs,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.structure_scanner")


async def run_structure_scanner(ctx) -> None:
    redis = ctx["redis"]

    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        spell_check_enabled = (
            await config_repo.get_value("spell_check_enabled", "false")
        ).lower() == "true"

        book_ids = await claim_books_for_structure(
            session,
            require_spell_check_terminal=spell_check_enabled,
            limit=20,
        )
        if not book_ids:
            return
        await session.commit()

    dispatched = await enqueue_claimed_structure_jobs(
        redis,
        book_ids,
        session_factory=db_session.async_session_factory,
    )

    log_json(
        logger,
        logging.INFO,
        "structure jobs dispatched",
        book_count=dispatched,
    )
