"""User chat usage repository with SQLAlchemy"""
from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import UserChatUsage
from app.db.repositories.base import BaseRepository


class UserChatUsageRepository(BaseRepository[UserChatUsage]):
    """Repository for tracking user chat usage"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserChatUsage)

    async def get_usage(self, user_id: str, usage_date: Optional[date] = None) -> int:
        """Get chat usage count for a user on a specific date (defaults to today)"""
        if usage_date is None:
            usage_date = date.today()

        stmt = select(UserChatUsage.count).where(
            and_(
                UserChatUsage.user_id == user_id,
                UserChatUsage.usage_date == usage_date
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def increment_usage(self, user_id: str, usage_date: Optional[date] = None) -> int:
        """
        Increment chat usage count for a user.
        Returns the new count.
        """
        if usage_date is None:
            usage_date = date.today()

        # Find existing record
        stmt = select(UserChatUsage).where(
            and_(
                UserChatUsage.user_id == user_id,
                UserChatUsage.usage_date == usage_date
            )
        )
        result = await self.session.execute(stmt)
        usage = result.scalar_one_or_none()

        if usage:
            usage.count += 1
            await self.session.commit()
            return usage.count
        
        # Create new record
        new_usage = UserChatUsage(user_id=user_id, usage_date=usage_date, count=1)
        self.session.add(new_usage)
        await self.session.commit()
        return 1


def get_user_chat_usage_repository(session: AsyncSession) -> UserChatUsageRepository:
    """Factory function for dependency injection"""
    return UserChatUsageRepository(session)
