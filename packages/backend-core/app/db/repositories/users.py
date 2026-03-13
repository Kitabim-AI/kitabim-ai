"""Users repository for authentication and user management"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User, RefreshToken
from app.db.repositories.base import BaseRepository


class UsersRepository(BaseRepository[User]):
    """Repository for users with OAuth provider lookups"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, User)

    async def find_by_email(self, email: str) -> Optional[User]:
        """Find user by email (case-insensitive)"""
        result = await self.session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def find_by_provider(self, provider: str, provider_id: str) -> Optional[User]:
        """Find user by OAuth provider and provider ID"""
        result = await self.session.execute(
            select(User).where(
                User.provider == provider,
                User.provider_id == provider_id
            )
        )
        return result.scalar_one_or_none()

    async def find_many(
        self,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[User]:
        """Find users with optional filtering by role and active status"""
        stmt = select(User)

        conditions = []
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)

        if search:
            search_pattern = f"%{search.lower()}%"
            from sqlalchemy import or_
            conditions.append(or_(
                func.lower(User.email).like(search_pattern),
                func.lower(User.display_name).like(search_pattern)
            ))

        if conditions:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*conditions))

        stmt = stmt.order_by(User.created_at.desc()).offset(skip).limit(limit)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_last_login(self, user_id: UUID, ip_address: Optional[str] = None) -> None:
        """Update user's last login timestamp and IP address"""
        updates = {"last_login_at": datetime.now(timezone.utc)}
        if ip_address:
            updates["last_login_ip"] = ip_address
        await self.update_one(user_id, **updates)

    async def count_by_role(self, role: Optional[str] = None, is_active: Optional[bool] = None, search: Optional[str] = None) -> int:
        """Count users, optionally filtered by role, active status, and search query"""
        stmt = select(func.count()).select_from(User)
        conditions = []
        if role:
            conditions.append(User.role == role)
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if search:
            search_pattern = f"%{search.lower()}%"
            from sqlalchemy import or_
            conditions.append(or_(
                func.lower(User.email).like(search_pattern),
                func.lower(User.display_name).like(search_pattern)
            ))

        if conditions:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*conditions))

        result = await self.session.execute(stmt)
        return result.scalar_one()


class RefreshTokensRepository(BaseRepository[RefreshToken]):
    """Repository for refresh tokens"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RefreshToken)

    async def find_by_jti(self, jti: UUID) -> Optional[RefreshToken]:
        """Find refresh token by JTI"""
        return await self.get(jti)

    async def find_by_user(self, user_id: UUID) -> List[RefreshToken]:
        """Find all refresh tokens for a user"""
        stmt = select(RefreshToken).where(RefreshToken.user_id == user_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_by_user(self, user_id: UUID) -> int:
        """Delete all refresh tokens for a user (logout from all devices)"""
        from sqlalchemy import delete
        stmt = delete(RefreshToken).where(RefreshToken.user_id == user_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_expired(self) -> int:
        """Delete all expired refresh tokens"""
        from sqlalchemy import delete
        stmt = delete(RefreshToken).where(RefreshToken.expires_at < datetime.now(timezone.utc))
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount


def get_users_repository(session: AsyncSession) -> UsersRepository:
    """Factory function for dependency injection"""
    return UsersRepository(session)


def get_refresh_tokens_repository(session: AsyncSession) -> RefreshTokensRepository:
    """Factory function for dependency injection"""
    return RefreshTokensRepository(session)
