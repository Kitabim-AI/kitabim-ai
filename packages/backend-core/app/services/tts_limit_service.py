"""Role-based daily TTS synthesis quota service (cache hits are free)."""

from __future__ import annotations

import logging
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import cache_config
from app.core.config import settings
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.db.repositories.user_tts_usage_repository import UserTtsUsageRepository
from app.models.user import User, UserRole
from app.services.cache_service import cache_service
from app.utils.observability import log_json

logger = logging.getLogger("app.tts_limit")

INCR_EXPIRE_LUA = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""


class TtsLimitService:
    async def get_limit_for_role(
        self, role: str, session: AsyncSession
    ) -> Optional[int]:
        """Get daily uncached TTS limit for a role from system_configs.

        Returns None for Admin (no limit).
        """
        role_val = getattr(role, "value", str(role))
        if role_val == UserRole.ADMIN or role == UserRole.ADMIN:
            return None

        repo = SystemConfigsRepository(session)
        limit_key = f"tts_limit_{role_val}"

        try:
            limit_val = await repo.get_value(limit_key)
            if limit_val is not None:
                return int(limit_val)
        except Exception as exc:
            log_json(
                logger,
                logging.WARNING,
                "Failed to fetch TTS limit from DB",
                key=limit_key,
                error=str(exc),
            )

        if role_val == UserRole.EDITOR:
            return 50
        if role_val == UserRole.READER:
            return 15
        return 10

    @staticmethod
    def _utc_now_and_ttl() -> tuple[datetime, int]:
        now = datetime.now(timezone.utc)
        tomorrow = datetime.combine(
            now.date() + timedelta(days=1), dt_time.min, tzinfo=timezone.utc
        )
        seconds_until_midnight = max(1, int((tomorrow - now).total_seconds()))
        return now, seconds_until_midnight

    async def get_usage(self, user_id: str, session: AsyncSession) -> int:
        now, seconds_until_midnight = self._utc_now_and_ttl()
        today_str = now.strftime("%Y-%m-%d")
        cache_key = cache_config.KEY_TTS_USAGE.format(user_id=user_id, date=today_str)

        try:
            val = await cache_service.get(cache_key)
            if val is not None:
                return int(val)
        except Exception as exc:
            logger.warning(
                "Failed to get TTS usage from Redis for %s: %s", user_id, exc
            )

        usage_repo = UserTtsUsageRepository(session)
        current_usage = await usage_repo.get_usage(user_id, usage_date=now.date())

        try:
            await cache_service.set(
                cache_key, current_usage, ttl=seconds_until_midnight
            )
        except Exception as exc:
            logger.warning(
                "Failed to backfill Redis TTS usage for %s: %s", user_id, exc
            )

        return current_usage

    async def increment_usage(self, user: User, session: AsyncSession) -> int:
        role_val = getattr(user.role, "value", str(user.role))
        if role_val == UserRole.ADMIN or user.role == UserRole.ADMIN:
            return 0

        now, seconds_until_midnight = self._utc_now_and_ttl()

        usage_repo = UserTtsUsageRepository(session)
        new_count_db = await usage_repo.increment_usage(user.id, usage_date=now.date())

        today_str = now.strftime("%Y-%m-%d")
        cache_key = cache_config.KEY_TTS_USAGE.format(user_id=user.id, date=today_str)
        full_cache_key = f"{settings.redis_cache_key_prefix}{cache_key}"
        try:
            client = await cache_service.get_client()
            if client:
                await client.eval(
                    INCR_EXPIRE_LUA, 1, full_cache_key, seconds_until_midnight
                )
        except Exception as exc:
            logger.warning(
                "Failed to increment TTS usage in Redis for %s: %s", user.id, exc
            )

        log_json(
            logger,
            logging.INFO,
            "TTS usage incremented",
            user_id=user.id,
            new_count=new_count_db,
        )
        return new_count_db

    async def get_user_usage_status(self, user: User, session: AsyncSession) -> dict:
        limit = await self.get_limit_for_role(user.role, session)
        current_usage = await self.get_usage(user.id, session)

        return {
            "usage": current_usage,
            "limit": limit,
            "has_reached_limit": limit is not None and current_usage >= limit,
        }


tts_limit_service = TtsLimitService()
