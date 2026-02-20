"""Database seeding logic"""
import logging
from app.db.repositories.system_configs import SystemConfigsRepository
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.observability import log_json

logger = logging.getLogger("app.db.seeds")

async def seed_system_configs(session: AsyncSession):
    """Seed default system configurations if they don't exist"""
    repo = SystemConfigsRepository(session)
    
    defaults = [
        {
            "key": "pdf_processing_enabled",
            "value": "true",
            "description": "Enable or disable PDF processing system-wide (true/false)"
        },
        {
            "key": "llm_cb_failure_threshold",
            "value": str(settings.llm_cb_failure_threshold),
            "description": "Number of consecutive failures before opening circuit breaker"
        },
        {
            "key": "llm_cb_recovery_seconds",
            "value": str(settings.llm_cb_recovery_seconds),
            "description": "Seconds to wait before attempting recovery (half-open)"
        }
    ]
    
    for item in defaults:
        existing = await repo.get(item["key"])
        if not existing:
            log_json(logger, logging.INFO, "Seeding system config", key=item["key"], value=item["value"])
            await repo.create(**item)
    
    await session.commit()
