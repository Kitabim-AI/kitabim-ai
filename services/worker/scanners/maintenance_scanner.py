"""
Maintenance Scanner — periodically cleans up old processed events and logs.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db import session as db_session
from app.db.models import PipelineEvent
from app.db.repositories.system_configs import SystemConfigsRepository
from app.core.config import settings
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.maintenance_scanner")

async def run_maintenance_scanner(ctx) -> None:
    """
    Periodic task to clean up old data.
    Runs according to the schedule in worker.py.
    """
    try:
        async with db_session.async_session_factory() as session:
            # 1. Fetch dynamic retention setting from DB
            repo = SystemConfigsRepository(session)
            db_retention = await repo.get_value("maintenance_retention_days")
            
            retention_days = int(db_retention) if db_retention else settings.maintenance_retention_days
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)

            log_json(logger, logging.INFO, "maintenance scanner: starting cleanup", 
                     retention_days=retention_days, cutoff_date=cutoff_date.isoformat())

            # 2. Clean up processed PipelineEvents
            stmt = (
                delete(PipelineEvent)
                .where(PipelineEvent.processed.is_(True))
                .where(PipelineEvent.created_at < cutoff_date)
            )
            result = await session.execute(stmt)
            deleted_events = result.rowcount

            # Commit the deletions
            await session.commit()

            log_json(logger, logging.INFO, "maintenance scanner: cleanup complete",
                     deleted_events=deleted_events)

    except Exception as exc:
        log_json(logger, logging.ERROR, "maintenance scanner failed", error=str(exc))
