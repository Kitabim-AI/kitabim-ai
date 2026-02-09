"""User models and schemas for authentication."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional, List
from pydantic import BaseModel, Field


class UserRole(str, Enum):
    """User role enumeration for RBAC."""
    ADMIN = "admin"
    EDITOR = "editor"
    READER = "reader"


class UserBase(BaseModel):
    """Base user fields shared across schemas."""
    email: str
    display_name: str
    avatar_url: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a new user (internal use)."""
    provider: str
    provider_id: str
    role: UserRole = UserRole.READER


class User(UserBase):
    """Full user model as stored in database."""
    id: str
    role: UserRole
    provider: str
    provider_id: str
    created_at: datetime
    updated_at: datetime
    last_login_at: Optional[datetime] = None
    is_active: bool = True

    class Config:
        from_attributes = True


class UserPublic(BaseModel):
    """Public user info returned to clients."""
    id: str
    email: str
    display_name: str
    avatar_url: Optional[str] = None
    role: UserRole
    is_active: bool = True
    created_at: Optional[datetime] = None
    
    @classmethod
    def from_user(cls, user: "User") -> "UserPublic":
        """Create a UserPublic from a User model."""
        return cls(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            avatar_url=user.avatar_url,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )


class UserInToken(BaseModel):
    """User info embedded in JWT token."""
    sub: str  # user id
    email: str
    role: str
    display_name: str
    jti: str
    type: str  # "access" or "refresh"


class UserUpdate(BaseModel):
    """Schema for updating user details (admin use)."""
    display_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None


class UserList(BaseModel):
    """Paginated list of users for admin."""
    users: List[UserPublic]
    total: int
    page: int
    page_size: int
