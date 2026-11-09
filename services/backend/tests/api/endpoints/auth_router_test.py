import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    # Force reload of api modules to avoid cache shadowing
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def _patched_cors_origins(cors_origins: str):
    # `settings` is a frozen dataclass, so its fields can't be patched
    # in place — swap the module-level `settings` name for a stand-in instead.
    return patch(
        "api.endpoints.auth_router.settings", MagicMock(cors_origins=cors_origins)
    )


def test_auth_basic():
    """Basic unit test scaffold for auth."""
    assert True


def test_allows_configured_cors_origin():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai,https://www.kitabim.ai"):
        assert _is_allowed_redirect_uri("https://kitabim.ai/some/path")


def test_rejects_origin_not_in_cors_list():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert not _is_allowed_redirect_uri("https://evil.example.com/callback")


def test_allows_loopback_ipv4_on_any_port():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert _is_allowed_redirect_uri("http://127.0.0.1:54321/oauth-callback")
        assert _is_allowed_redirect_uri("http://127.0.0.1:1/oauth-callback")


def test_allows_loopback_ipv6():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert _is_allowed_redirect_uri("http://[::1]:54321/oauth-callback")


def test_rejects_localhost_hostname_not_literal_loopback_ip():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert not _is_allowed_redirect_uri("http://localhost:54321/oauth-callback")


def test_rejects_https_loopback():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert not _is_allowed_redirect_uri("https://127.0.0.1:54321/oauth-callback")


def test_rejects_non_http_scheme():
    setup_paths()
    from api.endpoints.auth_router import _is_allowed_redirect_uri

    with _patched_cors_origins("https://kitabim.ai"):
        assert not _is_allowed_redirect_uri("javascript:alert(1)")


def _make_request(path: str = "/api/auth/google/callback"):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [(b"user-agent", b"pytest")],
            "client": ("203.0.113.10", 12345),
            "query_string": b"",
        }
    )


def test_error_response_includes_broadcast_channel_and_validated_redirect():
    setup_paths()
    from api.endpoints.auth_router import _error_response

    with _patched_cors_origins("https://kitabim.ai"):
        # Mobile Safari flow with allowed redirect_uri
        mobile_resp = _error_response(
            "Domain rejected",
            error_code="signup_email_domain_rejected",
            redirect_uri="https://kitabim.ai/?foo=1",
        )
        body = mobile_resp.body.decode("utf-8")
        assert mobile_resp.status_code == 400
        assert "BroadcastChannel('kitabim_auth')" in body
        assert 'errorCode: "signup_email_domain_rejected"' in body
        assert (
            '"https://kitabim.ai/?foo=1&auth_error=signup_email_domain_rejected"'
            in body
        )

        # Untrusted redirect_uri or desktop popup (None) must keep redirectUrl = null
        evil_resp = _error_response(
            "Domain rejected",
            error_code="signup_email_domain_rejected",
            redirect_uri="https://evil.example.com/",
        )
        assert "const redirectUrl = null;" in evil_resp.body.decode("utf-8")

        popup_resp = _error_response(
            "Domain rejected",
            error_code="signup_email_domain_rejected",
            redirect_uri=None,
        )
        assert "const redirectUrl = null;" in popup_resp.body.decode("utf-8")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gate_status", "expected_error_code"),
    [
        ("reject_policy", "signup_email_domain_rejected"),
        ("reject_unavailable", "signup_verification_unavailable"),
    ],
)
async def test_oauth_callback_blocks_new_user_creation_and_rolls_back_before_guard(
    gate_status: str, expected_error_code: str
):
    setup_paths()
    from app.core.i18n import I18n, set_current_lang
    from api.endpoints import auth_router
    from auth.email_domain_guard import DomainGateDecision
    from auth.oauth_providers import OAuthState

    I18n.load_translations()
    set_current_lang("en")

    call_order: list[str] = []
    session = MagicMock()

    async def _rollback():
        call_order.append("rollback")

    session.rollback = AsyncMock(side_effect=_rollback)
    session.commit = AsyncMock()

    fake_provider = MagicMock()
    fake_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "oauth_tok"}
    )
    fake_provider.get_user_info = AsyncMock(
        return_value=SimpleNamespace(
            email="bot@hhz.xintaitong.com",
            email_verified=True,
            provider_id="prov_123",
            name="Bot",
            picture=None,
        )
    )

    fake_config_repo = MagicMock()

    async def _get_cfg(key: str, default: str = "") -> str:
        call_order.append(f"cfg:{key}")
        return "true" if key == "auth_usercheck_enabled" else "xintaitong.com"

    fake_config_repo.get_value = AsyncMock(side_effect=_get_cfg)

    async def _eval_guard(**kwargs):
        call_order.append("guard")
        return DomainGateDecision(
            status=gate_status,  # type: ignore[arg-type]
            reason="disposable",
            domain="hhz.xintaitong.com",
            root_domain="xintaitong.com",
        )

    create_user_mock = AsyncMock()
    request = _make_request()

    with (
        _patched_cors_origins("https://kitabim.ai"),
        patch.object(auth_router.limiter, "enabled", False),
        patch.object(auth_router, "get_provider", return_value=fake_provider),
        patch.object(
            auth_router,
            "decode_oauth_state_token",
            return_value=OAuthState(
                state="s1", nonce="n1", redirect_uri="https://kitabim.ai/"
            ),
        ),
        patch.object(
            auth_router, "get_user_by_provider", new=AsyncMock(return_value=None)
        ),
        patch.object(
            auth_router, "get_user_by_email", new=AsyncMock(return_value=None)
        ),
        patch.object(
            auth_router, "SystemConfigsRepository", return_value=fake_config_repo
        ),
        patch.object(
            auth_router, "evaluate_signup_email_domain", side_effect=_eval_guard
        ),
        patch.object(auth_router, "create_user", create_user_mock),
    ):
        resp = await auth_router.oauth_callback(
            provider="google",
            request=request,
            code="auth_code",
            state="jwt_state",
            error=None,
            session=session,
        )

    assert resp.status_code == 400
    body = resp.body.decode("utf-8")
    assert f'errorCode: "{expected_error_code}"' in body
    assert f"auth_error={expected_error_code}" in body
    create_user_mock.assert_not_awaited()
    assert call_order == [
        "cfg:auth_usercheck_enabled",
        "cfg:auth_blocked_email_domains",
        "rollback",
        "guard",
    ]


