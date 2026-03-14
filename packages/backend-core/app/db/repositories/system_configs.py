"""System configuration repository with SQLAlchemy"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import SystemConfig
from app.db.repositories.base import BaseRepository
from app.services.cache_service import cache_service
from app.core.config import settings

class SystemConfigsRepository(BaseRepository[SystemConfig]):
    """Repository for system configurations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, SystemConfig)

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get config value by key with cache"""
        cache_key = f"config:{key}"
        cached_value = await cache_service.get(cache_key)
        if cached_value is not None:
            return cached_value

        config = await self.get(key)
        value = config.value if config else default

        if value is not None:
            await cache_service.set(
                cache_key,
                value,
                ttl=settings.cache_ttl_system_config
            )

        return value


    async def set_value(self, key: str, value: str, description: Optional[str] = None) -> SystemConfig:
        """Set config value, creating it if it doesn't exist"""
        config = await self.get(key)
        if config:
            config.value = value
            if description:
                config.description = description
            await self.session.commit()
            await cache_service.delete(f"config:{key}")
            return config

        
        config = await self.create(key=key, value=value, description=description)
        await cache_service.delete(f"config:{key}")
        return config



def get_system_configs_repository(session: AsyncSession) -> SystemConfigsRepository:
    """Factory function for dependency injection"""
    return SystemConfigsRepository(session)
