# OAuth Providers

## Overview
Concrete OAuth 2.0 provider implementations (`GoogleOAuthProvider`, `FacebookOAuthProvider`, `TwitterOAuthProvider`, and `InstagramOAuthProvider`) and abstract base interfaces used by the backend authentication service to build authorization URLs, exchange authorization codes for tokens, and fetch normalized user profile metadata.

## Interface
- `[__init__.py:OAUTH_PROVIDERS]`: `dict[str, Type[OAuthProvider]]` mapping `'google'`, `'facebook'`, and `'twitter'` to their provider classes.
- `[__init__.py:get_provider]`: `(provider_name: str) -> OAuthProvider` factory returning an instantiated provider by name.
- `[__init__.py:get_available_providers]`: `() -> list[str]` returning provider names with valid credentials configured.
- `[base_provider.py:ProviderUserInfo]`: Dataclass (`provider_id`, `email`, `email_verified`, `name`, `picture`, `first_name`, `last_name`).
- `[base_provider.py:OAuthProvider]`: Abstract base class declaring `name`, `validate_config()`, `get_auth_url(state: str, nonce: str) -> str`, `exchange_code_for_tokens(code: str, code_verifier: Optional[str] = None) -> dict`, and `get_user_info(access_token: str) -> ProviderUserInfo`.
- `[google_provider.py:GoogleOAuthProvider]`: Google OAuth 2.0 provider (`name='google'`).
- `[facebook_provider.py:FacebookOAuthProvider]`: Facebook Graph OAuth 2.0 provider (`name='facebook'`).
- `[twitter_provider.py:TwitterOAuthProvider]`: Twitter/X OAuth 2.0 provider with mandatory PKCE (`name='twitter'`).
- `[instagram_provider.py:InstagramOAuthProvider]`: Instagram OAuth 2.0 provider (`name='instagram'`; not registered in `[__init__.py:OAUTH_PROVIDERS]`).

## Invariants
- `get_provider` normalizes `provider_name.lower()` against `OAUTH_PROVIDERS` and raises `ValueError` if the provider is not registered (`[__init__.py:get_provider]`).
- `get_available_providers` only returns providers from `OAUTH_PROVIDERS` whose `validate_config()` returns `True` without raising an exception (`[__init__.py:get_available_providers]`).
- Each provider's `validate_config()` requires both its client ID and client secret to be truthy on `app.core.config.settings` (`[google_provider.py:GoogleOAuthProvider.validate_config]`, `[facebook_provider.py:FacebookOAuthProvider.validate_config]`, `[twitter_provider.py:TwitterOAuthProvider.validate_config]`, `[instagram_provider.py:InstagramOAuthProvider.validate_config]`).
- `GoogleOAuthProvider.exchange_code_for_tokens` and `GoogleOAuthProvider.get_user_info` retry up to 3 attempts with exponential backoff (`min=2`, `max=10`) on `httpx.TimeoutException`, `httpx.ConnectTimeout`, or `httpx.ReadTimeout`, and `get_user_info` raises `ValueError` if `id` or `email` is missing (`[google_provider.py:GoogleOAuthProvider.exchange_code_for_tokens]`, `[google_provider.py:GoogleOAuthProvider.get_user_info]`).
- `FacebookOAuthProvider.get_user_info` raises `ValueError` if `id` is missing; when `email` is absent, it synthesizes `{id}@facebook.placeholder` with `email_verified=False` (`[facebook_provider.py:FacebookOAuthProvider.get_user_info]`).
- `TwitterOAuthProvider.get_auth_url` requires `code_challenge` (`code_challenge_method='S256'`) and `exchange_code_for_tokens` requires `code_verifier`, raising `ValueError` if omitted; `get_user_info` always synthesizes `{username}@twitter.placeholder` or `{id}@twitter.placeholder` with `email_verified=False` (`[twitter_provider.py:TwitterOAuthProvider.get_auth_url]`, `[twitter_provider.py:TwitterOAuthProvider.exchange_code_for_tokens]`, `[twitter_provider.py:TwitterOAuthProvider.get_user_info]`).
- `InstagramOAuthProvider.get_user_info` raises `ValueError` if `id` is missing and always sets `email` to `{id}@instagram.placeholder` with `email_verified=False` (`[instagram_provider.py:InstagramOAuthProvider.get_user_info]`).

## Side Effects
- Makes outbound HTTPS requests via `httpx.AsyncClient` to Google (`oauth2.googleapis.com`, `www.googleapis.com`), Facebook (`graph.facebook.com`), Twitter/X (`api.twitter.com`), and Instagram (`api.instagram.com`, `graph.instagram.com`) token and userinfo endpoints (`[google_provider.py:GoogleOAuthProvider.exchange_code_for_tokens]`, `[facebook_provider.py:FacebookOAuthProvider.exchange_code_for_tokens]`, `[twitter_provider.py:TwitterOAuthProvider.exchange_code_for_tokens]`, `[instagram_provider.py:InstagramOAuthProvider.exchange_code_for_tokens]`).
- Reads OAuth credentials and redirect URIs from `app.core.config.settings` and emits structured warning/error logs when credentials are missing or upstream OAuth requests fail (`[google_provider.py:GoogleOAuthProvider.validate_config]`, `[facebook_provider.py:FacebookOAuthProvider.validate_config]`, `[twitter_provider.py:TwitterOAuthProvider.validate_config]`, `[instagram_provider.py:InstagramOAuthProvider.validate_config]`).

## Verification
- Run: `pytest services/backend/tests`
