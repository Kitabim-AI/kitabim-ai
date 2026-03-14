import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.chat_limit_service import ChatLimitService
from app.models.user import User, UserRole

@pytest.mark.asyncio
async def test_chat_limit_increment_syncs_to_redis_and_db(monkeypatch):
    # mocks
    mock_db_repo = AsyncMock()
    mock_db_repo.increment_usage = AsyncMock(return_value=5)
    
    mock_cache = AsyncMock()
    mock_redis_client = AsyncMock()
    mock_cache.get_client = AsyncMock(return_value=mock_redis_client)
    
    # Mocking UserRepository and Session
    monkeypatch.setattr("app.services.chat_limit_service.UserChatUsageRepository", lambda s: mock_db_repo)
    monkeypatch.setattr("app.services.chat_limit_service.cache_service", mock_cache)
    
    service = ChatLimitService()
    user = MagicMock(spec=User)
    user.id = "user123"
    user.role = UserRole.READER
    
    # Run
    new_count = await service.increment_usage(user, AsyncMock())
    
    # Verify DB increment
    mock_db_repo.increment_usage.assert_called_once_with("user123")
    assert new_count == 5
    
    # Verify Redis increment (via eval)
    mock_redis_client.eval.assert_called_once()
    # Check that Eval was called with the correct Lua script and key
    args, kwargs = mock_redis_client.eval.call_args
    assert "redis.call('INCR', KEYS[1])" in args[0]
    assert "user123" in args[2]

@pytest.mark.asyncio
async def test_get_usage_checks_cache_first(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=3)
    
    mock_db_repo = AsyncMock()
    monkeypatch.setattr("app.services.chat_limit_service.UserChatUsageRepository", lambda s: mock_db_repo)
    monkeypatch.setattr("app.services.chat_limit_service.cache_service", mock_cache)
    
    service = ChatLimitService()
    usage = await service.get_usage("user123", AsyncMock())
    
    assert usage == 3
    mock_cache.get.assert_called_once()
    mock_db_repo.get_usage.assert_not_called()

@pytest.mark.asyncio
async def test_get_usage_falls_back_to_db_and_backfills(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    
    mock_db_repo = AsyncMock()
    mock_db_repo.get_usage = AsyncMock(return_value=12)
    
    monkeypatch.setattr("app.services.chat_limit_service.UserChatUsageRepository", lambda s: mock_db_repo)
    monkeypatch.setattr("app.services.chat_limit_service.cache_service", mock_cache)
    
    service = ChatLimitService()
    usage = await service.get_usage("user123", AsyncMock())
    
    assert usage == 12
    mock_cache.get.assert_called_once()
    mock_db_repo.get_usage.assert_called_once_with("user123")
    # Backfill
    mock_cache.set.assert_called_once()
    args, kwargs = mock_cache.set.call_args
    assert args[1] == 12
