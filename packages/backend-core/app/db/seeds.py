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
        {
            "key": "gemini_chat_model",
            "value": "gemini-3.1-flash-lite-preview",
            "description": "Gemini model used for chat responses (reader chat and global chat)."
        },
        {
            "key": "gemini_categorization_model",
            "value": "gemini-3.1-flash-lite-preview",
            "description": "Gemini model used for category routing in global search."
        },
        {
            "key": "gemini_ocr_model",
            "value": "gemini-2.0-flash",
            "description": "Gemini model used for OCR page processing."
        },
        {
            "key": "maintenance_retention_days",
            "value": "7",
            "description": "Number of days to retain processed pipeline events before automated cleanup."
        },
        {
            "key": "spell_check_enabled",
            "value": "true",
            "description": "Globally enable/disable background spell check processing."
        }
    ]
    
    for item in defaults:
        existing = await repo.get(item["key"])
        if not existing:
            log_json(logger, logging.INFO, "Seeding system config", key=item["key"], value=item["value"])
            await repo.create(**item)
    
    await session.commit()
