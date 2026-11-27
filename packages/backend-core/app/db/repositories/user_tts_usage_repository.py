"""User daily TTS usage repository with SQLAlchemy."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UserTtsUsage
from app.db.repositories.base_repository import BaseRepository


class UserTtsUsageRepository(BaseRepository[UserTtsUsage]):
    """Repository for tracking daily uncached TTS synthesis usage per user."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, UserTtsUsage)

    async def get_usage(self, user_id: str, usage_date: Optional[date] = None) -> int:
        if usage_date is None:
            usage_date = date.today()

        stmt = select(UserTtsUsage.count).where(
            and_(
                UserTtsUsage.user_id == user_id,
                UserTtsUsage.usage_date == usage_date,
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def increment_usage(
        self, user_id: str, usage_date: Optional[date] = None
    ) -> int:
        if usage_date is None:
            usage_date = date.today()

        stmt = select(UserTtsUsage).where(
            and_(
                UserTtsUsage.user_id == user_id,
                UserTtsUsage.usage_date == usage_date,
            )
        )
        result = await self.session.execute(stmt)
        usage = result.scalar_one_or_none()

        if usage:
            usage.count += 1
            await self.session.commit()
            return usage.count

        new_usage = UserTtsUsage(user_id=user_id, usage_date=usage_date, count=1)
        self.session.add(new_usage)
        await self.session.commit()
        return 1
