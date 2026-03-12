"""
Shared ARQ worker lifecycle hooks.

Imported by services/worker/worker/worker.py.
All job functions live in services/worker/worker/ (scanners and jobs).
"""
from __future__ import annotations

import logging

from app.core.config import settings
from app.db import session as db_session
from app.db.session import init_db, close_db
from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json

logger = logging.getLogger("app.queue")


async def worker_startup(ctx):
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    configure_logging(level=log_level)
    configure_langchain()
    await init_db()

    try:
        from app.db.seeds import seed_system_configs
        async with db_session.async_session_factory() as session:
            await seed_system_configs(session)
    except Exception as exc:
        log_json(logger, logging.ERROR, "Worker system config seeding failed", error=str(exc))


async def worker_shutdown(ctx):
    await close_db()
