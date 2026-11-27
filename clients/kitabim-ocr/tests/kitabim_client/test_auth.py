import base64
import json
import time
from pathlib import Path
from unittest.mock import patch


from kitabim_client import auth


def _fake_jwt(exp: float) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def test_jwt_exp_decodes_expiry_claim():
    token = _fake_jwt(exp=1234567890.0)
    assert auth._jwt_exp(token) == 1234567890.0


def test_jwt_exp_returns_none_for_malformed_token():
    assert auth._jwt_exp("not-a-jwt") is None


def test_get_valid_token_returns_cached_token_when_not_expired(tmp_path: Path):
    config_path = tmp_path / "token.json"
    token = _fake_jwt(exp=time.time() + 3600)
    config_path.write_text(json.dumps({"access_token": token}))

    with patch("kitabim_client.auth._login") as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == token
    mock_login.assert_not_called()


def test_get_valid_token_relogs_in_when_cached_token_expired(tmp_path: Path):
    config_path = tmp_path / "token.json"
    old_token = _fake_jwt(exp=time.time() - 10)
    config_path.write_text(json.dumps({"access_token": old_token}))

    new_token = _fake_jwt(exp=time.time() + 3600)
    with patch("kitabim_client.auth._login", return_value=new_token) as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == new_token
    mock_login.assert_called_once()
    assert json.loads(config_path.read_text())["access_token"] == new_token


def test_get_valid_token_logs_in_when_no_cache_exists(tmp_path: Path):
    config_path = tmp_path / "token.json"
    new_token = _fake_jwt(exp=time.time() + 3600)

    with patch("kitabim_client.auth._login", return_value=new_token) as mock_login:
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == new_token
    mock_login.assert_called_once()


def test_get_valid_token_auto_refreshes_using_refresh_token(tmp_path: Path):
    from unittest.mock import MagicMock

    config_path = tmp_path / "token.json"
    expiring_soon = _fake_jwt(exp=time.time() + 120)
    config_path.write_text(
        json.dumps({"access_token": expiring_soon, "refresh_token": "ref_old"})
    )

    refreshed_access = _fake_jwt(exp=time.time() + 3600)
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "access_token": refreshed_access,
        "refresh_token": "ref_new",
    }

    with (
        patch("kitabim_client.auth.httpx.post", return_value=mock_res) as mock_post,
        patch("kitabim_client.auth._login") as mock_login,
    ):
        result = auth.get_valid_token("http://localhost:8000", config_path)

    assert result == refreshed_access
    mock_login.assert_not_called()
    mock_post.assert_called_once()
    saved = json.loads(config_path.read_text())
    assert saved["access_token"] == refreshed_access
    assert saved["refresh_token"] == "ref_old"


def test_get_valid_token_headless_raises_auth_error_without_browser(tmp_path: Path):
    import pytest

    config_path = tmp_path / "token.json"
    expired = _fake_jwt(exp=time.time() - 60)
    config_path.write_text(json.dumps({"access_token": expired}))

    with patch("kitabim_client.auth._login") as mock_login:
        with pytest.raises(auth.AuthError, match="python main.py login"):
            auth.get_valid_token("http://localhost:8000", config_path, headless=True)

    mock_login.assert_not_called()


def test_refresh_access_token_retries_transient_errors_and_succeeds(tmp_path: Path):
    from unittest.mock import MagicMock

    config_path = tmp_path / "token.json"
    expired = _fake_jwt(exp=time.time() - 10)
    config_path.write_text(
        json.dumps({"access_token": expired, "refresh_token": "ref_valid"})
    )

    fresh = _fake_jwt(exp=time.time() + 3600)
    transient_503 = MagicMock(status_code=503)
    ok_200 = MagicMock(status_code=200)
    ok_200.json.return_value = {"access_token": fresh}

    with (
        patch(
            "kitabim_client.auth.httpx.post",
            side_effect=[RuntimeError("connection reset"), transient_503, ok_200],
        ) as mock_post,
        patch("kitabim_client.auth.time.sleep") as mock_sleep,
    ):
        result = auth.refresh_access_token(
            "http://localhost:8000", config_path, max_retries=3, retry_backoff=0.01
        )

    assert result == fresh
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2
    saved = json.loads(config_path.read_text())
    assert saved["access_token"] == fresh
    assert saved["refresh_token"] == "ref_valid"


def test_refresh_access_token_does_not_retry_on_401(tmp_path: Path):
    from unittest.mock import MagicMock

    config_path = tmp_path / "token.json"
    config_path.write_text(
        json.dumps(
            {"access_token": _fake_jwt(time.time() - 10), "refresh_token": "ref_dead"}
        )
    )

    resp_401 = MagicMock(status_code=401)
    with patch("kitabim_client.auth.httpx.post", return_value=resp_401) as mock_post:
        result = auth.refresh_access_token(
            "http://localhost:8000", config_path, max_retries=3, retry_backoff=0.01
        )

    assert result is None
    assert mock_post.call_count == 1


def test_refresh_access_token_returns_fresher_disk_token_without_network(
    tmp_path: Path,
):
    config_path = tmp_path / "token.json"
    old_tok = _fake_jwt(exp=time.time() + 1800)
    newer_tok = _fake_jwt(exp=time.time() + 3600)
    config_path.write_text(
        json.dumps({"access_token": newer_tok, "refresh_token": "ref_ok"})
    )

    with patch("kitabim_client.auth.httpx.post") as mock_post:
        result = auth.refresh_access_token(
            "http://localhost:8000", config_path, rejected_token=old_tok
        )

    assert result == newer_tok
    mock_post.assert_not_called()


def test_wait_for_reauth_async_resumes_when_fresh_token_written_to_disk(tmp_path: Path):
    import asyncio

    config_path = tmp_path / "token.json"
    expired = _fake_jwt(exp=time.time() - 60)
    config_path.write_text(json.dumps({"access_token": expired}))
    fresh = _fake_jwt(exp=time.time() + 3600)

    async def _run():
        wake = asyncio.Event()

        async def _writer():
            await asyncio.sleep(0.03)
            auth._save_token_config(config_path, fresh, refresh_token="ref_new")
            wake.set()

        writer_task = asyncio.create_task(_writer())
        tok = await auth.wait_for_reauth_async(
            "http://localhost:8000",
            config_path,
            poll_interval=0.05,
            wake_event=wake,
        )
        await writer_task
        return tok

    assert asyncio.run(_run()) == fresh


def test_get_token_status_reports_validity_without_exposing_secrets(tmp_path: Path):
    config_path = tmp_path / "token.json"
    valid_access = _fake_jwt(exp=time.time() + 1800)
    expired_refresh = _fake_jwt(exp=time.time() - 10)
    config_path.write_text(
        json.dumps({"access_token": valid_access, "refresh_token": expired_refresh})
    )

    status = auth.get_token_status(config_path)
    assert status["hasAccessToken"] is True
    assert status["accessValid"] is True
    assert status["hasRefreshToken"] is True
    assert status["refreshValid"] is False
    assert status["authenticated"] is True
    assert valid_access not in json.dumps(status)
    assert expired_refresh not in json.dumps(status)
