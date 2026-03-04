"""Database seeding logic"""
import logging
from app.db.repositories.system_configs import SystemConfigsRepository
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.observability import log_json

logger = logging.getLogger("app.db.seeds")

async def seed_system_configs(session: AsyncSession):
    """Seed default system configurations if they don't exist"""
    repo = SystemConfigsRepository(session)
    
    defaults = [
        {
            "key": "ocr_max_retry_count",
            "value": "10",
            "description": "Maximum number of OCR retry attempts per page before marking it as error/skipped."
        },
    ]
    
    for item in defaults:
        existing = await repo.get(item["key"])
        if not existing:
            log_json(logger, logging.INFO, "Seeding system config", key=item["key"], value=item["value"])
            await repo.create(**item)
    
    await session.commit()
