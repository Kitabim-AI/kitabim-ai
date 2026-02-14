"""User service for database operations."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.models.user import User, UserRole, UserCreate

logger = logging.getLogger(__name__)


async def get_user_by_id(db, user_id: str) -> Optional[User]:
    """
    Fetch a user from the database by ID.
    """
    if db is None:
        logger.error("Database not initialized")
        return None
    
    user_doc = await db.users.find_one({"id": user_id})
    if not user_doc:
        return None
    
    return _doc_to_user(user_doc)


async def get_user_by_email(db, email: str) -> Optional[User]:
    """
    Fetch a user from the database by email.
    """
    if db is None:
        logger.error("Database not initialized")
        return None
    
    user_doc = await db.users.find_one({"email": email.lower()})
    if not user_doc:
        return None
    
    return _doc_to_user(user_doc)


async def get_user_by_provider(db, provider: str, provider_id: str) -> Optional[User]:
    """
    Fetch a user by OAuth provider and provider-specific ID.
    """
    if db is None:
        logger.error("Database not initialized")
        return None
    
    user_doc = await db.users.find_one({
        "provider": provider,
        "provider_id": provider_id,
    })
    if not user_doc:
        return None
    
    return _doc_to_user(user_doc)


async def create_user(
    db,
    email: str,
    display_name: str,
    provider: str,
    provider_id: str,
    role: UserRole = UserRole.READER,
    avatar_url: Optional[str] = None,
) -> User:
    """
    Create a new user in the database.
    """
    if db is None:
        raise ValueError("Database not initialized")
    
    now = datetime.now(timezone.utc)
    user_id = str(uuid.uuid4())
    
    user_doc = {
        "id": user_id,
        "email": email.lower(),
        "display_name": display_name,
        "avatar_url": avatar_url,
        "role": role.value,
        "provider": provider,
        "provider_id": provider_id,
        "created_at": now,
        "updated_at": now,
        "last_login_at": now,
        "is_active": True,
    }
    
    await db.users.insert_one(user_doc)
    logger.info(f"Created new user: {user_id} ({email}) with role {role.value}")
    
    return _doc_to_user(user_doc)


async def update_user_login(db, user_id: str, avatar_url: Optional[str] = None) -> None:
    """
    Update user's last login time and optionally their avatar.
    """
    if db is None:
        return
    
    now = datetime.now(timezone.utc)
    update_data = {
        "last_login_at": now,
        "updated_at": now,
    }
    
    if avatar_url:
        update_data["avatar_url"] = avatar_url
    
    await db.users.update_one(
        {"id": user_id},
        {"$set": update_data}
    )


async def update_user_role(db, user_id: str, new_role: UserRole) -> Optional[User]:
    """
    Update a user's role.
    """
    if db is None:
        return None
    
    now = datetime.now(timezone.utc)
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"role": new_role.value, "updated_at": now}}
    )
    
    if result.modified_count == 0:
        return None
    
    logger.info(f"Updated user {user_id} role to {new_role.value}")
    return await get_user_by_id(db, user_id)


async def update_user_status(db, user_id: str, is_active: bool) -> Optional[User]:
    """
    Enable or disable a user account.
    """
    if db is None:
        return None
    
    now = datetime.now(timezone.utc)
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"is_active": is_active, "updated_at": now}}
    )
    
    if result.modified_count == 0:
        return None
    
    logger.info(f"Set user {user_id} active={is_active}")
    return await get_user_by_id(db, user_id)


async def list_users(db, page: int = 1, page_size: int = 20, filter_dict: dict = None) -> tuple[list[User], int]:
    """
    List users with pagination and filtering.
    """
    if db is None:
        return [], 0
    
    skip = (page - 1) * page_size
    query = filter_dict or {}
    
    total = await db.users.count_documents(query)
    cursor = db.users.find(query).skip(skip).limit(page_size).sort("created_at", -1)

    docs = await cursor.to_list(page_size)
    users = [_doc_to_user(doc) for doc in docs]

    return users, total


def _doc_to_user(doc: dict) -> User:
    """Convert a MongoDB document to a User object."""
    try:
        # Handle both snake_case and camelCase for compatibility during migration
        display_name = doc.get("display_name") or doc.get("displayName") or ""
        provider_id = doc.get("provider_id") or doc.get("providerId") or ""
        role_val = doc.get("role")
        
        return User(
            id=str(doc["id"]),
            email=doc["email"],
            display_name=display_name,
            avatar_url=doc.get("avatar_url") or doc.get("avatarUrl"),
            role=UserRole(role_val) if role_val else UserRole.READER,
            provider=doc.get("provider", "google"),
            provider_id=provider_id,
            created_at=doc.get("created_at") or doc.get("createdAt") or datetime.now(timezone.utc),
            updated_at=doc.get("updated_at") or doc.get("updatedAt") or datetime.now(timezone.utc),
            last_login_at=doc.get("last_login_at") or doc.get("lastLoginAt"),
            is_active=doc.get("is_active", True),
        )
    except KeyError as e:
        logger.error(f"Failed to convert doc to User: {e}. Keys present: {list(doc.keys())}")
        raise
