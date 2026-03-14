"""
User management API endpoints.

Admin-only endpoints for managing users and their roles.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from auth.dependencies import require_admin, get_current_user
from app.models.user import User, UserRole, UserPublic
from app.services.user_service import (
    get_user_by_id,
    list_users,
    update_user_role,
    update_user_status,
)
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session
from app.core.i18n import t
from app.services.cache_service import cache_service
from app.core import cache_config


router = APIRouter()
logger = logging.getLogger(__name__)


class UserRoleUpdate(BaseModel):
    """Request body for updating a user's role."""
    role: UserRole


class UserStatusUpdate(BaseModel):
    """Request body for updating a user's active status."""
    is_active: bool


class PaginatedUsers(BaseModel):
    """Response model for paginated user list."""
    users: List[UserPublic]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=PaginatedUsers)
async def list_all_users(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    role: Optional[str] = Query(None, description="Filter by role"),
    status: Optional[str] = Query(None, description="Filter by status (active/inactive)"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    List all users with pagination.

    Admin only. Returns paginated list of users with optional role and status filtering.
    """
    # Build filter
    filter_dict = {}
    if role:
        try:
            filter_dict["role"] = UserRole(role)
        except ValueError:
            raise HTTPException(status_code=400, detail=t("errors.invalid_role", role=role))

    if status:
        if status == "active":
            filter_dict["is_active"] = True
        elif status == "inactive":
            filter_dict["is_active"] = False
        else:
            raise HTTPException(status_code=400, detail=t("errors.invalid_status", status=status))

    if search:
        filter_dict["search"] = search

    users, total = await list_users(session, page, page_size, filter_dict)

    return {
        "users": [UserPublic.from_user(u) for u in users],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{user_id}", response_model=UserPublic)
async def get_user(
    user_id: str,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Get a specific user by ID.
    
    Admin only.
    """
    user = await get_user_by_id(session, user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail=t("errors.user_not_found"))
    
    return UserPublic.from_user(user)


@router.patch("/{user_id}/role", response_model=UserPublic)
async def change_user_role(
    user_id: str,
    role_update: UserRoleUpdate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Change a user's role.
    
    Admin only. Cannot change own role to prevent lockout.
    """
    # Prevent admin from changing their own role
    if user_id == current_user.id:
        raise HTTPException(
            status_code=400,
            detail=t("errors.cannot_change_own_role")
        )
    
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=t("errors.user_not_found"))
    
    updated_user = await update_user_role(session, user_id, role_update.role)
    if not updated_user:
        raise HTTPException(status_code=500, detail=t("errors.failed_update_role"))
    
    await session.commit()
    await cache_service.delete(cache_config.KEY_USER.format(user_id=user_id))
    
    logger.info(

        f"Admin {current_user.email} changed role of {updated_user.email} "
        f"from {user.role.value} to {role_update.role.value}"
    )
    
    return UserPublic.from_user(updated_user)


@router.patch("/{user_id}/status", response_model=UserPublic)
async def change_user_status(
    user_id: str,
    status_update: UserStatusUpdate,
    current_user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Enable or disable a user account.
    
    Admin only. Cannot disable own account.
    """
    # Prevent admin from disabling themselves
    if user_id == current_user.id and not status_update.is_active:
        raise HTTPException(
            status_code=400,
            detail=t("errors.cannot_disable_self")
        )
    
    user = await get_user_by_id(session, user_id)
    if not user:
        raise HTTPException(status_code=404, detail=t("errors.user_not_found"))
    
    updated_user = await update_user_status(session, user_id, status_update.is_active)
    if not updated_user:
        raise HTTPException(status_code=500, detail=t("errors.failed_update_status"))
    
    await session.commit()
    await cache_service.delete(cache_config.KEY_USER.format(user_id=user_id))
    
    action = "enabled" if status_update.is_active else "disabled"

    logger.info(f"Admin {current_user.email} {action} user {updated_user.email}")
    
    return UserPublic.from_user(updated_user)


@router.get("/me/profile", response_model=UserPublic)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
):
    """
    Get the current user's profile.
    
    Available to all authenticated users.
    """
    return UserPublic.from_user(current_user)
