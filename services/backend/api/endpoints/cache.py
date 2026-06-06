from __future__ import annotations
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.services.cache_service import cache_service
from auth.dependencies import get_current_user_optional, security
from fastapi.security import HTTPAuthorizationCredentials
from app.db.session import get_session

logger = logging.getLogger("app.api.cache")
router = APIRouter()

async def verify_operator_access(
    x_operator_token: Optional[str] = Header(None, alias="X-Operator-Token"),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_session),
) -> bool:
    """Verifies that the request either has a valid operator token or is authenticated as an admin."""
    # 1. Check if token matches settings.operator_token
    if settings.operator_token and x_operator_token == settings.operator_token:
        return True

    # 2. Or check if the user is an admin
    try:
        user = await get_current_user_optional(credentials, db)
        if user and user.role == "admin":
            return True
    except Exception:
        pass

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient permissions. A valid operator token or admin session is required."
    )

@router.post("/invalidate")
async def invalidate_cache(
    authorized: bool = Depends(verify_operator_access)
):
    """
    Operator-triggered cache invalidation endpoint.
    Flushes Redis caching patterns, bumps versions, and instructs all instances
    to clear their local in-process LRU caches immediately.
    """
    logger.info("Operator triggered global cache invalidation")
    
    # 1. Bump namespace versions to invalidate aggregated keys
    await cache_service.bump_namespace_version("books:list")
    await cache_service.bump_namespace_version("category")
    
    # 2. Delete Redis pattern caches (excluding configuration/chat usage to avoid data loss)
    await cache_service.delete_pattern("book:*")
    await cache_service.delete_pattern("books:list:*")
    await cache_service.delete_pattern("category:*")
    await cache_service.delete_pattern("rag:search:*")
    await cache_service.delete_pattern("rag:summary_search:*")
    await cache_service.delete_pattern("proverb:*")
    await cache_service.delete_pattern("stats:*")
    
    # 3. Publish global local-cache eviction message to all processes
    await cache_service.publish_invalidation("user_invalidation", "__ALL__")
    
    return {
        "status": "success",
        "message": "Global cache invalidation triggered successfully"
    }
