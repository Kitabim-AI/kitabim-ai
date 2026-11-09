"""Unit tests for services/backend/auth/email_domain_guard.py."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.core.cache_config import (
    KEY_USERCHECK_COOLDOWN,
    KEY_USERCHECK_DOMAIN,
    TTL_USERCHECK_DOMAIN,
    TTL_USERCHECK_NEGATIVE_MX,
)
from app.core.config import settings as base_settings
from auth import email_domain_guard
from auth.email_domain_guard import (
    evaluate_signup_email_domain,
    probe_usercheck_status,
    validate_usercheck_config,
)


class InMemoryCacheStub:
    """Simple in-memory replacement for `cache_service` with TTL tracking."""

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.ttls: dict[str, int | None] = {}

    async def get(self, key: str) -> Any:
        return self.store.get(key)

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        self.store[key] = value
        self.ttls[key] = ttl
        return True


class FakeRedisPaceStub:
    """In-memory replacement for `get_redis().set(..., nx=True, px=...)`."""

    def __init__(self, responses: list[bool] | None = None) -> None:
        self.responses = list(responses) if responses is not None else None
        self.calls: list[tuple[str, bool | None, int | None]] = []

    async def set(
        self, key: str, value: str, *, nx: bool | None = None, px: int | None = None
    ) -> bool:
        self.calls.append((key, nx, px))
        if self.responses:
            return self.responses.pop(0)
        return True


def _enabled_settings(**overrides: Any):
    defaults = {
        "usercheck_enabled": True,
        "usercheck_api_key": "uc_live_test_key_123",
        "admin_emails": "admin@custom-org.org",
        "redis_cache_enabled": True,
        "redis_cache_key_prefix": "kitabim:cache:",
    }
    defaults.update(overrides)
    return replace(base_settings, **defaults)


def _mock_httpx_transport(handler):
    """Patch `httpx.AsyncClient` in `email_domain_guard` with `httpx.MockTransport`."""
    transport = httpx.MockTransport(handler)
    real_async_client = httpx.AsyncClient

    def _factory(*args: Any, **kwargs: Any):
        kwargs["transport"] = transport
        return real_async_client(*args, **kwargs)

    return patch.object(email_domain_guard.httpx, "AsyncClient", side_effect=_factory)


def test_validate_usercheck_config():
    with patch.object(
        email_domain_guard,
        "settings",
        replace(base_settings, usercheck_enabled=False, usercheck_api_key=""),
    ):
        validate_usercheck_config()

    for bad_key in ("", "   ", "FILL_IN"):
        with patch.object(
            email_domain_guard,
            "settings",
            replace(base_settings, usercheck_enabled=True, usercheck_api_key=bad_key),
        ):
            with pytest.raises(ValueError, match="USERCHECK_API_KEY"):
                validate_usercheck_config()

    with patch.object(email_domain_guard, "settings", _enabled_settings()):
        validate_usercheck_config()


@pytest.mark.asyncio
async def test_probe_usercheck_status_handles_200_401_and_timeout():
    with patch.object(email_domain_guard, "settings", _enabled_settings()):
        with _mock_httpx_transport(
            lambda req: httpx.Response(200, json={"usage": {"remaining": 987}})
        ):
            assert await probe_usercheck_status() == 987

        with _mock_httpx_transport(
            lambda req: httpx.Response(401, json={"error": "Invalid API key"})
        ):
            with pytest.raises(PermissionError, match="401"):
                await probe_usercheck_status()

        def _raise_timeout(req: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=req)

        with _mock_httpx_transport(_raise_timeout):
            assert await probe_usercheck_status() is None


@pytest.mark.asyncio
async def test_fast_paths_bypass_external_http_calls():
    cache_stub = InMemoryCacheStub()
    http_called = False

    def _unexpected_http(req: httpx.Request) -> httpx.Response:
        nonlocal http_called
        http_called = True
        return httpx.Response(500)

    patched_settings = _enabled_settings()
    with (
        patch.object(email_domain_guard, "settings", patched_settings),
        patch("auth.oauth_providers.settings", patched_settings),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        _mock_httpx_transport(_unexpected_http),
    ):
        # 1. Facebook hidden-email placeholder
        d1 = await evaluate_signup_email_domain(
            email="1001@facebook.placeholder",
            provider="facebook",
            email_verified=False,
        )
        assert d1.status == "allow"
        assert d1.reason == "placeholder_email"

        # 2. Configured ADMIN_EMAILS
        d2 = await evaluate_signup_email_domain(
            email="Admin@Custom-Org.org",
            provider="google",
            email_verified=True,
        )
        assert d2.status == "allow"
        assert d2.reason == "admin_email"

        # 3. Verified consumer allowlist (including pm.me & gmail.com)
        for email in ("reader@gmail.com", "alias@pm.me", "reader@qq.com"):
            d3 = await evaluate_signup_email_domain(
                email=email,
                provider="google",
                email_verified=True,
            )
            assert d3.status == "allow"
            assert d3.reason == "trusted_provider"

        # 4. Local system_configs blocked domains (wildcards, @ prefixes, subdomains)
        d4 = await evaluate_signup_email_domain(
            email="deodtbmtd38n6x@hhz.xintaitong.com",
            provider="google",
            email_verified=True,
            blocked_domains_raw=" *.Xintaitong.com., @spamfarm.org ",
        )
        assert d4.status == "reject_policy"
        assert d4.reason == "blocked_domain_config"
        assert d4.root_domain == "xintaitong.com"

        # 5. Runtime kill-switch disabled (`auth_usercheck_enabled="false"`)
        d5 = await evaluate_signup_email_domain(
            email="newuser@novel-university.edu",
            provider="google",
            email_verified=True,
            auth_usercheck_enabled_raw="false",
        )
        assert d5.status == "allow"
        assert d5.reason == "gate_disabled"

    assert http_called is False


@pytest.mark.asyncio
async def test_unverified_consumer_domain_does_not_take_allowlist_shortcut():
    cache_stub = InMemoryCacheStub()
    pace_stub = FakeRedisPaceStub()
    requests: list[str] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        requests.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "domain": "gmail.com",
                "disposable": False,
                "spam": False,
                "blocklisted": False,
                "free_subdomain": False,
                "relay_domain": False,
                "mx": True,
            },
        )

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=pace_stub),
        _mock_httpx_transport(_handler),
    ):
        decision = await evaluate_signup_email_domain(
            email="someone@gmail.com",
            provider="facebook",
            email_verified=False,
        )
        assert decision.status == "allow"
        assert decision.reason == "clean"
        assert len(requests) == 1


@pytest.mark.asyncio
async def test_etld_plus_one_root_caching_blocks_rotated_subdomains_in_one_credit():
    cache_stub = InMemoryCacheStub()
    pace_stub = FakeRedisPaceStub()
    http_calls: list[httpx.Request] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        http_calls.append(req)
        # UserCheck echoes the queried subdomain, NOT the eTLD+1 root!
        return httpx.Response(
            200,
            headers={"X-RateLimit-Remaining": "0"},
            json={
                "domain": "a1.tempfarm.co.uk",
                "disposable": True,
                "spam": False,
                "blocklisted": False,
                "free_subdomain": False,
                "relay_domain": False,
                "mx": True,
            },
        )

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=pace_stub),
        _mock_httpx_transport(_handler),
    ):
        first = await evaluate_signup_email_domain(
            email="bot1@a1.tempfarm.co.uk",
            provider="google",
            email_verified=True,
            blocked_domains_raw="",
        )
        assert first.status == "reject_policy"
        assert first.reason == "disposable"
        assert first.root_domain == "tempfarm.co.uk"
        assert first.cache_status == "miss"
        assert len(http_calls) == 1
        assert http_calls[0].headers["Authorization"] == "Bearer uc_live_test_key_123"

        # Both exact subdomain and eTLD+1 root cached for 30 days
        assert (
            cache_stub.ttls[KEY_USERCHECK_DOMAIN.format(domain="a1.tempfarm.co.uk")]
            == TTL_USERCHECK_DOMAIN
        )
        assert (
            cache_stub.ttls[KEY_USERCHECK_DOMAIN.format(domain="tempfarm.co.uk")]
            == TTL_USERCHECK_DOMAIN
        )

        # Second bot on rotated subdomain b2.tempfarm.co.uk blocked at 0 HTTP calls!
        second = await evaluate_signup_email_domain(
            email="bot2@b2.tempfarm.co.uk",
            provider="google",
            email_verified=True,
            blocked_domains_raw="",
        )
        assert second.status == "reject_policy"
        assert second.reason == "disposable"
        assert second.cache_status == "hit_parent"
        assert len(http_calls) == 1


@pytest.mark.asyncio
async def test_asymmetric_parent_cache_never_auto_allows_unverified_child_subdomains():
    cache_stub = InMemoryCacheStub()
    await cache_stub.set(
        KEY_USERCHECK_DOMAIN.format(domain="example.edu"),
        {"status": "allow", "reason": "clean", "root_domain": "example.edu"},
        ttl=TTL_USERCHECK_DOMAIN,
    )
    pace_stub = FakeRedisPaceStub()
    queried_urls: list[str] = []

    def _handler(req: httpx.Request) -> httpx.Response:
        queried_urls.append(str(req.url))
        return httpx.Response(
            200,
            json={
                "domain": " disposable-lab.example.edu",
                "disposable": False,
                "spam": False,
                "blocklisted": False,
                "free_subdomain": False,
                "relay_domain": False,
                "mx": False,
            },
        )

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=pace_stub),
        _mock_httpx_transport(_handler),
    ):
        result = await evaluate_signup_email_domain(
            email="student@disposable-lab.example.edu",
            provider="google",
            email_verified=True,
        )
        assert len(queried_urls) == 1
        assert result.status == "reject_policy"
        assert result.reason == "mx_false"
        assert (
            cache_stub.ttls[
                KEY_USERCHECK_DOMAIN.format(domain="disposable-lab.example.edu")
            ]
            == TTL_USERCHECK_NEGATIVE_MX
        )


@pytest.mark.asyncio
async def test_relay_domain_allowed_and_free_subdomain_only_caches_exact_host():
    cache_stub = InMemoryCacheStub()
    pace_stub = FakeRedisPaceStub()

    def _handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/privaterelay.appleid.com"):
            return httpx.Response(
                200,
                json={
                    "domain": "privaterelay.appleid.com",
                    "disposable": False,
                    "spam": False,
                    "blocklisted": False,
                    "free_subdomain": True,
                    "relay_domain": True,
                    "mx": True,
                },
            )
        return httpx.Response(
            200,
            json={
                "domain": "throwaway.ddns-provider.org",
                "disposable": False,
                "spam": False,
                "blocklisted": False,
                "free_subdomain": True,
                "relay_domain": False,
                "mx": True,
            },
        )

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=pace_stub),
        _mock_httpx_transport(_handler),
    ):
        relay = await evaluate_signup_email_domain(
            email="abc@privaterelay.appleid.com",
            provider="google",
            email_verified=True,
        )
        assert relay.status == "allow"
        assert relay.reason == "relay_domain"

        free_sub = await evaluate_signup_email_domain(
            email="bot@throwaway.ddns-provider.org",
            provider="google",
            email_verified=True,
        )
        assert free_sub.status == "reject_policy"
        assert free_sub.reason == "free_subdomain"
        assert (
            KEY_USERCHECK_DOMAIN.format(domain="throwaway.ddns-provider.org")
            in cache_stub.store
        )
        assert (
            KEY_USERCHECK_DOMAIN.format(domain="ddns-provider.org")
            not in cache_stub.store
        )


@pytest.mark.asyncio
async def test_fail_closed_on_mx_null_429_503_and_timeout_without_domain_caching():
    # 1. mx: null -> reject_unavailable, zero cache writes
    cache_stub = InMemoryCacheStub()
    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=FakeRedisPaceStub()),
        _mock_httpx_transport(
            lambda req: httpx.Response(
                200,
                json={
                    "domain": "slowdns.org",
                    "disposable": False,
                    "spam": False,
                    "mx": None,
                },
            )
        ),
    ):
        d_null = await evaluate_signup_email_domain(
            email="u@slowdns.org", provider="google", email_verified=True
        )
        assert d_null.status == "reject_unavailable"
        assert d_null.reason == "mx_inconclusive"
        assert cache_stub.store == {}

    # 2. 429 without Retry-After -> sets 300s default cooldown, zero domain cache writes
    cache_stub_429 = InMemoryCacheStub()
    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub_429),
        patch.object(email_domain_guard, "get_redis", return_value=FakeRedisPaceStub()),
        _mock_httpx_transport(
            lambda req: httpx.Response(429, json={"error": "quota_exceeded"})
        ),
    ):
        d_429 = await evaluate_signup_email_domain(
            email="u@corp-a.org", provider="google", email_verified=True
        )
        assert d_429.status == "reject_unavailable"
        assert d_429.reason == "rate_limited"
        assert cache_stub_429.store == {KEY_USERCHECK_COOLDOWN: True}
        assert cache_stub_429.ttls[KEY_USERCHECK_COOLDOWN] == 300

        # Subsequent call short-circuits on active cooldown
        d_cool = await evaluate_signup_email_domain(
            email="u@corp-b.org", provider="google", email_verified=True
        )
        assert d_cool.status == "reject_unavailable"
        assert d_cool.reason == "cooldown_active"

    # 3. ReadTimeout -> sets 15s upstream error cooldown, zero domain cache writes
    cache_stub_timeout = InMemoryCacheStub()

    def _timeout(req: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=req)

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub_timeout),
        patch.object(email_domain_guard, "get_redis", return_value=FakeRedisPaceStub()),
        _mock_httpx_transport(_timeout),
    ):
        d_to = await evaluate_signup_email_domain(
            email="u@corp-c.org", provider="google", email_verified=True
        )
        assert d_to.status == "reject_unavailable"
        assert d_to.reason == "upstream_timeout"
        assert cache_stub_timeout.store == {KEY_USERCHECK_COOLDOWN: True}
        assert cache_stub_timeout.ttls[KEY_USERCHECK_COOLDOWN] == 15


@pytest.mark.asyncio
async def test_pacing_contention_retries_once_then_fails_closed():
    cache_stub = InMemoryCacheStub()
    pace_stub = FakeRedisPaceStub(responses=[False, False])
    sleep_mock = AsyncMock()

    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", cache_stub),
        patch.object(email_domain_guard, "get_redis", return_value=pace_stub),
        patch.object(email_domain_guard.asyncio, "sleep", sleep_mock),
    ):
        decision = await evaluate_signup_email_domain(
            email="u@novel-domain.org", provider="google", email_verified=True
        )
        assert decision.status == "reject_unavailable"
        assert decision.reason == "pacing_contended"
        sleep_mock.assert_awaited_once_with(1.1)
        assert len(pace_stub.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_email",
    [
        "gmail.com",
        "@gmail.com",
        "user@",
        "user@a..b.com",
        "user@evil.com/../status",
        "user@co.uk",
        "a@b@example.com",
    ],
)
async def test_invalid_domains_and_path_traversal_rejected_locally(bad_email: str):
    with (
        patch.object(email_domain_guard, "settings", _enabled_settings()),
        patch.object(email_domain_guard, "cache_service", InMemoryCacheStub()),
    ):
        decision = await evaluate_signup_email_domain(
            email=bad_email, provider="google", email_verified=True
        )
        assert decision.status == "reject_policy"
        assert decision.reason == "invalid_domain"
