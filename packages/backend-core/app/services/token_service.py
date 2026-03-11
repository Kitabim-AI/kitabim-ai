"""Refresh token service for session management."""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional


from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.refresh_tokens import RefreshTokensRepository
from app.db.models import RefreshToken

from app.core.config import settings

logger = logging.getLogger(__name__)

def hash_token(token: str) -> str:
    """
    Hash a token for secure storage.
    
    Args:
        token: The token to hash.
        
    Returns:
        SHA-256 hash of the token.
    """
    return hashlib.sha256(token.encode()).hexdigest()


async def store_refresh_token(
    session: AsyncSession,
    user_id: str,
    jti: str,
    token: str,
    device_info: Optional[str] = None,
) -> None:
    """Store a refresh token in the database."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    
    RefreshTokensRepository(session)
    token_obj = RefreshToken(
        user_id=user_id,
        jti=jti,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=expires_at,
        revoked=False,
        device_info=device_info,
    )
    session.add(token_obj)
    await session.flush()
    logger.debug(f"Stored refresh token for user {user_id}, jti={jti}")


async def validate_refresh_token(session: AsyncSession, jti: str, token: str) -> Optional[str]:
    """Validate a refresh token and return the user ID."""
    token_hash = hash_token(token)
    repo = RefreshTokensRepository(session)
    
    token_doc = await repo.find_valid(jti, token_hash)
    if not token_doc:
        logger.warning(f"Refresh token not found or revoked: jti={jti}")
        return None
    
    # Check expiration
    if token_doc.expires_at and token_doc.expires_at < datetime.now(timezone.utc):
        logger.warning(f"Refresh token expired: jti={jti}")
        return None
    
    return str(token_doc.user_id)


async def revoke_refresh_token(session: AsyncSession, jti: str) -> bool:
    """Revoke a single refresh token."""
    repo = RefreshTokensRepository(session)
    return await repo.revoke_by_jti(jti)


async def revoke_all_user_tokens(session: AsyncSession, user_id: str) -> int:
    """Revoke all refresh tokens for a user (logout everywhere)."""
    repo = RefreshTokensRepository(session)
    return await repo.revoke_all_for_user(user_id)


async def cleanup_expired_tokens(session: AsyncSession) -> int:
    """Clean up expired and revoked tokens."""
    repo = RefreshTokensRepository(session)
    return await repo.delete_expired_or_revoked()
