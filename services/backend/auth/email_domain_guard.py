"""Pre-signup email domain validation gate backed by UserCheck and Redis."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
import time
from typing import Any, Literal, Optional
from urllib.parse import quote

import httpx
import publicsuffix2

from app.core.cache_config import (
    KEY_USERCHECK_COOLDOWN,
    KEY_USERCHECK_DOMAIN,
    KEY_USERCHECK_PACE,
    TTL_USERCHECK_DOMAIN,
    TTL_USERCHECK_NEGATIVE_MX,
)
from app.core.config import settings
from app.services.cache_service import cache_service
from app.utils.circuit_breaker import get_redis
from app.utils.observability import log_json
from app.utils.security import hash_ip_if_present
from auth.oauth_providers import is_admin_email, is_placeholder_email

logger = logging.getLogger("app.auth.usercheck")

USERCHECK_BASE_URL = "https://api.usercheck.com"
USERCHECK_TIMEOUT_SECONDS = 3.0

PACE_TTL_MS = 1100
PACE_SLEEP_SECONDS = 1.1

COOLDOWN_DEFAULT_429_SECONDS = 300
COOLDOWN_MIN_429_SECONDS = 60
COOLDOWN_MAX_429_SECONDS = 3600
COOLDOWN_UPSTREAM_ERROR_SECONDS = 15

ROOT_BLOCK_REASONS: frozenset[str] = frozenset({"disposable", "spam", "blocklisted"})

VERIFIED_CONSUMER_ALLOWLIST: frozenset[str] = frozenset(
    {
        "gmail.com",
        "googlemail.com",
        "icloud.com",
        "me.com",
        "mac.com",
        "outlook.com",
        "hotmail.com",
        "live.com",
        "msn.com",
        "yahoo.com",
        "proton.me",
        "protonmail.com",
        "pm.me",
        "yandex.com",
        "yandex.ru",
        "mail.ru",
        "qq.com",
        "163.com",
    }
)

_DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+$"
)
_SPLIT_DELIM_RE = re.compile(r"[,\s]+")

GateStatus = Literal["allow", "reject_policy", "reject_unavailable"]
CacheStatus = Literal["bypass", "hit_exact", "hit_parent", "miss"]


@dataclass(frozen=True)
class DomainGateDecision:
    """Outcome of evaluating a new OAuth signup's email domain."""

    status: GateStatus
    reason: str
    domain: str
    root_domain: Optional[str] = None
    cache_status: CacheStatus = "bypass"


def validate_usercheck_config() -> None:
    """Validate static UserCheck configuration when the gate is enabled."""
    if not settings.usercheck_enabled:
        return
    api_key = (settings.usercheck_api_key or "").strip()
    if not api_key or api_key == "FILL_IN":
        raise ValueError(
            "USERCHECK_ENABLED is true, but USERCHECK_API_KEY is missing or set to FILL_IN."
        )


