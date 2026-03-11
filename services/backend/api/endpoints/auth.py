"""Authentication API endpoints."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Response, Request, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_session

from auth.dependencies import get_current_user
from app.core.i18n import t
from auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_jwt,
    TokenExpiredError,
    TokenInvalidError,
)
from auth.oauth_providers import (
    OAuthState,
    is_admin_email,
    create_oauth_state_token,
    decode_oauth_state_token,
)
from auth.providers import (
    get_provider,
    get_available_providers,
)
from app.models.user import User, UserPublic, UserRole
from app.services.user_service import (
    get_user_by_provider,
    get_user_by_email,
    create_user,
    update_user_login,
)
from app.services.token_service import (
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
)
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Cookie settings
OAUTH_STATE_COOKIE = "kitabim_oauth_state"
REFRESH_TOKEN_COOKIE = "kitabim_refresh_token"


@router.get("/me", response_model=UserPublic)
async def get_current_user_profile(
    current_user: User = Depends(get_current_user),
) -> UserPublic:
    """
    Get the current authenticated user's profile.
    
    Returns:
        UserPublic: The authenticated user's public profile.
        
    Raises:
        HTTPException 401: If not authenticated.
    """
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        avatar_url=current_user.avatar_url,
        role=current_user.role,
    )


@router.get("/{provider}/login")
async def oauth_login(provider: str, response: Response, next: Optional[str] = None):
    """
    Initiate OAuth login flow for any provider.

    Supports: google, facebook, twitter (X)

    Generates authorization URL and sets state cookie for CSRF protection.

    Args:
        provider: OAuth provider name (google, facebook, twitter)

    Returns:
        Redirect to provider's authorization page.

    Raises:
        HTTPException 400: If provider is unknown
        HTTPException 503: If provider is not configured
    """
    try:
        oauth_provider = get_provider(provider)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported OAuth provider: {provider}"
        )

    if not oauth_provider.validate_config():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=t("errors.oauth_not_configured", provider=provider),
        )

    # Generate state and nonce for CSRF protection (with PKCE for Twitter)
    use_pkce = provider.lower() == "twitter"
    oauth_state = OAuthState.generate(use_pkce=use_pkce)
    if next:
        oauth_state.redirect_uri = next

    # Encode all state into a signed JWT passed as the OAuth `state` parameter.
    # No cookie is needed — the JWT is returned unchanged by Google in the callback.
    # This avoids iOS Safari ITP cookie issues entirely.
    state_jwt = create_oauth_state_token(oauth_state)

    # Build authorization URL (pass JWT as state instead of bare random token)
    if use_pkce and oauth_state.code_verifier:
        code_challenge = oauth_state.get_code_challenge()
        auth_url = oauth_provider.get_auth_url(
            state_jwt,
            oauth_state.nonce,
            code_challenge=code_challenge
        )
    else:
        auth_url = oauth_provider.get_auth_url(state_jwt, oauth_state.nonce)

    return RedirectResponse(url=auth_url)


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
):
    """
    Handle OAuth callback for any provider.

    Supports: google, facebook, twitter (X)

    Exchanges code for tokens, creates/updates user, and returns
    an HTML page that posts the access token to the opener window.

    Args:
        provider: OAuth provider name (google, facebook, twitter)

    Returns:
        HTML response with embedded JavaScript for popup communication
    """
    # Get provider instance
    try:
        oauth_provider = get_provider(provider)
    except ValueError:
        return _error_response(f"Unsupported OAuth provider: {provider}")

    # Handle OAuth errors
    if error:
        logger.warning(f"OAuth error from {provider}: {error}")
        return _error_response(t("errors.oauth_login_failed", provider=provider, error=error))

    if not code or not state:
        return _error_response(t("errors.missing_oauth_params"))

    # Validate state by decoding the signed JWT (no cookie needed).
    # The JWT contains state, nonce, code_verifier, and redirect_uri.
    saved_state = decode_oauth_state_token(state)
    if not saved_state:
        return _error_response(t("errors.invalid_oauth_state"))

    try:
        # Exchange code for tokens (with PKCE code_verifier for Twitter)
        token_response = await oauth_provider.exchange_code_for_tokens(
            code,
            code_verifier=saved_state.code_verifier
        )
        access_token = token_response.get("access_token")

        if not access_token:
            return _error_response(t("errors.no_access_token"))

        # Get user info from provider
        user_info = await oauth_provider.get_user_info(access_token)

        # Check if email is verified (skip for Twitter placeholder emails)
        if not user_info.email_verified and not user_info.email.endswith("@twitter.placeholder"):
            return _error_response(t("errors.email_not_verified"))

        # Check if user exists with this provider
        user = await get_user_by_provider(session, provider, user_info.provider_id)

        if not user:
            # Check if email exists with different provider (no auto-linking)
            if not user_info.email.endswith(("@twitter.placeholder", "@facebook.placeholder")):
                existing_user = await get_user_by_email(session, user_info.email)
                if existing_user:
                    return _error_response(
                        t("errors.email_already_exists")
                    )

            # Determine role based on admin emails
            role = UserRole.ADMIN if is_admin_email(user_info.email) else UserRole.READER

            # Create new user
            user = await create_user(
                session=session,
                email=user_info.email,
                display_name=user_info.name,
                provider=provider,
                provider_id=user_info.provider_id,
                role=role,
                avatar_url=user_info.picture,
            )
            logger.info(f"Created new user from {provider} OAuth: {user.id} ({user.email})")
        else:
            # Update last login and avatar
            await update_user_login(session, user.id, user_info.picture)
            logger.info(f"User logged in via {provider} OAuth: {user.id} ({user.email})")

        # Check if user is active
        if not user.is_active:
            return _error_response(t("errors.account_disabled"))

        # Generate tokens
        access_token = create_access_token(user)
        refresh_token, jti = create_refresh_token(user)

        # Store refresh token
        user_agent = request.headers.get("User-Agent", "unknown")
        await store_refresh_token(session, user.id, jti, refresh_token, user_agent[:200])

        # Commit changes
        await session.commit()

        # Mobile redirect flow: redirect back to app with token in URL
        if saved_state.redirect_uri:
            from urllib.parse import urlencode, urlparse
            parsed = urlparse(saved_state.redirect_uri)
            # Safety check: only allow same-host or relative redirects
            request_host = request.headers.get("host", "")
            if not parsed.netloc or parsed.netloc == request_host:
                callback_url = f"{saved_state.redirect_uri}?{urlencode({'access_token': access_token})}"
                redirect_response = RedirectResponse(url=callback_url)
                redirect_response.set_cookie(
                    key=REFRESH_TOKEN_COOKIE,
                    value=refresh_token,
                    max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
                    httponly=True,
                    secure=settings.cookie_secure,
                    samesite="lax",
                )
                redirect_response.delete_cookie(OAUTH_STATE_COOKIE)
                return redirect_response

        # Popup flow: return HTML that posts token to opener
        return _success_response(access_token, refresh_token)
        
    except Exception as e:
        logger.exception(f"OAuth callback error: {e}")
        return _error_response(t("errors.google_login_failed", error=str(e)))


@router.post("/refresh")
async def refresh_access_token(
    request: Request,
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_session),
):
    """
    Refresh an access token using a valid refresh token.
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=t("errors.refresh_token_required"),
        )
    
    try:
        # Decode refresh token
        payload = decode_jwt(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        user_id = payload.get("sub")
        
        if not jti or not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=t("errors.invalid_refresh_token"),
            )
        
        # Validate token is not revoked
        validated_user_id = await validate_refresh_token(session, jti, refresh_token)
        if not validated_user_id or validated_user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=t("errors.refresh_token_revoked"),
            )
        
        # Get fresh user data
        from app.services.user_service import get_user_by_id
        user = await get_user_by_id(session, user_id)
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=t("errors.user_not_found_inactive"),
            )
        
        # Generate new access token
        new_access_token = create_access_token(user)
        
        return {"access_token": new_access_token, "token_type": "bearer"}
        
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=t("errors.refresh_token_expired"),
        )
    except TokenInvalidError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/logout")
