import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from datetime import datetime, timedelta, timezone
from app.db.repositories.refresh_tokens import RefreshTokensRepository
from app.db.models import RefreshToken

@pytest.mark.asyncio
async def test_get_by_jti():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    jti = uuid4()
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = RefreshToken(jti=jti)
    session.execute.return_value = mock_res
    
    res = await repo.get_by_jti(jti)
    assert res.jti == jti

@pytest.mark.asyncio
async def test_find_valid_token():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    jti = uuid4()
    
    mock_res = MagicMock()
    mock_token = RefreshToken(jti=jti, token_hash="hash", revoked=False)
    mock_res.scalar_one_or_none.return_value = mock_token
    session.execute.return_value = mock_res
    
    res = await repo.find_valid(jti, "hash")
    assert res == mock_token

@pytest.mark.asyncio
async def test_revoke_by_jti():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    jti = uuid4()
    
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res
    
    res = await repo.revoke_by_jti(jti)
    assert res is True
    assert session.flush.called

@pytest.mark.asyncio
async def test_revoke_all_for_user():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    user_id = uuid4()
    
    mock_res = MagicMock()
    mock_res.rowcount = 3
    session.execute.return_value = mock_res
    
    res = await repo.revoke_all_for_user(user_id)
    assert res == 3

@pytest.mark.asyncio
async def test_delete_expired_or_revoked():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    
    mock_res = MagicMock()
    mock_res.rowcount = 5
    session.execute.return_value = mock_res
    
    res = await repo.delete_expired_or_revoked()
    assert res == 5
