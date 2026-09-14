import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
