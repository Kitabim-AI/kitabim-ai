from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.repositories.user_chat_usage import UserChatUsageRepository
from app.models.user import UserRole, User
from app.utils.observability import log_json

from app.services.cache_service import cache_service
from app.core import cache_config

logger = logging.getLogger("app.chat_limit")

# Lua script to increment counter and set expiry only if it's new
INCR_EXPIRE_LUA = """
local current = redis.call('INCR', KEYS[1])
if tonumber(current) == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

class ChatLimitService:
    async def get_limit_for_role(self, role: str, session: AsyncSession) -> Optional[int]:
        """
        Get chat message limit for a given role from system configuration.
        Returns None for Admin (no limit).
        """
        if role == UserRole.ADMIN:
            return None  # No limit
        
        repo = SystemConfigsRepository(session)
        limit_key = f"chat_limit_{role}"
        
        try:
            # Note: SystemConfigsRepository.get_value already uses cache_service
            limit_val = await repo.get_value(limit_key)
            if limit_val is not None:
                return int(limit_val)
        except Exception as exc:
            log_json(logger, logging.WARNING, "Failed to fetch chat limit from DB", key=limit_key, error=str(exc))
        
        # Fallback to hardcoded defaults if not in DB or error
        if role == UserRole.EDITOR:
            return 100
        if role == UserRole.READER:
            return 20
        return 10  # Default for unknown roles

    async def _get_today_cache_key(self, user_id: str) -> str:
        """Generate a redis key for user's daily usage."""
        from datetime import datetime
        today_str = datetime.now().strftime("%Y-%m-%d")
        return cache_config.KEY_CHAT_USAGE.format(user_id=user_id, date=today_str)

    async def get_usage(self, user_id: str, session: AsyncSession) -> int:
        """Get current usage by checking Redis first, then falling back to DB."""
        cache_key = await self._get_today_cache_key(user_id)
        
        # 1. Try Redis
        try:
            val = await cache_service.get(cache_key)
            if val is not None:
                return int(val)
        except Exception as e:
            logger.warning(f"Failed to get usage from Redis for {user_id}: {e}")

        # 2. Fallback to DB
        usage_repo = UserChatUsageRepository(session)
        current_usage = await usage_repo.get_usage(user_id)
        
        # 3. Backfill Redis if missing
        try:
            # Use current day's remaining TTL (until midnight)
            from datetime import datetime, timedelta, time as dt_time
            now = datetime.now()
            tomorrow = datetime.combine(now.date() + timedelta(days=1), dt_time.min)
            seconds_until_midnight = int((tomorrow - now).total_seconds())
            
            await cache_service.set(cache_key, current_usage, ttl=seconds_until_midnight)
        except Exception as e:
             logger.warning(f"Failed to backfill Redis usage for {user_id}: {e}")

        return current_usage

    async def is_within_limit(self, user: User, session: AsyncSession) -> bool:
        """Check if user has reached their daily chat limit without incrementing."""
        limit = await self.get_limit_for_role(user.role, session)
        if limit is None:
            return True
            
        current_usage = await self.get_usage(user.id, session)
        return current_usage < limit

    async def increment_usage(self, user: User, session: AsyncSession) -> int:
        """Increment daily chat usage for a user in both Redis and DB."""
        log_json(logger, logging.DEBUG, "Incrementing usage attempt", user_id=user.id, role=user.role)
        if user.role == UserRole.ADMIN:
            log_json(logger, logging.DEBUG, "Skipping usage increment for admin", user_id=user.id)
            return 0
            
        # 1. Update DB (Durability)
        usage_repo = UserChatUsageRepository(session)
        new_count_db = await usage_repo.increment_usage(user.id)
        
        # 2. Update Redis (Speed)
        cache_key = await self._get_today_cache_key(user.id)
        try:
            # TTL until midnight
            from datetime import datetime, timedelta, time as dt_time
            now = datetime.now()
            tomorrow = datetime.combine(now.date() + timedelta(days=1), dt_time.min)
            seconds_until_midnight = int((tomorrow - now).total_seconds())
            
            # Use Lua script for atomic increment and expire
            client = await cache_service.get_client()
            if client:
                new_count_redis = await client.eval(INCR_EXPIRE_LUA, 1, cache_key, seconds_until_midnight)
                log_json(logger, logging.INFO, "Usage incremented in Redis", user_id=user.id, new_count=new_count_redis)
        except Exception as e:
            logger.warning(f"Failed to increment usage in Redis for {user.id}: {e}")

        log_json(logger, logging.INFO, "Usage incremented", user_id=user.id, new_count=new_count_db)
        return new_count_db

    async def get_user_usage_status(self, user: User, session: AsyncSession) -> dict:
        """Get current usage and limit status for a user."""
        limit = await self.get_limit_for_role(user.role, session)
        current_usage = await self.get_usage(user.id, session)
        
        return {
            "usage": current_usage,
            "limit": limit,
            "has_reached_limit": limit is not None and current_usage >= limit
        }


chat_limit_service = ChatLimitService()
