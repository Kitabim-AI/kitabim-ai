from __future__ import annotations

import base64
import json
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlencode, urlparse, parse_qs

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
                if token:
                    result_holder["token"] = token
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

    return result_holder["token"]


def get_valid_token(base_url: str, config_path: Path, provider: str = "google") -> str:
    if config_path.exists():
        cached = json.loads(config_path.read_text())
        token = cached.get("access_token")
        exp = _jwt_exp(token) if token else None
        if token and exp and exp > time.time() + 30:
            return token

    token = _login(base_url, provider)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps({"access_token": token}))
    return token
