"""Google OAuth 2.0 provider implementation."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from .base import OAuthProvider, ProviderUserInfo

logger = logging.getLogger(__name__)


class GoogleOAuthProvider(OAuthProvider):
    """Google OAuth 2.0 provider implementation."""

    # Google OAuth endpoints
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    @property
    def name(self) -> str:
        """Provider name identifier."""
        return "google"

    def validate_config(self) -> bool:
        """
        Check if Google OAuth is properly configured.

        Returns:
            True if client_id and client_secret are set.
        """
        if not settings.google_client_id:
            logger.warning("GOOGLE_CLIENT_ID not configured")
            return False
        if not settings.google_client_secret:
            logger.warning("GOOGLE_CLIENT_SECRET not configured")
            return False
        return True

    def get_auth_url(self, state: str, nonce: str) -> str:
        """
        Generate Google OAuth authorization URL.

        Args:
            state: Random state for CSRF protection
            nonce: Random nonce for ID token validation

        Returns:
            Full authorization URL to redirect user to
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
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, code_verifier: Optional[str] = None) -> dict:
        """
        Exchange authorization code for access and ID tokens.

        Args:
            code: Authorization code from OAuth callback
            code_verifier: Not used for Google (PKCE not required)

        Returns:
            Token response containing access_token, id_token, refresh_token, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
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
                logger.error(f"Google token exchange failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            return response.json()

    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Fetch user profile from Google using access token.

        Args:
            access_token: Valid Google access token

        Returns:
            ProviderUserInfo with user's profile data

        Raises:
            httpx.HTTPStatusError: If user info fetch fails
            ValueError: If response is missing required fields
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(f"Google user info fetch failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()

            # Validate required fields
            if not data.get("id") or not data.get("email"):
                raise ValueError("Missing required user info fields from Google")

            return ProviderUserInfo(
                provider_id=data["id"],
                email=data["email"],
                email_verified=data.get("verified_email", False),
                name=data.get("name", data["email"].split("@")[0]),
                picture=data.get("picture"),
                first_name=data.get("given_name"),
                last_name=data.get("family_name"),
            )
