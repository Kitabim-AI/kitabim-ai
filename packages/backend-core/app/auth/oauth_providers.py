"""OAuth provider implementations for external authentication."""

from __future__ import annotations

import base64
import logging
import secrets
import hashlib
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Google OAuth endpoints
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"


@dataclass
class OAuthState:
    """OAuth state for CSRF protection, nonce validation, and PKCE support."""
    state: str
    nonce: str
    code_verifier: Optional[str] = None  # For PKCE (Twitter)

    @classmethod
    def generate(cls, use_pkce: bool = False) -> "OAuthState":
        """
        Generate a new random state and nonce, with optional PKCE support.

        Args:
            use_pkce: If True, also generate a code_verifier for PKCE flow (required for Twitter)

        Returns:
            OAuthState instance with state, nonce, and optionally code_verifier
        """
        oauth_state = cls(
            state=secrets.token_urlsafe(32),
            nonce=secrets.token_urlsafe(32),
        )
        if use_pkce:
            oauth_state.code_verifier = secrets.token_urlsafe(32)
        return oauth_state

    def get_code_challenge(self) -> Optional[str]:
        """
        Generate PKCE code_challenge from code_verifier (SHA-256 base64url).

        Returns:
            Base64url-encoded SHA-256 hash of code_verifier, or None if no verifier
        """
        if not self.code_verifier:
            return None
        digest = hashlib.sha256(self.code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')

    def to_cookie_value(self) -> str:
        """
        Encode state, nonce, and optional code_verifier for cookie storage.

        Returns:
            Colon-separated string with state:nonce or state:nonce:code_verifier
        """
        parts = [self.state, self.nonce]
        if self.code_verifier:
            parts.append(self.code_verifier)
        return ":".join(parts)

    @classmethod
    def from_cookie_value(cls, value: str) -> Optional["OAuthState"]:
        """
        Decode state, nonce, and optional code_verifier from cookie value.

        Args:
            value: Colon-separated cookie value

        Returns:
            OAuthState instance or None if invalid format
        """
        try:
            parts = value.split(":")
            if len(parts) < 2:
                return None
            return cls(
                state=parts[0],
                nonce=parts[1],
                code_verifier=parts[2] if len(parts) > 2 else None
            )
        except Exception:
            return None


@dataclass
class GoogleUserInfo:
    """User information from Google OAuth."""
    id: str
    email: str
    verified_email: bool
    name: str
    picture: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None


def get_google_auth_url(state: str, nonce: str) -> str:
    """
    Generate Google OAuth authorization URL.
    
    Args:
        state: Random state for CSRF protection.
        nonce: Random nonce for ID token validation.
        
    Returns:
        Full authorization URL to redirect user to.
    """
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",  # Always show consent screen to get refresh token
        "state": state,
        "nonce": nonce,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


async def exchange_code_for_tokens(code: str) -> dict:
    """
    Exchange authorization code for access and ID tokens.
    
    Args:
        code: Authorization code from OAuth callback.
        
    Returns:
        Token response containing access_token, id_token, refresh_token, etc.
        
    Raises:
        httpx.HTTPStatusError: If token exchange fails.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        return response.json()


async def get_google_user_info(access_token: str) -> GoogleUserInfo:
    """
    Fetch user profile from Google using access token.
    
    Args:
        access_token: Valid Google access token.
        
    Returns:
        GoogleUserInfo with user's profile data.
        
    Raises:
        httpx.HTTPStatusError: If user info fetch fails.
        ValueError: If response is missing required fields.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        
        if response.status_code != 200:
            logger.error(f"User info fetch failed: {response.status_code} - {response.text}")
            response.raise_for_status()
        
        data = response.json()
        
        # Validate required fields
        if not data.get("id") or not data.get("email"):
            raise ValueError("Missing required user info fields from Google")
        
        return GoogleUserInfo(
            id=data["id"],
            email=data["email"],
            verified_email=data.get("verified_email", False),
            name=data.get("name", data["email"].split("@")[0]),
            picture=data.get("picture"),
            given_name=data.get("given_name"),
            family_name=data.get("family_name"),
        )


def validate_oauth_config() -> bool:
    """
    Check if Google OAuth is properly configured.
    
    Returns:
        True if all required settings are present.
    """
    if not settings.google_client_id:
        logger.warning("GOOGLE_CLIENT_ID not configured")
        return False
    if not settings.google_client_secret:
        logger.warning("GOOGLE_CLIENT_SECRET not configured")
        return False
    return True


def get_admin_emails_list() -> list[str]:
    """
    Get list of admin emails from configuration.
    
    Returns:
        List of email addresses that should be auto-promoted to admin.
    """
    if not settings.admin_emails:
        return []
    return [email.strip().lower() for email in settings.admin_emails.split(",") if email.strip()]


def is_admin_email(email: str) -> bool:
    """
    Check if an email should be auto-promoted to admin.
    
    Args:
        email: Email address to check.
        
    Returns:
        True if email is in the admin emails list.
    """
    admin_emails = get_admin_emails_list()
    return email.lower() in admin_emails
