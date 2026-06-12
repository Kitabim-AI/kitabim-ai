"""Instagram OAuth 2.0 provider implementation."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from .base_provider import OAuthProvider, ProviderUserInfo

logger = logging.getLogger(__name__)


class InstagramOAuthProvider(OAuthProvider):
    """Instagram OAuth 2.0 provider implementation."""

    AUTH_URL = "https://api.instagram.com/oauth/authorize"
    TOKEN_URL = "https://api.instagram.com/oauth/access_token"
    USER_INFO_URL = "https://graph.instagram.com/me"

    @property
    def name(self) -> str:
        """Provider name identifier."""
        return "instagram"

    def validate_config(self) -> bool:
        """
        Check if Instagram OAuth is properly configured.

        Returns:
            True if client_id and client_secret are set.
        """
        if not settings.instagram_client_id:
            logger.warning("INSTAGRAM_CLIENT_ID not configured")
            return False
        if not settings.instagram_client_secret:
            logger.warning("INSTAGRAM_CLIENT_SECRET not configured")
            return False
        return True

    def get_auth_url(self, state: str, nonce: str) -> str:
        """
        Generate Instagram OAuth authorization URL.

        Args:
            state: Random state for CSRF protection
            nonce: Random nonce (not used by Instagram but kept for consistency)

        Returns:
            Full authorization URL to redirect user to
        """
        params = {
            "client_id": settings.instagram_client_id,
            "redirect_uri": settings.instagram_redirect_uri,
            "response_type": "code",
            "scope": "user_profile",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(
        self, code: str, code_verifier: Optional[str] = None
    ) -> dict:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback
            code_verifier: Not used for Instagram

        Returns:
            Token response containing access_token

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.instagram_client_id,
                    "client_secret": settings.instagram_client_secret,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.instagram_redirect_uri,
                    "code": code,
                },
            )

            if response.status_code != 200:
                logger.error(
                    f"Instagram token exchange failed: {response.status_code} - {response.text}"
                )
                response.raise_for_status()

            return response.json()

    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Fetch user profile from Instagram using access token.

        Args:
            access_token: Valid Instagram access token

        Returns:
            ProviderUserInfo with user's profile data

        Raises:
            httpx.HTTPStatusError: If user info fetch fails
            ValueError: If response is missing required fields
        """
        # Instagram Basic Display API requires explicit field selection
        fields = "id,username"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.USER_INFO_URL,
                params={"fields": fields, "access_token": access_token},
            )

            if response.status_code != 200:
                logger.error(
                    f"Instagram user info fetch failed: {response.status_code} - {response.text}"
                )
                response.raise_for_status()

            data = response.json()

            # Validate required fields
            if not data.get("id"):
                raise ValueError(
                    "Missing required user info fields from Instagram (id)"
                )

            # Instagram does not provide email, generate a placeholder
            username = data.get("username", "instagram_user")
            email = f"{data['id']}@instagram.placeholder"

            return ProviderUserInfo(
                provider_id=data["id"],
                email=email,
                email_verified=False,
                name=username,
                picture=None,
                first_name=None,
                last_name=None,
            )