async def probe_usercheck_status() -> Optional[int]:
    """
    Probe UserCheck's zero-credit `GET /status` endpoint at startup.

    Returns remaining monthly credits on `200 OK`, raises `PermissionError` on
    `401`/`403` (invalid or revoked API key), and logs a warning returning `None`
    on transient network errors or `5xx` responses so upstream outages cannot
    crash-loop the backend container.
    """
    if not settings.usercheck_enabled:
        return None
    api_key = (settings.usercheck_api_key or "").strip()
    timeout = httpx.Timeout(USERCHECK_TIMEOUT_SECONDS, connect=2.0)
    try:
        async with httpx.AsyncClient(
            base_url=USERCHECK_BASE_URL, timeout=timeout
        ) as client:
            response = await client.get(
                "/status",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.HTTPError as exc:
        log_json(
            logger,
            logging.WARNING,
            "UserCheck /status startup probe failed due to network error",
            error=str(exc),
        )
        return None

    if response.status_code in (401, 403):
        raise PermissionError(
            f"UserCheck /status rejected USERCHECK_API_KEY with HTTP {response.status_code}"
        )

    if response.status_code != 200:
        log_json(
            logger,
            logging.WARNING,
            "UserCheck /status startup probe returned non-200 status",
            status_code=response.status_code,
        )
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    if isinstance(payload, dict):
        usage = payload.get("usage")
        if isinstance(usage, dict) and isinstance(usage.get("remaining"), int):
            return usage["remaining"]
    return None


def _normalize_domain(raw_domain: str) -> Optional[str]:
    """Normalize a hostname to lowercase Punycode ASCII and validate RFC syntax."""
    candidate = raw_domain.strip().lower().rstrip(".")
    if not candidate or candidate.startswith(".") or ".." in candidate:
        return None
    if any(ch in candidate for ch in ("/", "\\", "?", "#", "@", ":")):
        return None
    try:
        ascii_domain = candidate.encode("idna").decode("ascii")
    except UnicodeError:
        return None
    if not _DOMAIN_RE.fullmatch(ascii_domain):
        return None
    sld = publicsuffix2.get_sld(ascii_domain)
    tld = publicsuffix2.get_tld(ascii_domain)
    if not sld or sld == tld:
        return None
    return ascii_domain


def _extract_email_domain(email: str) -> tuple[Optional[str], str]:
    """Extract `(validated_punycode_domain, raw_logged_domain)` from an email string."""
    local, sep, raw_host = (email or "").strip().lower().rpartition("@")
    logged_host = raw_host[:253] if sep else ""
    if not sep or not local or "@" in local:
        return None, logged_host
    normalized = _normalize_domain(raw_host)
    return normalized, (normalized or logged_host)


def _parse_blocked_domains(blocked_domains_raw: Optional[str]) -> set[str]:
    """Parse admin-configured comma/whitespace-separated blocked root domains."""
    if not blocked_domains_raw:
        return set()
    parsed: set[str] = set()
    for token in _SPLIT_DELIM_RE.split(blocked_domains_raw):
        cleaned = token.strip().lower().lstrip("@").removeprefix("*.").strip(".")
        if not cleaned:
            continue
        normalized = _normalize_domain(cleaned)
        if normalized:
            parsed.add(normalized)
    return parsed


def _parse_retry_after_seconds(header_val: Optional[str]) -> int:
    """Parse HTTP `Retry-After` integer seconds clamped to `60..3600`, defaulting to `300`."""
    if header_val:
        try:
            parsed = int(header_val.strip())
            return max(COOLDOWN_MIN_429_SECONDS, min(COOLDOWN_MAX_429_SECONDS, parsed))
        except ValueError:
            pass
    return COOLDOWN_DEFAULT_429_SECONDS


async def _lookup_cached_verdict(
    domain: str, root_domain: str
) -> Optional[DomainGateDecision]:
    """
    Perform two-key asymmetric Redis verdict lookup.

    1. Exact `domain`: honors both `"allow"` and `"reject_policy"`.
    2. Registrable `root_domain` (when `root_domain != domain`): honors ONLY
       `"reject_policy"` with `reason in ROOT_BLOCK_REASONS` (`disposable`,
       `spam`, `blocklisted`), never `"allow"`.
    """
    exact_cached = await cache_service.get(KEY_USERCHECK_DOMAIN.format(domain=domain))
    if isinstance(exact_cached, dict):
        status = exact_cached.get("status")
        reason = exact_cached.get("reason")
        if status in ("allow", "reject_policy") and isinstance(reason, str):
            return DomainGateDecision(
                status=status,
                reason=reason,
                domain=domain,
                root_domain=exact_cached.get("root_domain") or root_domain,
                cache_status="hit_exact",
            )

    if root_domain and root_domain != domain:
        parent_cached = await cache_service.get(
            KEY_USERCHECK_DOMAIN.format(domain=root_domain)
        )
        if isinstance(parent_cached, dict):
            status = parent_cached.get("status")
            reason = parent_cached.get("reason")
            if status == "reject_policy" and reason in ROOT_BLOCK_REASONS:
                return DomainGateDecision(
                    status="reject_policy",
                    reason=reason,
                    domain=domain,
                    root_domain=root_domain,
                    cache_status="hit_parent",
                )

    return None


async def _acquire_redis_pace_slot() -> bool:
    """
    Attempt to acquire the 1.1s Redis pace slot (`SET NX PX 1100`).

    If Redis is disabled or unreachable, logs a warning and returns `True` so a
    Redis hiccup does not silently bypass disposable-domain checks.
    """
    if not settings.redis_cache_enabled:
        return True
    pace_key = f"{settings.redis_cache_key_prefix}{KEY_USERCHECK_PACE}"
    try:
        acquired = await get_redis().set(pace_key, "1", nx=True, px=PACE_TTL_MS)
        return bool(acquired)
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Redis pace lock check failed; proceeding directly to UserCheck",
            error=str(exc),
        )
        return True


def _emit_audit_log(
    decision: DomainGateDecision,
    *,
    provider: str,
    start_time: float,
    client_ip: Optional[str],
    rate_limit_remaining: Optional[str] = None,
    level: int = logging.INFO,
) -> DomainGateDecision:
    latency_ms = round((time.monotonic() - start_time) * 1000, 2)
    log_json(
        logger,
        level,
        "Evaluated signup email domain",
        provider=provider,
        domain=decision.domain,
        root_domain=decision.root_domain,
        decision=decision.status,
        reason=decision.reason,
        cache_status=decision.cache_status,
        latency_ms=latency_ms,
        rate_limit_remaining=rate_limit_remaining,
        ip_hash=hash_ip_if_present(client_ip),
    )
    return decision


