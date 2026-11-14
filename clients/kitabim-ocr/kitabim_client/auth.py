from __future__ import annotations

import base64
import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

import httpx

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


def _save_token_config(
    config_path: Path, access_token: str, refresh_token: Optional[str] = None
) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, str] = {"access_token": access_token}
    if refresh_token:
        payload["refresh_token"] = refresh_token
    config_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass


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


def refresh_access_token(base_url: str, config_path: Path) -> Optional[str]:
    """Use the stored non-rotating ``refresh_token`` to mint a fresh access token."""
    if not config_path.exists():
        return None
    try:
        cached = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    refresh_token = cached.get("refresh_token")
    if not refresh_token:
        return None
    try:
        response = httpx.post(
            f"{base_url.rstrip('/')}/auth/refresh",
            json={"refresh_token": refresh_token},
            timeout=15.0,
        )
        if response.status_code != 200:
            return None
        body = response.json()
        new_access = body.get("access_token")
        if not new_access:
            return None
        _save_token_config(config_path, new_access, refresh_token=refresh_token)
        return str(new_access)
    except Exception:
        return None


def login_and_save(
    base_url: str, config_path: Path, provider: str = "google", timeout: float = 120.0
) -> dict[str, Optional[str]]:
    """Run interactive loopback OAuth login and save ``{access_token, refresh_token}`` (`0600`)."""
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
) -> str:
    global _LAST_CAPTURED_REFRESH_TOKEN
    existing_refresh: Optional[str] = None
    if config_path.exists():
        try:
            cached = json.loads(config_path.read_text(encoding="utf-8"))
        except Exception:
            cached = {}
        token = cached.get("access_token")
        existing_refresh = cached.get("refresh_token")
        exp = _jwt_exp(token) if token else None
        if token and exp and exp > time.time() + 300:
            return token
        if existing_refresh:
            refreshed = refresh_access_token(base_url, config_path)
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
