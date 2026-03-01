from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.repositories.user_chat_usage import UserChatUsageRepository
from app.models.user import UserRole, User
from app.utils.observability import log_json

logger = logging.getLogger("app.chat_limit")

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

    async def is_within_limit(self, user: User, session: AsyncSession) -> bool:
        """Check if user has reached their daily chat limit without incrementing."""
        limit = await self.get_limit_for_role(user.role, session)
        if limit is None:
            return True
            
        usage_repo = UserChatUsageRepository(session)
        current_usage = await usage_repo.get_usage(user.id)
        
        return current_usage < limit

    async def increment_usage(self, user: User, session: AsyncSession) -> int:
        """Increment daily chat usage for a user."""
        log_json(logger, logging.DEBUG, "Incrementing usage attempt", user_id=user.id, role=user.role)
        if user.role == UserRole.ADMIN:
            log_json(logger, logging.DEBUG, "Skipping usage increment for admin", user_id=user.id)
            return 0
            
        usage_repo = UserChatUsageRepository(session)
        new_count = await usage_repo.increment_usage(user.id)
        log_json(logger, logging.INFO, "Usage incremented", user_id=user.id, new_count=new_count)
        return new_count

    async def get_user_usage_status(self, user: User, session: AsyncSession) -> dict:
        """Get current usage and limit status for a user."""
        limit = await self.get_limit_for_role(user.role, session)
        usage_repo = UserChatUsageRepository(session)
        current_usage = await usage_repo.get_usage(user.id)
        
        return {
            "usage": current_usage,
            "limit": limit,
            "has_reached_limit": limit is not None and current_usage >= limit
        }

chat_limit_service = ChatLimitService()
