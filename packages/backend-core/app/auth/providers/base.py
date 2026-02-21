"""Base OAuth provider class for extensible authentication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class ProviderUserInfo:
    """Standardized user information across all OAuth providers."""

    provider_id: str  # Unique ID from the provider (e.g., Google ID, Facebook ID)
    email: str
    email_verified: bool
    name: str
    picture: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None


class OAuthProvider(ABC):
    """
    Abstract base class for OAuth 2.0 providers.

    Each provider (Google, Facebook, Twitter, etc.) should inherit from this class
    and implement the required methods for their specific OAuth flow.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Provider name identifier (e.g., 'google', 'facebook', 'twitter').

        This should be lowercase and match the URL path segment used in endpoints.
        """
        pass

    @abstractmethod
    def validate_config(self) -> bool:
        """
        Check if the OAuth provider is properly configured.

        Returns:
            True if client_id and client_secret are set, False otherwise.
        """
        pass

    @abstractmethod
    def get_auth_url(self, state: str, nonce: str) -> str:
        """
        Generate the authorization URL to redirect the user to the provider's login page.

        Args:
            state: Random CSRF protection token
            nonce: Random value for token validation

        Returns:
            Full authorization URL with all required parameters
        """
        pass

    @abstractmethod
    async def exchange_code_for_tokens(self, code: str, code_verifier: Optional[str] = None) -> dict:
        """
        Exchange the authorization code for access and refresh tokens.

        Args:
            code: Authorization code received from OAuth callback
            code_verifier: Optional PKCE code verifier (for Twitter)

        Returns:
            Dictionary containing access_token, refresh_token, id_token, etc.

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> ProviderUserInfo:
        """
        Fetch user profile information from the provider using the access token.

        Args:
            access_token: Valid OAuth access token

        Returns:
            ProviderUserInfo with standardized user data

        Raises:
            httpx.HTTPStatusError: If user info fetch fails
            ValueError: If response is missing required fields
        """
        pass
