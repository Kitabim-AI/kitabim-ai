import os
import pytest
from datetime import datetime, timezone, timedelta
from jose import jwt, JWTError
from app.core.config import Settings
from app.models.user import User, UserRole
from auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_jwt,
    validate_jwt_secret,
    TokenInvalidError,
    TokenExpiredError
)
import auth.jwt_handler

class DummyUser:
    def __init__(self, id, email, display_name, role):
        self.id = id
        self.email = email
        self.display_name = display_name
        self.role = role

def test_jwt_rotation_handling(monkeypatch):
    # Instantiate Settings with keyword arguments directly bypassing defaults
    test_settings = Settings(
        jwt_active_kid="v2",
        jwt_secret_key="legacy_jwt_secret_key_minimum_32_chars_long",
        jwt_rotation_secrets="v1:legacy_jwt_secret_key_minimum_32_chars_long,v2:new_jwt_secret_key_minimum_32_chars_long"
    )
    monkeypatch.setattr(auth.jwt_handler, "settings", test_settings)
    
    # Verify parsing logic of settings.jwt_secrets
    assert test_settings.jwt_active_kid == "v2"
    assert test_settings.jwt_secrets["v1"] == "legacy_jwt_secret_key_minimum_32_chars_long"
    assert test_settings.jwt_secrets["v2"] == "new_jwt_secret_key_minimum_32_chars_long"

    user = DummyUser(
        id="user-123",
        email="test@example.com",
        display_name="Test User",
        role=UserRole.READER
    )

    # 1. Generate token using current active key (v2)
    token = create_access_token(user)
    
    # Verify kid is v2 in the header
    header = jwt.get_unverified_header(token)
    assert header["kid"] == "v2"

    # Decode using decode_jwt (uses v2 secret because kid is v2)
    payload = decode_jwt(token, expected_type="access")
    assert payload["sub"] == "user-123"

    # 2. Simulate token generated with legacy key (v1)
    # manually encode a token signed with the old secret but with kid="v1"
    legacy_payload = {
        "sub": "user-123",
        "email": "test@example.com",
        "role": "reader",
        "display_name": "Test User",
        "type": "access",
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=10),
    }
    legacy_token = jwt.encode(
        legacy_payload, 
        test_settings.jwt_secrets["v1"], 
        algorithm=test_settings.jwt_algorithm,
        headers={"kid": "v1"}
    )

    # Verify we can decode the old token with kid="v1" successfully even when active kid is v2
    legacy_decoded = decode_jwt(legacy_token, expected_type="access")
    assert legacy_decoded["sub"] == "user-123"

    # 3. Verify fallback behavior for missing kid or unknown kid (defaults to jwt_secret_key)
    no_kid_token = jwt.encode(
        legacy_payload,
        test_settings.jwt_secret_key,
        algorithm=test_settings.jwt_algorithm
    )
    no_kid_decoded = decode_jwt(no_kid_token, expected_type="access")
    assert no_kid_decoded["sub"] == "user-123"

    # 4. Verify invalid kid fails if secret is different
    invalid_kid_token = jwt.encode(
        legacy_payload,
        "some_other_secret_minimum_32_chars_long",
        algorithm=test_settings.jwt_algorithm,
        headers={"kid": "unknown_kid"}
    )
    with pytest.raises(TokenInvalidError):
        decode_jwt(invalid_kid_token, expected_type="access")

def test_validate_jwt_secrets_config(monkeypatch):
    # Valid secrets
    test_settings = Settings(
        jwt_secret_key="secret_must_be_at_least_32_chars_long",
        jwt_rotation_secrets="v1:secret_must_be_at_least_32_chars_long"
    )
    monkeypatch.setattr(auth.jwt_handler, "settings", test_settings)
    validate_jwt_secret()  # Should not raise any error

    # Invalid secrets - too short
    test_settings_invalid = Settings(
        jwt_secret_key="short",
        jwt_rotation_secrets="v1:short"
    )
    monkeypatch.setattr(auth.jwt_handler, "settings", test_settings_invalid)
    with pytest.raises(ValueError) as exc:
        validate_jwt_secret()
    assert "at least 32 characters" in str(exc.value)
