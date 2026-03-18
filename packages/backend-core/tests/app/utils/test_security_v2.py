import pytest
from unittest.mock import patch, MagicMock
from app.utils.security import hash_ip_address, hash_ip_if_present

@pytest.fixture
def mock_settings():
    with patch("app.utils.security.settings") as m:
        m.ip_salt = "pepper"
        yield m

def test_hash_ip_address_with_salt(mock_settings):
    ip = "1.2.3.4"
    h1 = hash_ip_address(ip)
    assert len(h1) == 16
    
    mock_settings.ip_salt = "salt2"
    h2 = hash_ip_address(ip)
    assert h2 != h1

def test_hash_ip_address_no_salt():
    with patch("app.utils.security.settings") as m:
        m.ip_salt = None
        ip = "1.2.3.4"
        h = hash_ip_address(ip)
        assert len(h) == 16

def test_hash_ip_if_present():
    assert hash_ip_if_present(None) is None
    assert hash_ip_if_present("5.6.7.8") is not None

def test_hash_ip_address_empty():
    assert hash_ip_address("") == ""
    assert hash_ip_address(None) == ""
