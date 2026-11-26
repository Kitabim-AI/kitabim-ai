from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

_TOKEN_LOCK = threading.RLock()

_CALLBACK_HTML = b"""<!doctype html>
<html><body>
<p>Logging in to Kitabim...</p>
<script>
  var hash = window.location.hash.substring(1);
  fetch('/oauth-callback/token?' + hash).then(function () {
    document.body.innerHTML = '<p>Login complete. You can close this tab.</p>';
  });
</script>
</body></html>"""

_LAST_CAPTURED_REFRESH_TOKEN: Optional[str] = None


class AuthError(Exception):
    """Raised when browser-based login fails or times out."""


def _jwt_exp(token: str) -> Optional[float]:
    """Decode (not verify - only used for local re-login UX) the `exp`
    claim from a JWT's payload segment."""
    try:
        payload_b64 = token.split(".")[1]
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        return float(payload["exp"])
    except Exception:
        return None


def _load_token_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_token_config(
    config_path: Path, access_token: str, refresh_token: Optional[str] = None
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {"access_token": access_token}
    if refresh_token:
        payload["refresh_token"] = refresh_token
    tmp_path = config_path.parent / (
        f".{config_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    tmp_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(tmp_path, 0o600)
    except OSError:
        pass
    os.replace(tmp_path, config_path)
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass


def is_token_usable(
    token: Optional[str],
    *,
    min_ttl_seconds: float = 60.0,
    rejected_token: Optional[str] = None,
) -> bool:
    """Return True if ``token`` is a non-rejected JWT with at least ``min_ttl_seconds`` remaining."""
    if not token:
        return False
    if rejected_token and token == rejected_token:
        return False
    exp = _jwt_exp(token)
    if exp is None:
        return False
    return exp > time.time() + min_ttl_seconds


def read_valid_cached_token(
    config_path: Path,
    *,
    min_ttl_seconds: float = 60.0,
    rejected_token: Optional[str] = None,
) -> Optional[str]:
    """Read a valid access token from ``config_path`` without network calls or browser login."""
    cached = _load_token_config(config_path)
    token = cached.get("access_token")
    if isinstance(token, str) and is_token_usable(
        token, min_ttl_seconds=min_ttl_seconds, rejected_token=rejected_token
    ):
        return token
    return None


def get_token_status(config_path: Path) -> dict[str, Any]:
    """Return non-sensitive metadata about the cached access and refresh tokens."""
    now = time.time()
    cached = _load_token_config(config_path)
    access_token = cached.get("access_token")
    refresh_token = cached.get("refresh_token")

    access_exp = _jwt_exp(access_token) if isinstance(access_token, str) else None
    refresh_exp = _jwt_exp(refresh_token) if isinstance(refresh_token, str) else None

    access_expires_in = (access_exp - now) if access_exp is not None else None
    refresh_expires_in = (refresh_exp - now) if refresh_exp is not None else None

    access_valid = bool(
        isinstance(access_token, str)
        and access_exp is not None
        and access_exp > now + 60
    )
    refresh_valid = bool(
        isinstance(refresh_token, str)
        and (refresh_exp is None or refresh_exp > now + 60)
    )
    return {
        "hasAccessToken": bool(access_token),
        "accessValid": access_valid,
        "accessExpiresIn": (
            round(access_expires_in, 1) if access_expires_in is not None else None
        ),
        "hasRefreshToken": bool(refresh_token),
        "refreshValid": refresh_valid,
        "refreshExpiresIn": (
            round(refresh_expires_in, 1) if refresh_expires_in is not None else None
        ),
        "authenticated": bool(access_valid or refresh_valid),
    }


def _make_handler(result_holder: dict, done_event: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/oauth-callback":
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(_CALLBACK_HTML)
            elif parsed.path == "/oauth-callback/token":
                params = parse_qs(parsed.query)
                token = params.get("access_token", [None])[0]
                refresh_token = params.get("refresh_token", [None])[0]
                if token:
                    result_holder["token"] = token
                if refresh_token:
                    result_holder["refresh_token"] = refresh_token
                self.send_response(200)
                self.end_headers()
                done_event.set()
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # keep the CLI output quiet

    return Handler


def _login(base_url: str, provider: str, timeout: float = 120.0) -> str:
    global _LAST_CAPTURED_REFRESH_TOKEN
    _LAST_CAPTURED_REFRESH_TOKEN = None
    done_event = threading.Event()
    result_holder: dict = {}
    handler_cls = _make_handler(result_holder, done_event)

    server = HTTPServer(("127.0.0.1", 0), handler_cls)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    redirect_uri = f"http://127.0.0.1:{port}/oauth-callback"
    login_url = f"{base_url}/auth/{provider}/login?" + urlencode({"next": redirect_uri})
    print(f"Opening browser to log in: {login_url}")
    webbrowser.open(login_url)

    got_it = done_event.wait(timeout=timeout)
    server.shutdown()
    thread.join(timeout=5)

    if not got_it or "token" not in result_holder:
        raise AuthError("Login timed out or was cancelled")

    _LAST_CAPTURED_REFRESH_TOKEN = result_holder.get("refresh_token")
    return result_holder["token"]


def refresh_access_token(
    base_url: str,
    config_path: Path,
    *,
    max_retries: int = 3,
    retry_backoff: float = 1.0,
    rejected_token: Optional[str] = None,
) -> Optional[str]:
    """Use the stored non-rotating ``refresh_token`` to mint a fresh access token.

    Retries transient network / 5xx / 429 failures with exponential backoff, and
    returns immediately if another thread/process already wrote a fresher token.
    """
    with _TOKEN_LOCK:
        cached = _load_token_config(config_path)
        if not cached:
            return None
        current_access = cached.get("access_token")
        if (
            rejected_token
            and isinstance(current_access, str)
            and is_token_usable(
                current_access, min_ttl_seconds=60.0, rejected_token=rejected_token
            )
        ):
            return current_access

        refresh_token = cached.get("refresh_token")
        if not refresh_token:
            return None

        attempts = max(1, int(max_retries))
        for attempt in range(attempts):
            try:
                response = httpx.post(
                    f"{base_url.rstrip('/')}/auth/refresh",
                    json={"refresh_token": refresh_token},
                    timeout=15.0,
                )
                if response.status_code == 200:
                    body = response.json()
                    new_access = body.get("access_token")
                    if not new_access:
                        return None
                    _save_token_config(
                        config_path, str(new_access), refresh_token=refresh_token
                    )
                    return str(new_access)
                if response.status_code in (400, 401, 403):
                    logger.warning(
                        "Refresh token rejected by server (HTTP %s)",
                        response.status_code,
                    )
                    return None
                logger.warning(
                    "Transient HTTP %s refreshing access token (attempt %d/%d)",
                    response.status_code,
                    attempt + 1,
                    attempts,
                )
            except Exception as exc:
                logger.warning(
                    "Error refreshing access token (attempt %d/%d): %s",
                    attempt + 1,
                    attempts,
                    exc,
                )
            if attempt + 1 < attempts:
                time.sleep(retry_backoff * (2**attempt))
        return None


def login_and_save(
    base_url: str, config_path: Path, provider: str = "google", timeout: float = 120.0
) -> dict[str, Optional[str]]:
    """Run interactive loopback OAuth login and save ``{access_token, refresh_token}`` (`0600`)."""
    with _TOKEN_LOCK:
        token = _login(base_url.rstrip("/"), provider, timeout=timeout)
        refresh_token = _LAST_CAPTURED_REFRESH_TOKEN
        _save_token_config(config_path, token, refresh_token=refresh_token)
        return {"access_token": token, "refresh_token": refresh_token}


def get_valid_token(
    base_url: str,
    config_path: Path,
    provider: str = "google",
    *,
    headless: bool = False,
    force_refresh: bool = False,
    rejected_token: Optional[str] = None,
) -> str:
    global _LAST_CAPTURED_REFRESH_TOKEN
    with _TOKEN_LOCK:
        existing_refresh: Optional[str] = None
        if config_path.exists():
            cached = _load_token_config(config_path)
            token = cached.get("access_token")
            existing_refresh = cached.get("refresh_token")
            exp = _jwt_exp(token) if isinstance(token, str) else None
            if not force_refresh and token and exp and exp > time.time() + 300:
                return str(token)
            if (
                force_refresh
                and rejected_token
                and isinstance(token, str)
                and is_token_usable(
                    token, min_ttl_seconds=60.0, rejected_token=rejected_token
                )
            ):
                return token
            if existing_refresh:
                refreshed = refresh_access_token(
                    base_url, config_path, rejected_token=rejected_token
                )
                if refreshed:
                    return refreshed

        if headless:
            raise AuthError(
                "Authentication required in headless mode (token expired or missing refresh_token). "
                "Run 'python main.py login' first."
            )

        _LAST_CAPTURED_REFRESH_TOKEN = None
        login_res = _login(base_url, provider)
        if isinstance(login_res, tuple):
            token, captured_refresh = login_res
        else:
            token = login_res
            captured_refresh = _LAST_CAPTURED_REFRESH_TOKEN or existing_refresh
        _save_token_config(config_path, token, refresh_token=captured_refresh)
        return token


def wait_for_reauth_sync(
    base_url: str,
    config_path: Path,
    *,
    poll_interval: float = 3.0,
    refresh_retry_interval: float = 60.0,
    stop_event: Optional[threading.Event] = None,
    rejected_token: Optional[str] = None,
    on_waiting: Optional[Callable[[], None]] = None,
) -> str:
    """Block until a valid token appears in ``config_path`` or refresh succeeds.

    Never exits on token expiry — allows a long-running process to pause cleanly
    until the user re-authenticates (e.g. via ``python main.py login`` or the web UI)
    or until a transient backend outage resolves.
    """
    initial_cached = _load_token_config(config_path)
    failed_refresh = initial_cached.get("refresh_token")
    last_refresh_try = time.monotonic()

    if on_waiting is not None:
        try:
            on_waiting()
        except Exception:
            pass

    while True:
        if stop_event is not None and stop_event.is_set():
            raise AuthError("Cancelled while waiting for re-authentication")

        fresh = read_valid_cached_token(
            config_path, min_ttl_seconds=60.0, rejected_token=rejected_token
        )
        if fresh:
            return fresh

        current_refresh = _load_token_config(config_path).get("refresh_token")
        now_mono = time.monotonic()
        if current_refresh and (
            current_refresh != failed_refresh
            or (now_mono - last_refresh_try) >= refresh_retry_interval
        ):
            last_refresh_try = now_mono
            refreshed = refresh_access_token(
                base_url,
                config_path,
                max_retries=1,
                rejected_token=rejected_token,
            )
            if refreshed:
                return refreshed
            failed_refresh = current_refresh

        if stop_event is not None:
            if stop_event.wait(timeout=poll_interval):
                raise AuthError("Cancelled while waiting for re-authentication")
        else:
            time.sleep(poll_interval)


async def wait_for_reauth_async(
    base_url: str,
    config_path: Path,
    *,
    poll_interval: float = 3.0,
    refresh_retry_interval: float = 60.0,
    should_stop: Optional[Callable[[], bool]] = None,
    wake_event: Optional[asyncio.Event] = None,
    rejected_token: Optional[str] = None,
    on_waiting: Optional[Callable[[], None]] = None,
) -> str:
    """Async version of :func:`wait_for_reauth_sync` that wakes immediately on ``wake_event``."""
    initial_cached = _load_token_config(config_path)
    failed_refresh = initial_cached.get("refresh_token")
    last_refresh_try = time.monotonic()

    if on_waiting is not None:
        try:
            on_waiting()
        except Exception:
            pass

    while True:
        if wake_event is not None:
            wake_event.clear()

        if should_stop is not None and should_stop():
            raise AuthError("Cancelled while waiting for re-authentication")

        fresh = read_valid_cached_token(
            config_path, min_ttl_seconds=60.0, rejected_token=rejected_token
        )
        if fresh:
            return fresh

        current_refresh = _load_token_config(config_path).get("refresh_token")
        now_mono = time.monotonic()
        if current_refresh and (
            current_refresh != failed_refresh
            or (now_mono - last_refresh_try) >= refresh_retry_interval
        ):
            last_refresh_try = now_mono
            refreshed = await asyncio.to_thread(
                refresh_access_token,
                base_url,
                config_path,
                max_retries=1,
                rejected_token=rejected_token,
            )
            if refreshed:
                return refreshed
            failed_refresh = current_refresh

        if wake_event is not None:
            try:
                await asyncio.wait_for(wake_event.wait(), timeout=poll_interval)
            except asyncio.TimeoutError:
                pass
        else:
            await asyncio.sleep(poll_interval)