async def logout(
    response: Response,
    request: Request,
    current_user: User = Depends(get_current_user),
    refresh_token: Optional[str] = Cookie(None, alias=REFRESH_TOKEN_COOKIE),
    session: AsyncSession = Depends(get_session),
):
    """
    Logout the current user.
    """
    if refresh_token:
        try:
            payload = decode_jwt(refresh_token, expected_type="refresh")
            jti = payload.get("jti")
            if jti:
                await revoke_refresh_token(session, jti)
                await session.commit()
        except (TokenExpiredError, TokenInvalidError):
            # Token invalid, but still clear cookies
            pass
    
    # Clear cookies
    response.delete_cookie(REFRESH_TOKEN_COOKIE)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    
    return {"message": t("messages.logged_out")}


@router.get("/health")
async def auth_health():
    """
    Health check endpoint for auth service.

    Returns:
        dict: Status with list of configured OAuth providers.
    """
    available_providers = get_available_providers()

    return {
        "status": "ok",
        "service": "auth",
        "oauth_providers": available_providers,
        "google_oauth": "google" in available_providers,
        "facebook_oauth": "facebook" in available_providers,
        "twitter_oauth": "twitter" in available_providers,
    }


def _success_response(access_token: str, refresh_token: str) -> HTMLResponse:
    """
    Generate HTML response for successful OAuth that posts token to opener.
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login Successful</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
            }}
            .spinner {{
                border: 4px solid rgba(255,255,255,0.3);
                border-top: 4px solid white;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 1rem auto;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="spinner"></div>
            <h2>Login Successful!</h2>
            <p>Redirecting...</p>
        </div>
        <script>
            const accessToken = "{access_token}";
            
            function notifyAndClose() {{
                console.log('[Kitabim Auth] Attempting to notify opener...');
                
                // Try to post to opener (popup flow)
                if (window.opener && !window.opener.closed) {{
                    try {{
                        window.opener.postMessage({{
                            type: 'OAUTH_SUCCESS',
                            accessToken: accessToken
                        }}, '*');
                        
                        console.log('[Kitabim Auth] Message posted, closing in 500ms...');
                        setTimeout(() => window.close(), 500);
                        return true;
                    }} catch (err) {{
                        console.error('[Kitabim Auth] Failed to post message:', err);
                    }}
                }}
                return false;
            }}

            // Run immediately
            const notified = notifyAndClose();
            
            if (!notified) {{
                console.log('[Kitabim Auth] Opener not found, storing token and redirecting to app');
                // Store token in localStorage then redirect back to the app.
                // window.close() is blocked by Safari when not opened via window.open(),
                // so we navigate back to the app root instead.
                localStorage.setItem('kitabim_access_token', accessToken);

                // Update UI while redirecting
                const container = document.querySelector('.container');
                const p = container.querySelector('p');
                const h2 = container.querySelector('h2');

                h2.textContent = 'Login Successful!';
                p.textContent = 'Redirecting you back to the app\u2026';

                // Redirect — useAuth will pick up the token from localStorage on load
                setTimeout(() => window.location.replace('/'), 800);

                // Fallback button in case redirect is blocked
                const btn = document.createElement('button');
                btn.textContent = 'Continue to App';
                btn.style.cssText = 'margin-top: 1.5rem; padding: 0.75rem 2rem; background: white; color: #667eea; border: none; border-radius: 12px; cursor: pointer; font-weight: bold; font-size: 1rem; box-shadow: 0 4px 12px rgba(0,0,0,0.1);';
                btn.onclick = () => window.location.replace('/');
                container.appendChild(btn);
            }}

            // Also try periodically in case opener wasn't ready
            let attempts = 0;
            const interval = setInterval(() => {{
                attempts++;
                if (notifyAndClose() || attempts > 10) {{
                    clearInterval(interval);
                }}
            }}, 1000);
        </script>
    </body>
    </html>
    """
    
    response = HTMLResponse(content=html)
    # Removing COOP header to ensure window.opener is available across ports in dev
    # response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    
    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key=REFRESH_TOKEN_COOKIE,
        value=refresh_token,
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    
    # Clear the OAuth state cookie
    response.delete_cookie(OAUTH_STATE_COOKIE)
    
    return response


