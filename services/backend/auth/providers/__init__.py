"""OAuth provider registry and factory."""

from __future__ import annotations

from typing import Type

from .base import OAuthProvider, ProviderUserInfo
from .google import GoogleOAuthProvider
from .facebook import FacebookOAuthProvider
from .twitter import TwitterOAuthProvider

# Export base classes and user info
__all__ = [
    "OAuthProvider",
    "ProviderUserInfo",
    "GoogleOAuthProvider",
    "FacebookOAuthProvider",
    "TwitterOAuthProvider",
    "get_provider",
    "get_available_providers",
    "OAUTH_PROVIDERS",
]

# Registry of all available OAuth providers
OAUTH_PROVIDERS: dict[str, Type[OAuthProvider]] = {
    "google": GoogleOAuthProvider,
    "facebook": FacebookOAuthProvider,
    "twitter": TwitterOAuthProvider,
}


def get_provider(provider_name: str) -> OAuthProvider:
    """
    Factory function to get an OAuth provider instance.

    Args:
        provider_name: Name of the provider (e.g., 'google', 'facebook', 'twitter')

    Returns:
        Instance of the requested OAuth provider

    Raises:
        ValueError: If the provider name is not recognized

    Example:
        >>> provider = get_provider("google")
        >>> auth_url = provider.get_auth_url(state="abc", nonce="xyz")
    """
    provider_class = OAUTH_PROVIDERS.get(provider_name.lower())
    if not provider_class:
        raise ValueError(f"Unknown OAuth provider: {provider_name}")
    return provider_class()


def get_available_providers() -> list[str]:
    """
    Get list of properly configured OAuth provider names.

    Only returns providers that have valid client_id and client_secret configured.

    Returns:
        List of provider names that are ready to use

    Example:
        >>> providers = get_available_providers()
        >>> print(providers)
        ['google', 'facebook']
    """
    available = []
    for provider_name, provider_class in OAUTH_PROVIDERS.items():
        try:
            provider_instance = provider_class()
            if provider_instance.validate_config():
                available.append(provider_name)
        except Exception:
            # Skip providers that fail to instantiate
            continue
    return available
