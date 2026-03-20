import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone
from app.services.chat_limit_service import ChatLimitService
from app.models.user import UserRole, User

@pytest.fixture
def chat_limit_service():
    return ChatLimitService()

@pytest.fixture
def mock_user():
    return User(
        id="user-123", 
        email="t@e.com", 
        display_name="T", 
        role=UserRole.READER,
        provider="google",
        provider_id="123",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )

@pytest.mark.asyncio
async def test_get_limit_for_role_admin(chat_limit_service):
    session = AsyncMock()
    limit = await chat_limit_service.get_limit_for_role(UserRole.ADMIN, session)
    assert limit is None

@pytest.mark.asyncio
async def test_get_limit_for_role_reader(chat_limit_service):
    session = AsyncMock()
    with patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", return_value="50"):
        limit = await chat_limit_service.get_limit_for_role(UserRole.READER, session)
        assert limit == 50

@pytest.mark.asyncio
async def test_get_limit_fallback(chat_limit_service):
    session = AsyncMock()
    # Mock exception
    with patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", side_effect=Exception("fail")):
        limit = await chat_limit_service.get_limit_for_role(UserRole.EDITOR, session)
        assert limit == 100

@pytest.mark.asyncio
async def test_get_usage_redis_hit(chat_limit_service):
    session = AsyncMock()
    with patch("app.services.cache_service.cache_service.get", return_value="15"):
        usage = await chat_limit_service.get_usage("user-123", session)
        assert usage == 15

@pytest.mark.asyncio
async def test_get_usage_redis_miss_db_hit(chat_limit_service):
    session = AsyncMock()
    with patch("app.services.cache_service.cache_service.get", return_value=None):
        with patch("app.db.repositories.user_chat_usage.UserChatUsageRepository.get_usage", return_value=7):
            with patch("app.services.cache_service.cache_service.set", return_value=None) as mock_set:
                usage = await chat_limit_service.get_usage("user-123", session)
                assert usage == 7
                assert mock_set.called

@pytest.mark.asyncio
async def test_is_within_limit(chat_limit_service, mock_user):
    session = AsyncMock()
    with patch.object(chat_limit_service, "get_limit_for_role", return_value=10):
        with patch.object(chat_limit_service, "get_usage", return_value=5):
            assert await chat_limit_service.is_within_limit(mock_user, session) is True
        
        with patch.object(chat_limit_service, "get_usage", return_value=10):
            assert await chat_limit_service.is_within_limit(mock_user, session) is False

@pytest.mark.asyncio
async def test_increment_usage(chat_limit_service, mock_user):
    session = AsyncMock()
    with patch("app.db.repositories.user_chat_usage.UserChatUsageRepository.increment_usage", return_value=6):
        with patch("app.services.cache_service.cache_service.get_client", return_value=AsyncMock()) as mock_client:
            res = await chat_limit_service.increment_usage(mock_user, session)
            assert res == 6
            assert mock_client.called

@pytest.mark.asyncio
async def test_get_user_usage_status(chat_limit_service, mock_user):
    session = AsyncMock()
    with patch.object(chat_limit_service, "get_limit_for_role", return_value=10):
        with patch.object(chat_limit_service, "get_usage", return_value=3):
            status = await chat_limit_service.get_user_usage_status(mock_user, session)
            assert status["usage"] == 3
            assert status["limit"] == 10
            assert status["has_reached_limit"] is False
