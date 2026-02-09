"""Refresh token service for session management."""

from __future__ import annotations

import logging
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional

from app.db.mongodb import db_manager
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
    user_id: str,
    jti: str,
    token: str,
    device_info: Optional[str] = None,
) -> None:
    """
    Store a refresh token in the database.
    
    Args:
        user_id: User's unique identifier.
        jti: Token's unique identifier (from JWT).
        token: The raw refresh token (will be hashed).
        device_info: Optional device/browser info.
    """
    db = db_manager.db
    if db is None:
        logger.error("Database not initialized")
        return
    
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    
    token_doc = {
        "user_id": user_id,
        "jti": jti,
        "token_hash": hash_token(token),
        "created_at": now,
        "expires_at": expires_at,
        "revoked": False,
        "device_info": device_info,
    }
    
    await db.refresh_tokens.insert_one(token_doc)
    logger.debug(f"Stored refresh token for user {user_id}, jti={jti}")


async def validate_refresh_token(jti: str, token: str) -> Optional[str]:
    """
    Validate a refresh token and return the user ID.
    
    Args:
        jti: Token's unique identifier.
        token: The raw refresh token.
        
    Returns:
        User ID if token is valid, None otherwise.
    """
    db = db_manager.db
    if db is None:
        return None
    
    token_hash = hash_token(token)
    
    token_doc = await db.refresh_tokens.find_one({
        "jti": jti,
        "token_hash": token_hash,
        "revoked": False,
    })
    
    if not token_doc:
        logger.warning(f"Refresh token not found or revoked: jti={jti}")
        return None
    
    # Check expiration (also handled by TTL index, but double-check)
    if token_doc.get("expires_at") and token_doc["expires_at"] < datetime.now(timezone.utc):
        logger.warning(f"Refresh token expired: jti={jti}")
        return None
    
    return token_doc["user_id"]


async def revoke_refresh_token(jti: str) -> bool:
    """
    Revoke a single refresh token.
    
    Args:
        jti: Token's unique identifier.
        
    Returns:
        True if token was revoked, False if not found.
    """
    db = db_manager.db
    if db is None:
        return False
    
    result = await db.refresh_tokens.update_one(
        {"jti": jti},
        {"$set": {"revoked": True}}
    )
    
    if result.modified_count > 0:
        logger.info(f"Revoked refresh token: jti={jti}")
        return True
    
    return False


async def revoke_all_user_tokens(user_id: str) -> int:
    """
    Revoke all refresh tokens for a user (logout everywhere).
    
    Args:
        user_id: User's unique identifier.
        
    Returns:
        Number of tokens revoked.
    """
    db = db_manager.db
    if db is None:
        return 0
    
    result = await db.refresh_tokens.update_many(
        {"user_id": user_id, "revoked": False},
        {"$set": {"revoked": True}}
    )
    
    if result.modified_count > 0:
        logger.info(f"Revoked {result.modified_count} refresh tokens for user {user_id}")
    
    return result.modified_count


async def cleanup_expired_tokens() -> int:
    """
    Clean up expired and revoked tokens.
    
    Note: The TTL index should handle this automatically,
    but this can be called manually for cleanup.
    
    Returns:
        Number of tokens deleted.
    """
    db = db_manager.db
    if db is None:
        return 0
    
    now = datetime.now(timezone.utc)
    
    result = await db.refresh_tokens.delete_many({
        "$or": [
            {"expires_at": {"$lt": now}},
            {"revoked": True},
        ]
    })
    
    if result.deleted_count > 0:
        logger.info(f"Cleaned up {result.deleted_count} expired/revoked tokens")
    
    return result.deleted_count