def _error_response(message: str) -> HTMLResponse:
    """
    Generate HTML response for OAuth errors.
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Login Failed</title>
        <style>
            body {{
                font-family: system-ui, -apple-system, sans-serif;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
                margin: 0;
                background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%);
                color: white;
            }}
            .container {{
                text-align: center;
                padding: 2rem;
                max-width: 400px;
            }}
            .error-icon {{
                font-size: 48px;
                margin-bottom: 1rem;
            }}
            .message {{
                background: rgba(255,255,255,0.2);
                padding: 1rem;
                border-radius: 8px;
                margin: 1rem 0;
            }}
            button {{
                background: white;
                color: #f5576c;
                border: none;
                padding: 12px 24px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                margin-top: 1rem;
            }}
            button:hover {{
                opacity: 0.9;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="error-icon">⚠️</div>
            <h2>Login Failed</h2>
            <div class="message">{message}</div>
            <button onclick="window.close()">Close</button>
        </div>
        <script>
            // Notify opener of error
            if (window.opener && !window.opener.closed) {{
                try {{
                    window.opener.postMessage({{
                        type: 'OAUTH_ERROR',
                        error: "{message}"
                    }}, '*');
                    // Auto-close after a short delay
                    setTimeout(() => window.close(), 2000);
                }} catch (err) {{
                    console.error('Failed to post error message:', err);
                }}
            }}
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(
        content=html, 
        status_code=400,
        headers={
            # "Cross-Origin-Opener-Policy": "same-origin-allow-popups"
        }
    )
