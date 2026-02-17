"""System configuration repository with SQLAlchemy"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import SystemConfig
from app.db.repositories.base import BaseRepository


class SystemConfigsRepository(BaseRepository[SystemConfig]):
    """Repository for system configurations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, SystemConfig)

    async def get_value(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get config value by key with optional default"""
        config = await self.get(key)
        return config.value if config else default

    async def set_value(self, key: str, value: str, description: Optional[str] = None) -> SystemConfig:
        """Set config value, creating it if it doesn't exist"""
        config = await self.get(key)
        if config:
            config.value = value
            if description:
                config.description = description
            await self.session.commit()
            return config
        
        new_config = SystemConfig(key=key, value=value, description=description)
        await self.create(new_config)
        return new_config


def get_system_configs_repository(session: AsyncSession) -> SystemConfigsRepository:
    """Factory function for dependency injection"""
    return SystemConfigsRepository(session)
