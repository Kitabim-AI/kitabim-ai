"""Twitter OAuth 2.0 provider implementation."""

from __future__ import annotations

import base64
import logging
from typing import Optional
from urllib.parse import urlencode

import httpx

from app.core.config import settings
from .base import OAuthProvider, ProviderUserInfo

logger = logging.getLogger(__name__)


class TwitterOAuthProvider(OAuthProvider):
    """Twitter OAuth 2.0 provider implementation with PKCE support."""

    # Twitter OAuth 2.0 endpoints
    AUTH_URL = "https://twitter.com/i/oauth2/authorize"
    TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
    USER_INFO_URL = "https://api.twitter.com/2/users/me"

    @property
    def name(self) -> str:
        """Provider name identifier."""
        return "twitter"

    def validate_config(self) -> bool:
        """
        Check if Twitter OAuth is properly configured.

        Returns:
            True if client_id and client_secret are set.
        """
        if not settings.twitter_client_id:
            logger.warning("TWITTER_CLIENT_ID not configured")
            return False
        if not settings.twitter_client_secret:
            logger.warning("TWITTER_CLIENT_SECRET not configured")
            return False
        return True

    def get_auth_url(self, state: str, nonce: str, code_challenge: Optional[str] = None) -> str:
        """
        Generate Twitter OAuth 2.0 authorization URL with PKCE.

        Args:
            state: Random state for CSRF protection
            nonce: Random nonce (not used by Twitter but kept for consistency)
            code_challenge: PKCE code challenge (SHA-256 hash of code_verifier)

        Returns:
            Full authorization URL to redirect user to
        """
        if not code_challenge:
            raise ValueError("Twitter OAuth requires PKCE code_challenge")

        params = {
            "client_id": settings.twitter_client_id,
            "redirect_uri": settings.twitter_redirect_uri,
            "response_type": "code",
            "scope": "tweet.read users.read offline.access",  # offline.access for refresh token
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code_for_tokens(self, code: str, code_verifier: Optional[str] = None) -> dict:
        """
        Exchange authorization code for access token using PKCE.

        Args:
            code: Authorization code from OAuth callback
            code_verifier: PKCE code verifier (required for Twitter)

        Returns:
            Token response containing access_token and refresh_token

        Raises:
            httpx.HTTPStatusError: If token exchange fails
            ValueError: If code_verifier is missing
        """
        if not code_verifier:
            raise ValueError("Twitter OAuth requires PKCE code_verifier")

        # Twitter requires Basic Auth with client_id:client_secret
        credentials = f"{settings.twitter_client_id}:{settings.twitter_client_secret}"
        b64_credentials = base64.b64encode(credentials.encode()).decode()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.twitter_redirect_uri,
                    "code_verifier": code_verifier,
                },
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Authorization": f"Basic {b64_credentials}",
                },
            )

            if response.status_code != 200:
                logger.error(f"Twitter token exchange failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            return response.json()

    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Fetch user profile from Twitter using access token.

        Args:
            access_token: Valid Twitter access token

        Returns:
            ProviderUserInfo with user's profile data

        Raises:
            httpx.HTTPStatusError: If user info fetch fails
            ValueError: If response is missing required fields

        Note:
            Twitter's email access is restricted for new apps. If email is not available,
            we'll use the username as fallback and generate a placeholder email.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.USER_INFO_URL,
                params={"user.fields": "profile_image_url,name,username"},
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(f"Twitter user info fetch failed: {response.status_code} - {response.text}")
                response.raise_for_status()

            json_response = response.json()
            data = json_response.get("data", {})

            # Validate required fields
            if not data.get("id"):
                raise ValueError("Missing required user info fields from Twitter (id)")

            # Twitter email access is restricted - use username as fallback
            username = data.get("username", "")
            email = f"{username}@twitter.placeholder" if username else f"{data['id']}@twitter.placeholder"

            logger.info(f"Twitter user {data['id']} authenticated (email not available, using placeholder)")

            return ProviderUserInfo(
                provider_id=data["id"],
                email=email,
                email_verified=False,  # We can't verify placeholder emails
                name=data.get("name", username),
                picture=data.get("profile_image_url"),
                first_name=None,  # Twitter doesn't provide first/last name separately
                last_name=None,
            )
