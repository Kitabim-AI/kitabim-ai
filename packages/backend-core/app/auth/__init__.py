"""
Authentication and Authorization module for Kitabim.AI.

This module provides:
- JWT token creation and validation
- OAuth provider integrations (Google)
- FastAPI security dependencies
- Role-based access control
"""

from app.auth.jwt_handler import create_access_token, create_refresh_token, decode_jwt
from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    require_role,
    require_admin,
    require_editor,
    require_reader,
)

__all__ = [
    "create_access_token",
    "create_refresh_token",
    "decode_jwt",
    "get_current_user",
    "get_current_user_optional",
    "require_role",
    "require_admin",
    "require_editor",
    "require_reader",
]