@pytest.mark.asyncio
async def test_oauth_callback_skips_domain_guard_for_existing_user_and_guards_placeholder_linking():
    setup_paths()
    from api.endpoints import auth_router
    from auth.oauth_providers import OAuthState

    session = MagicMock()
    session.commit = AsyncMock()

    existing_user = SimpleNamespace(
        id="user-1",
        email="reader@old-domain.org",
        role="reader",
        is_active=True,
    )
    fake_provider = MagicMock()
    fake_provider.exchange_code_for_tokens = AsyncMock(
        return_value={"access_token": "oauth_tok"}
    )
    fake_provider.get_user_info = AsyncMock(
        return_value=SimpleNamespace(
            email="reader@old-domain.org",
            email_verified=True,
            provider_id="prov_existing",
            name="Reader",
            picture=None,
        )
    )
    guard_mock = AsyncMock()
    request = _make_request()

    with (
        patch.object(auth_router.limiter, "enabled", False),
        patch.object(auth_router, "get_provider", return_value=fake_provider),
        patch.object(
            auth_router,
            "decode_oauth_state_token",
            return_value=OAuthState(state="s1", nonce="n1", redirect_uri=None),
        ),
        patch.object(
            auth_router,
            "get_user_by_provider",
            new=AsyncMock(return_value=existing_user),
        ),
        patch.object(auth_router, "update_user_login", new=AsyncMock()),
        patch.object(auth_router, "create_access_token", return_value="acc_jwt"),
        patch.object(
            auth_router, "create_refresh_token", return_value=("ref_jwt", "jti_1")
        ),
        patch.object(auth_router, "store_refresh_token", new=AsyncMock()),
        patch.object(auth_router, "evaluate_signup_email_domain", guard_mock),
    ):
        resp = await auth_router.oauth_callback(
            provider="google",
            request=request,
            code="auth_code",
            state="jwt_state",
            error=None,
            session=session,
        )

    assert resp.status_code == 200
    guard_mock.assert_not_awaited()

    # Cross-provider placeholder linking protection: Google returning @facebook.placeholder
    # must NOT call get_user_by_email!
    fake_provider.get_user_info = AsyncMock(
        return_value=SimpleNamespace(
            email="12345@facebook.placeholder",
            email_verified=True,
            provider_id="google_spoof",
            name="Spoof",
            picture=None,
        )
    )
    get_by_email_mock = AsyncMock(return_value=existing_user)
    fake_cfg_repo = MagicMock()
    fake_cfg_repo.get_value = AsyncMock(return_value="true")
    session.rollback = AsyncMock()

    from auth.email_domain_guard import DomainGateDecision

    with (
        _patched_cors_origins("https://kitabim.ai"),
        patch.object(auth_router.limiter, "enabled", False),
        patch.object(auth_router, "get_provider", return_value=fake_provider),
        patch.object(
            auth_router,
            "decode_oauth_state_token",
            return_value=OAuthState(state="s1", nonce="n1", redirect_uri=None),
        ),
        patch.object(
            auth_router, "get_user_by_provider", new=AsyncMock(return_value=None)
        ),
        patch.object(auth_router, "get_user_by_email", get_by_email_mock),
        patch.object(
            auth_router, "SystemConfigsRepository", return_value=fake_cfg_repo
        ),
        patch.object(
            auth_router,
            "evaluate_signup_email_domain",
            new=AsyncMock(
                return_value=DomainGateDecision(
                    status="reject_policy",
                    reason="invalid_domain",
                    domain="facebook.placeholder",
                )
            ),
        ),
    ):
        spoof_resp = await auth_router.oauth_callback(
            provider="google",
            request=request,
            code="auth_code",
            state="jwt_state",
            error=None,
            session=session,
        )

    assert spoof_resp.status_code == 400
    get_by_email_mock.assert_not_awaited()
