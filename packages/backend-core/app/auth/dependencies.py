"""FastAPI security dependencies for authentication and authorization."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.jwt_handler import decode_jwt, TokenExpiredError, TokenInvalidError
from app.models.user import User, UserRole
from app.services.user_service import get_user_by_id

logger = logging.getLogger(__name__)

# HTTPBearer with auto_error=False to allow guest access
security = HTTPBearer(auto_error=False)


from app.db.mongodb import get_db

async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db = Depends(get_db),
) -> Optional[User]:
    """
    Get the current user if a valid token is provided.
    
    Returns None only when no token is provided (guest access).
    Raises HTTPException if token is provided but invalid.
    
    Args:
        credentials: Optional Bearer token credentials.
        db: Database session.
        
    Returns:
        User object if authenticated, None for guests.
        
    Raises:
        HTTPException 401: If token is provided but invalid/expired.
    """
    if not credentials:
        return None
    
    try:
        payload = decode_jwt(credentials.credentials, expected_type="access")
        user = await get_user_by_id(db, payload["sub"])
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is disabled",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return user
        
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(
    user: Optional[User] = Depends(get_current_user_optional),
) -> User:
    """
    Require an authenticated user.
    
    Args:
        user: User from get_current_user_optional dependency.
        
    Returns:
        The authenticated User.
        
    Raises:
        HTTPException 401: If no user is authenticated.
    """
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_role(*allowed_roles: UserRole):
    """
    Dependency factory for role-based access control.
    
    Creates a dependency that requires the authenticated user
    to have one of the specified roles.
    
    Args:
        *allowed_roles: One or more UserRole values that are permitted.
        
    Returns:
        A FastAPI dependency function.
        
    Example:
        @router.delete("/books/{id}", dependencies=[Depends(require_role(UserRole.ADMIN))])
        async def delete_book(id: str):
            ...
    """
    async def role_checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required roles: {[r.value for r in allowed_roles]}",
            )
        return user
    
    return role_checker


# Convenience dependencies for common role requirements
require_admin = require_role(UserRole.ADMIN)
require_editor = require_role(UserRole.ADMIN, UserRole.EDITOR)
require_reader = require_role(UserRole.ADMIN, UserRole.EDITOR, UserRole.READER)