async def evaluate_signup_email_domain(
    *,
    email: str,
    provider: str,
    email_verified: bool,
    auth_usercheck_enabled_raw: Optional[str] = "true",
    blocked_domains_raw: Optional[str] = "",
    client_ip: Optional[str] = None,
) -> DomainGateDecision:
    """
    Evaluate whether a new OAuth signup's email domain is permitted to register.

    This function is strictly DB-free; callers must fetch `system_configs` values
    and release any pooled SQLAlchemy transaction (`await session.rollback()`)
    before awaiting this coroutine.
    """
    start_time = time.monotonic()
    normalized_email = (email or "").strip().lower()

    # 1. Synthetic social placeholder bypass (e.g. @facebook.placeholder)
    if is_placeholder_email(normalized_email, provider=provider):
        _, raw_host = _extract_email_domain(normalized_email)
        return _emit_audit_log(
            DomainGateDecision(
                status="allow",
                reason="placeholder_email",
                domain=raw_host,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 2. Configured administrator email bypass
    if is_admin_email(normalized_email):
        parsed_domain, raw_host = _extract_email_domain(normalized_email)
        return _emit_audit_log(
            DomainGateDecision(
                status="allow",
                reason="admin_email",
                domain=parsed_domain or raw_host,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 3. Punycode + RFC hostname validation (enforced before external calls)
    domain, raw_host = _extract_email_domain(normalized_email)
    if not domain:
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason="invalid_domain",
                domain=raw_host,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    root_domain = publicsuffix2.get_sld(domain) or domain

    # 4. Local Admin Panel suffix denylist (enforced even when external UserCheck is disabled)
    blocked_domains = _parse_blocked_domains(blocked_domains_raw)
    if any(
        domain == blocked or domain.endswith(f".{blocked}")
        for blocked in blocked_domains
    ):
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason="blocked_domain_config",
                domain=domain,
                root_domain=root_domain,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 5. Static env flag + live runtime Admin Panel toggle
    runtime_enabled = (auth_usercheck_enabled_raw or "true").strip().lower() in {
        "true",
        "1",
        "yes",
    }
    if not settings.usercheck_enabled or not runtime_enabled:
        return _emit_audit_log(
            DomainGateDecision(
                status="allow",
                reason="gate_disabled",
                domain=domain,
                root_domain=root_domain,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 6. Zero-credit verified mainstream consumer mailbox allowlist
    if email_verified and domain in VERIFIED_CONSUMER_ALLOWLIST:
        return _emit_audit_log(
            DomainGateDecision(
                status="allow",
                reason="trusted_provider",
                domain=domain,
                root_domain=root_domain,
                cache_status="bypass",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 7. Two-key asymmetric Redis domain cache lookup
    cached_decision = await _lookup_cached_verdict(domain, root_domain)
    if cached_decision is not None:
        return _emit_audit_log(
            cached_decision,
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
        )

    # 8. Upstream cooldown & atomic 1 req/sec Redis pacing
    if await cache_service.get(KEY_USERCHECK_COOLDOWN):
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="cooldown_active",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            level=logging.WARNING,
        )

    if not await _acquire_redis_pace_slot():
        await asyncio.sleep(PACE_SLEEP_SECONDS)
        # Re-check cache and cooldown after waiting (singleflight hit if same domain/root)
        cached_after_wait = await _lookup_cached_verdict(domain, root_domain)
        if cached_after_wait is not None:
            return _emit_audit_log(
                cached_after_wait,
                provider=provider,
                start_time=start_time,
                client_ip=client_ip,
            )
        if await cache_service.get(KEY_USERCHECK_COOLDOWN):
            return _emit_audit_log(
                DomainGateDecision(
                    status="reject_unavailable",
                    reason="cooldown_active",
                    domain=domain,
                    root_domain=root_domain,
                    cache_status="miss",
                ),
                provider=provider,
                start_time=start_time,
                client_ip=client_ip,
                level=logging.WARNING,
            )
        if not await _acquire_redis_pace_slot():
            return _emit_audit_log(
                DomainGateDecision(
                    status="reject_unavailable",
                    reason="pacing_contended",
                    domain=domain,
                    root_domain=root_domain,
                    cache_status="miss",
                ),
                provider=provider,
                start_time=start_time,
                client_ip=client_ip,
                level=logging.WARNING,
            )

    # 9. Scoped UserCheck `GET /domain/{domain}` request
    api_key = (settings.usercheck_api_key or "").strip()
    if not api_key or api_key == "FILL_IN":
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_error",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            level=logging.ERROR,
        )

    quoted_domain = quote(domain, safe="")
    timeout = httpx.Timeout(USERCHECK_TIMEOUT_SECONDS, connect=2.0)
    try:
        async with httpx.AsyncClient(
            base_url=USERCHECK_BASE_URL, timeout=timeout
        ) as client:
            response = await client.get(
                f"/domain/{quoted_domain}",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException:
        await cache_service.set(
            KEY_USERCHECK_COOLDOWN, True, ttl=COOLDOWN_UPSTREAM_ERROR_SECONDS
        )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_timeout",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            level=logging.WARNING,
        )
    except httpx.HTTPError:
        await cache_service.set(
            KEY_USERCHECK_COOLDOWN, True, ttl=COOLDOWN_UPSTREAM_ERROR_SECONDS
        )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_error",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            level=logging.WARNING,
        )

    rate_limit_remaining = response.headers.get("X-RateLimit-Remaining")
    status_code = response.status_code

    if status_code == 400:
        verdict_payload: dict[str, Any] = {
            "status": "reject_policy",
            "reason": "upstream_bad_request",
            "root_domain": root_domain,
        }
        await cache_service.set(
            KEY_USERCHECK_DOMAIN.format(domain=domain),
            verdict_payload,
            ttl=TTL_USERCHECK_DOMAIN,
        )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason="upstream_bad_request",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
        )

    if status_code == 429:
        cooldown_ttl = _parse_retry_after_seconds(response.headers.get("Retry-After"))
        await cache_service.set(KEY_USERCHECK_COOLDOWN, True, ttl=cooldown_ttl)
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="rate_limited",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
            level=logging.WARNING,
        )

    if status_code != 200:
        if status_code >= 500:
            await cache_service.set(
                KEY_USERCHECK_COOLDOWN, True, ttl=COOLDOWN_UPSTREAM_ERROR_SECONDS
            )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_error",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
            level=logging.ERROR if status_code in (401, 403) else logging.WARNING,
        )

    try:
        payload = response.json()
    except ValueError:
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_error",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
            level=logging.WARNING,
        )

    if not isinstance(payload, dict):
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="upstream_error",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
            level=logging.WARNING,
        )

    # 10. Truth-table evaluation
    disposable = bool(payload.get("disposable"))
    spam = bool(payload.get("spam"))
    blocklisted = bool(payload.get("blocklisted"))
    free_subdomain = bool(payload.get("free_subdomain"))
    relay_domain = bool(payload.get("relay_domain"))
    mx_val = payload.get("mx")

    if disposable or spam or blocklisted:
        block_reason = (
            "disposable" if disposable else ("spam" if spam else "blocklisted")
        )
        verdict = {
            "status": "reject_policy",
            "reason": block_reason,
            "root_domain": root_domain,
        }
        await cache_service.set(
            KEY_USERCHECK_DOMAIN.format(domain=domain),
            verdict,
            ttl=TTL_USERCHECK_DOMAIN,
        )
        if not free_subdomain and root_domain and root_domain != domain:
            await cache_service.set(
                KEY_USERCHECK_DOMAIN.format(domain=root_domain),
                verdict,
                ttl=TTL_USERCHECK_DOMAIN,
            )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason=block_reason,
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
        )

    if free_subdomain and not relay_domain:
        verdict = {
            "status": "reject_policy",
            "reason": "free_subdomain",
            "root_domain": root_domain,
        }
        await cache_service.set(
            KEY_USERCHECK_DOMAIN.format(domain=domain),
            verdict,
            ttl=TTL_USERCHECK_DOMAIN,
        )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason="free_subdomain",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
        )

    if mx_val is False:
        verdict = {
            "status": "reject_policy",
            "reason": "mx_false",
            "root_domain": root_domain,
        }
        await cache_service.set(
            KEY_USERCHECK_DOMAIN.format(domain=domain),
            verdict,
            ttl=TTL_USERCHECK_NEGATIVE_MX,
        )
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_policy",
                reason="mx_false",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
        )

    if mx_val is not True:
        # Incomplete DNS lookup (`mx: null`) — fail closed without caching
        return _emit_audit_log(
            DomainGateDecision(
                status="reject_unavailable",
                reason="mx_inconclusive",
                domain=domain,
                root_domain=root_domain,
                cache_status="miss",
            ),
            provider=provider,
            start_time=start_time,
            client_ip=client_ip,
            rate_limit_remaining=rate_limit_remaining,
            level=logging.WARNING,
        )

    allow_reason = "relay_domain" if relay_domain else "clean"
    await cache_service.set(
        KEY_USERCHECK_DOMAIN.format(domain=domain),
        {
            "status": "allow",
            "reason": allow_reason,
            "root_domain": root_domain,
        },
        ttl=TTL_USERCHECK_DOMAIN,
    )
    return _emit_audit_log(
        DomainGateDecision(
            status="allow",
            reason=allow_reason,
            domain=domain,
            root_domain=root_domain,
            cache_status="miss",
        ),
        provider=provider,
        start_time=start_time,
        client_ip=client_ip,
        rate_limit_remaining=rate_limit_remaining,
    )
