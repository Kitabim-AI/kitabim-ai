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
    active_secret = settings.jwt_secrets.get(settings.jwt_active_kid, settings.jwt_secret_key)
    return jwt.encode(
        payload, 
        active_secret, 
        algorithm=settings.jwt_algorithm, 
        headers={"kid": settings.jwt_active_kid}
    )


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
    active_secret = settings.jwt_secrets.get(settings.jwt_active_kid, settings.jwt_secret_key)
    token = jwt.encode(
        payload, 
        active_secret, 
        algorithm=settings.jwt_algorithm,
        headers={"kid": settings.jwt_active_kid}
    )
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
        header = jwt.get_unverified_header(token)
        kid = header.get("kid", "v1")
    except JWTError as e:
        raise TokenInvalidError(f"Invalid token header: {e}")

    secret = settings.jwt_secrets.get(kid)
    if not secret:
        # Fallback to default secret key if key ID is not found in secrets map
        logger.warning(f"JWT header specified unknown kid '{kid}'. Trying default fallback secret.")
        secret = settings.jwt_secret_key

    try:
        payload = jwt.decode(
            token,
            secret,
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
    Validate that all configured JWT secret keys are configured properly.
    Should be called at application startup.
    
    Raises:
        ValueError: If any key is missing or too short.
    """
    secrets_map = settings.jwt_secrets
    if not secrets_map:
        raise ValueError("No JWT secret keys configured")
        
    for kid, secret in secrets_map.items():
        if not secret:
            raise ValueError(f"JWT secret for kid '{kid}' is empty")
        if len(secret) < 32:
            raise ValueError(f"JWT secret for kid '{kid}' must be at least 32 characters (256 bits)")
            
    logger.info(f"JWT secrets validated successfully (loaded {len(secrets_map)} key(s))")
