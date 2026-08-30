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
