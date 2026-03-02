"""User service for database operations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple

from app.models.user import User, UserRole
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.users import UsersRepository
from app.db.models import User as UserDB

logger = logging.getLogger(__name__)


async def get_user_by_id(session: AsyncSession, user_id: str) -> Optional[User]:
    """Fetch a user from the database by ID."""
    repo = UsersRepository(session)
    user_obj = await repo.get(user_id)
    if not user_obj:
        return None
    return _model_to_user(user_obj)


async def get_user_by_email(session: AsyncSession, email: str) -> Optional[User]:
    """Fetch a user from the database by email."""
    repo = UsersRepository(session)
    user_obj = await repo.find_by_email(email)
    if not user_obj:
        return None
    return _model_to_user(user_obj)


async def get_user_by_provider(session: AsyncSession, provider: str, provider_id: str) -> Optional[User]:
    """Fetch a user by OAuth provider and provider-specific ID."""
    repo = UsersRepository(session)
    user_obj = await repo.find_by_provider(provider, provider_id)
    if not user_obj:
        return None
    return _model_to_user(user_obj)


async def create_user(
    session: AsyncSession,
    email: str,
    display_name: str,
    provider: str,
    provider_id: str,
    role: UserRole = UserRole.READER,
    avatar_url: Optional[str] = None,
) -> User:
    """Create a new user in the database."""
    now = datetime.now(timezone.utc)
    user_id = str(uuid.uuid4())
    
    user_obj = UserDB(
        id=user_id,
        email=email.lower(),
        display_name=display_name,
        avatar_url=avatar_url,
        role=role.value,
        provider=provider,
        provider_id=provider_id,
        created_at=now,
        updated_at=now,
        last_login_at=now,
        is_active=True,
    )
    
    session.add(user_obj)
    await session.flush()
    logger.info(f"Created new user: {user_id} ({email}) with role {role.value}")
    
    return _model_to_user(user_obj)


async def update_user_login(session: AsyncSession, user_id: str, avatar_url: Optional[str] = None) -> None:
    """Update user's last login time and optionally their avatar."""
    repo = UsersRepository(session)
    update_data = {
        "last_login_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    if avatar_url:
        update_data["avatar_url"] = avatar_url
    
    try:
        await repo.update_one(user_id, **update_data)
        await session.flush()
    except Exception as e:
        logger.error(f"Failed to update user login: {e}")


async def update_user_role(session: AsyncSession, user_id: str, new_role: UserRole) -> Optional[User]:
    """Update a user's role."""
    repo = UsersRepository(session)
    from uuid import UUID
    success = await repo.update_one(user_id, role=new_role.value, updated_at=datetime.now(timezone.utc))
    if not success:
        return None
    
    await session.flush()
    user_obj = await repo.get(user_id)
    return _model_to_user(user_obj) if user_obj else None


async def update_user_status(session: AsyncSession, user_id: str, is_active: bool) -> Optional[User]:
    """Enable or disable a user account."""
    repo = UsersRepository(session)
    success = await repo.update_one(user_id, is_active=is_active, updated_at=datetime.now(timezone.utc))
    if not success:
        return None
    
    await session.flush()
    user_obj = await repo.get(user_id)
    return _model_to_user(user_obj) if user_obj else None


async def list_users(session: AsyncSession, page: int = 1, page_size: int = 20, filter_dict: dict = None) -> Tuple[List[User], int]:
    """List users with pagination and filtering."""
    repo = UsersRepository(session)
    skip = (page - 1) * page_size

    role = filter_dict.get("role") if filter_dict else None
    is_active = filter_dict.get("is_active") if filter_dict else None
    search = filter_dict.get("search") if filter_dict else None

    users_objs = await repo.find_many(role=role, is_active=is_active, search=search, skip=skip, limit=page_size)
    total = await repo.count_by_role(role=role, is_active=is_active, search=search)

    users = [_model_to_user(obj) for obj in users_objs]
    return users, total


def _model_to_user(user_obj: UserDB) -> User:
    """Convert a SQLAlchemy User model to a Pydantic User schema."""
    return User(
        id=str(user_obj.id),
        email=user_obj.email,
        display_name=user_obj.display_name,
        avatar_url=user_obj.avatar_url,
        role=UserRole(user_obj.role) if user_obj.role else UserRole.READER,
        provider=user_obj.provider or "google",
        provider_id=user_obj.provider_id or "",
        created_at=user_obj.created_at or datetime.now(timezone.utc),
        updated_at=user_obj.updated_at or datetime.now(timezone.utc),
        last_login_at=user_obj.last_login_at,
        is_active=user_obj.is_active,
    )
