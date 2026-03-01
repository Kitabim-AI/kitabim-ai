"""JWT token creation and validation."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from jose import jwt, JWTError, ExpiredSignatureError

from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)


class TokenError(Exception):
    """Base exception for token-related errors."""
    pass


class TokenExpiredError(TokenError):
    """Raised when a token has expired."""
    pass


class TokenInvalidError(TokenError):
    """Raised when a token is invalid."""
    pass


def create_access_token(user: User) -> str:
    """
    Create a short-lived access token for API authentication.
    
    Args:
        user: The user to create a token for.
        
    Returns:
        Encoded JWT access token string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "email": user.email,
        "role": user.role.value if hasattr(user.role, 'value') else user.role,
        "display_name": user.display_name,
        "jti": str(uuid.uuid4()),
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user: User) -> tuple[str, str]:
    """
    Create a long-lived refresh token for session management.
    
    Args:
        user: The user to create a token for.
        
    Returns:
        Tuple of (encoded JWT refresh token string, jti for storage).
    """
    now = datetime.now(timezone.utc)
    jti = str(uuid.uuid4())
    payload = {
        "sub": user.id,
        "jti": jti,
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=settings.jwt_refresh_token_expire_days),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, jti


def decode_jwt(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token string to decode.
        expected_type: Expected token type ("access" or "refresh").
        
    Returns:
        Decoded token payload as a dictionary.
        
    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token is invalid or wrong type.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        
        # Validate token type
        if payload.get("type") != expected_type:
            raise TokenInvalidError(f"Expected {expected_type} token, got {payload.get('type')}")
        
        return payload
        
    except ExpiredSignatureError:
        raise TokenExpiredError("Token has expired")
    except JWTError as e:
        logger.warning(f"JWT decode error: {e}")
        raise TokenInvalidError(f"Invalid token: {e}")


def validate_jwt_secret() -> None:
    """
    Validate that JWT secret key is configured properly.
    Should be called at application startup.
    
    Raises:
        ValueError: If JWT_SECRET_KEY is missing or too short.
    """
    if not settings.jwt_secret_key:
        raise ValueError("JWT_SECRET_KEY environment variable is required")
    
    if len(settings.jwt_secret_key) < 32:
        raise ValueError("JWT_SECRET_KEY must be at least 32 characters (256 bits)")
    
    logger.info("JWT secret key validated successfully")
