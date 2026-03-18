import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.services.token_service import (
    hash_token,
    store_refresh_token,
    validate_refresh_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    cleanup_expired_tokens
)
from app.db.models import RefreshToken

def test_hash_token():
    t1 = "test-token"
    h1 = hash_token(t1)
    assert h1 == hash_token(t1)
    assert h1 != hash_token("other")

@pytest.mark.asyncio
async def test_store_refresh_token():
    session = AsyncMock()
    session.add = MagicMock()
    user_id = "user-123"
    jti = "jti-456"
    token = "secret-token"
    
    await store_refresh_token(session, user_id, jti, token, device_info="device")
    assert session.add.called
    assert session.flush.called

@pytest.mark.asyncio
async def test_validate_refresh_token_valid():
    session = AsyncMock()
    jti = "jti-456"
    token = "secret-token"
    token_hash = hash_token(token)
    
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_token = RefreshToken(user_id="user-123", expires_at=datetime.now(timezone.utc) + timedelta(days=1))
        mock_repo.find_valid = AsyncMock(return_value=mock_token)
        
        uid = await validate_refresh_token(session, jti, token)
        assert uid == "user-123"

@pytest.mark.asyncio
async def test_validate_refresh_token_expired():
    session = AsyncMock()
    jti = "jti-456"
    token = "secret-token"
    
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_token = RefreshToken(user_id="user-123", expires_at=datetime.now(timezone.utc) - timedelta(days=1))
        mock_repo.find_valid = AsyncMock(return_value=mock_token)
        
        uid = await validate_refresh_token(session, jti, token)
        assert uid is None

@pytest.mark.asyncio
async def test_validate_refresh_token_not_found():
    session = AsyncMock()
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_valid = AsyncMock(return_value=None)
        
        uid = await validate_refresh_token(session, "jti", "token")
        assert uid is None

@pytest.mark.asyncio
async def test_revoke_refresh_token():
    session = AsyncMock()
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.revoke_by_jti = AsyncMock(return_value=True)
        
        res = await revoke_refresh_token(session, "jti")
        assert res is True

@pytest.mark.asyncio
async def test_revoke_all_user_tokens():
    session = AsyncMock()
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.revoke_all_for_user = AsyncMock(return_value=3)
        
        res = await revoke_all_user_tokens(session, "user-123")
        assert res == 3

@pytest.mark.asyncio
async def test_cleanup_expired_tokens():
    session = AsyncMock()
    with patch("app.services.token_service.RefreshTokensRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.delete_expired_or_revoked = AsyncMock(return_value=5)
        
        res = await cleanup_expired_tokens(session)
        assert res == 5
