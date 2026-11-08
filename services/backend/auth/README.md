# Backend Authentication

## Overview
Authentication and authorization subsystem providing JWT lifecycle management (access, refresh, download tokens), FastAPI security dependencies with multi-tier caching (in-process LRU, Redis, and PostgreSQL), role-based access control (RBAC), and OAuth 2.0 state/provider handlers.

## Interface
- `[__init__.py:create_access_token]`: `(user: User) -> str`
- `[__init__.py:create_refresh_token]`: `(user: User) -> tuple[str, str]`
- `[__init__.py:create_download_token]`: `(user: User, book_id: str, expire_seconds: int = 120) -> str`
- `[__init__.py:decode_jwt]`: `(token: str, expected_type: str = 'access') -> dict[str, Any]`
- `[__init__.py:get_current_user]`: `async (user: Optional[User]) -> User`
- `[__init__.py:get_current_user_optional]`: `async (credentials, db) -> Optional[User]`
- `[__init__.py:require_role]`: `(*allowed_roles: UserRole) -> Callable`
- `[__init__.py:require_admin]`: Dependency requiring `UserRole.ADMIN`
- `[__init__.py:require_editor]`: Dependency requiring `UserRole.ADMIN` or `UserRole.EDITOR`
- `[__init__.py:require_reader]`: Dependency requiring `UserRole.ADMIN`, `UserRole.EDITOR`, or `UserRole.READER`
- `[dependencies.py:user_lru_cache]`: In-process `LocalLRUCache` instance (maxsize=1000, TTL `settings.cache_ttl_user_profile`)
- `[dependencies.py:security]`: `HTTPBearer(auto_error=False)` allowing guest and authenticated access
- `[dependencies.py:get_current_user_optional]`: Resolves authenticated `User` across LRU, Redis, and DB, or `None` for unauthenticated guests
- `[dependencies.py:get_current_user]`: Enforces authentication and raises HTTP 401 if unauthenticated
- `[jwt_handler.py:TokenError]`: Base exception for JWT operations
- `[jwt_handler.py:TokenExpiredError]`: Exception raised on token expiration
- `[jwt_handler.py:TokenInvalidError]`: Exception raised on signature or token structure mismatch
- `[jwt_handler.py:create_access_token]`: Signs short-lived access JWT (expiry `settings.jwt_access_token_expire_minutes`)
- `[jwt_handler.py:create_refresh_token]`: Signs long-lived refresh JWT (expiry `settings.jwt_refresh_token_expire_days`) returning `(token, jti)`
- `[jwt_handler.py:create_download_token]`: Signs short-lived (default 120s) file download JWT scoped to `book_id`
- `[jwt_handler.py:decode_jwt]`: Validates JWT signature with active key identifier (`kid`) and enforces matching `type` claim
- `[jwt_handler.py:validate_jwt_secret]`: Validates configured JWT secrets meet minimum 256-bit (32 character) length
- `[oauth_providers.py:OAuthState]`: Dataclass for CSRF state, nonce, PKCE `code_verifier`, and base64url-encoded `redirect_uri`
- `[oauth_providers.py:GoogleUserInfo]`: Dataclass containing parsed Google profile fields
- `[oauth_providers.py:get_google_auth_url]`: Generates Google OAuth consent screen URL
- `[oauth_providers.py:exchange_code_for_tokens]`: Exchanges OAuth authorization code with Google token endpoint
- `[oauth_providers.py:get_google_user_info]`: Retrieves verified profile from Google UserInfo endpoint
- `[oauth_providers.py:validate_oauth_config]`: Validates Google client ID and secret configuration
- `[oauth_providers.py:get_admin_emails_list]`: Parses comma-separated `settings.admin_emails`
- `[oauth_providers.py:create_oauth_state_token]`: Encodes `OAuthState` into a 10-minute signed JWT
- `[oauth_providers.py:decode_oauth_state_token]`: Decodes and verifies state JWT, returning `None` if invalid
- `[oauth_providers.py:is_admin_email]`: Checks if an email is configured for automatic admin promotion
- Providers: [./providers/README.md](./providers/README.md) - Concrete OAuth 2.0 implementations for Google, Facebook, Twitter, and Instagram.

## Invariants
- `get_current_user_optional` checks 3 distinct storage tiers in order: in-process `user_lru_cache`, Redis cache (`cache_config.KEY_USER`), and PostgreSQL (`get_user_by_id`). Disabled accounts (`is_active=False`) immediately raise HTTP 401 (`[dependencies.py:get_current_user_optional]`).
- `create_access_token`, `create_refresh_token`, and `create_download_token` sign tokens using `settings.jwt_active_kid` from `settings.jwt_secrets` (raises `RuntimeError` if missing) and set specific `type` payload claims (`'access'`, `'refresh'`, `'download'`) (`[jwt_handler.py:create_access_token]`, `[jwt_handler.py:create_refresh_token]`, `[jwt_handler.py:create_download_token]`).
- `decode_jwt` validates token type against `expected_type` and raises `TokenExpiredError` on expiration or `TokenInvalidError` on signature or payload mismatch (`[jwt_handler.py:decode_jwt]`).
- `validate_jwt_secret` requires secret keys to be at least 32 characters (256 bits), raising `ValueError` on validation failure (`[jwt_handler.py:validate_jwt_secret]`).
- `OAuthState.from_cookie_value` and `decode_oauth_state_token` catch errors and return `None` rather than raising uncaught exceptions on malformed or expired tokens (`[oauth_providers.py:OAuthState.from_cookie_value]`, `[oauth_providers.py:decode_oauth_state_token]`).

## Side Effects
- Queries and caches user profiles in Redis (`cache_config.KEY_USER`) and the local in-process `user_lru_cache` (`[dependencies.py:get_current_user_optional]`).
- Performs outbound HTTPS requests via `httpx.AsyncClient` to `oauth2.googleapis.com` and `www.googleapis.com` (`[oauth_providers.py:exchange_code_for_tokens]`, `[oauth_providers.py:get_google_user_info]`).
- Emits structured error and warning logs on JWT signature failures and missing OAuth credentials (`[jwt_handler.py:decode_jwt]`, `[oauth_providers.py:validate_oauth_config]`).

## Verification
- Run: `pytest services/backend/tests`
