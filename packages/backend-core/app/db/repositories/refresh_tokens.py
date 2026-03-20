from __future__ import annotations

from typing import Optional
from uuid import UUID
from datetime import datetime

from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RefreshToken
from app.db.repositories.base import BaseRepository


class RefreshTokensRepository(BaseRepository[RefreshToken]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, RefreshToken)

    async def get_by_jti(self, jti: str | UUID) -> Optional[RefreshToken]:
        stmt = select(RefreshToken).where(RefreshToken.jti == jti)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_valid(self, jti: str | UUID, token_hash: str) -> Optional[RefreshToken]:
        stmt = select(RefreshToken).where(
            and_(
                RefreshToken.jti == jti,
                RefreshToken.token_hash == token_hash,
                not RefreshToken.revoked
            )
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke_by_jti(self, jti: str | UUID) -> bool:
        stmt = (
            update(RefreshToken)
            .where(RefreshToken.jti == jti)
            .values(revoked=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def revoke_all_for_user(self, user_id: str | UUID) -> int:
        stmt = (
            update(RefreshToken)
            .where(and_(RefreshToken.user_id == user_id, not RefreshToken.revoked))
            .values(revoked=True)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_expired_or_revoked(self) -> int:
        from datetime import timezone
        now = datetime.now(timezone.utc)
        stmt = delete(RefreshToken).where(
            or_(
                RefreshToken.expires_at < now,
                RefreshToken.revoked
            )
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
