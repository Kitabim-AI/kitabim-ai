"""Facebook OAuth 2.0 provider implementation."""

from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from .base import OAuthProvider, ProviderUserInfo

logger = logging.getLogger(__name__)


class FacebookOAuthProvider(OAuthProvider):
    """Facebook OAuth 2.0 provider implementation."""

    # Facebook OAuth endpoints (using Graph API v18.0)
    AUTH_URL = "https://www.facebook.com/v18.0/dialog/oauth"
    TOKEN_URL = "https://graph.facebook.com/v18.0/oauth/access_token"
    USER_INFO_URL = "https://graph.facebook.com/me"

    @property
    def name(self) -> str:
        """Provider name identifier."""
        return "facebook"

    def validate_config(self) -> bool:
        """
        Check if Facebook OAuth is properly configured.

        Returns:
            True if client_id and client_secret are set.
        """
        if not settings.facebook_client_id:
            logger.warning("FACEBOOK_CLIENT_ID not configured")
            return False
        if not settings.facebook_client_secret:
            logger.warning("FACEBOOK_CLIENT_SECRET not configured")
            return False
        return True

    def get_auth_url(self, state: str, nonce: str) -> str:
        """
        Generate Facebook OAuth authorization URL.

        Args:
            state: Random state for CSRF protection
            nonce: Random nonce (not used by Facebook but kept for consistency)

        Returns:
            Full authorization URL to redirect user to
        """
        params = {
            "client_id": settings.facebook_client_id,
            "redirect_uri": settings.facebook_redirect_uri,
            "response_type": "code",
            "scope": "email,public_profile",
            "state": state,
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, code_verifier: Optional[str] = None) -> dict:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback
            code_verifier: Not used for Facebook (PKCE not required)

        Returns:
            Token response containing access_token

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": settings.facebook_client_id,
                    "client_secret": settings.facebook_client_secret,
                    "code": code,
                    "redirect_uri": settings.facebook_redirect_uri,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                logger.error(f"Facebook token exchange failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            return response.json()

    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Fetch user profile from Facebook using access token.

        Args:
            access_token: Valid Facebook access token

        Returns:
            ProviderUserInfo with user's profile data

        Raises:
            httpx.HTTPStatusError: If user info fetch fails
            ValueError: If response is missing required fields
        """
        # Facebook requires explicit field selection
        fields = "id,email,name,picture,first_name,last_name"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.USER_INFO_URL,
                params={"fields": fields, "access_token": access_token},
            )

            if response.status_code != 200:
                logger.error(f"Facebook user info fetch failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            data = response.json()

            # Validate required fields
            if not data.get("id"):
                raise ValueError("Missing required user info fields from Facebook (id)")

            # Email may not be provided if user denied permission
            email = data.get("email")
            if not email:
                # Fallback: Use Facebook ID as placeholder
                logger.warning(f"Facebook user {data['id']} did not provide email")
                email = f"{data['id']}@facebook.placeholder"
                email_verified = False
            else:
                # Facebook emails are verified by default
                email_verified = True

            # Extract picture URL from nested structure
            picture_url = None
            if "picture" in data and isinstance(data["picture"], dict):
                picture_data = data["picture"].get("data", {})
                picture_url = picture_data.get("url")

            return ProviderUserInfo(
                provider_id=data["id"],
                email=email,
                email_verified=email_verified,
                name=data.get("name", email.split("@")[0]),
                picture=picture_url,
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
            )
