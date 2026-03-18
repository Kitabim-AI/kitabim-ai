import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import date
from app.db.repositories.user_chat_usage import UserChatUsageRepository, get_user_chat_usage_repository
from app.db.models import UserChatUsage

@pytest.mark.asyncio
async def test_get_usage():
    session = AsyncMock()
    repo = UserChatUsageRepository(session)
    user_id = "test-user"
    
    mock_res = MagicMock()
    mock_res.scalar.return_value = 5
    session.execute.return_value = mock_res
    
    usage = await repo.get_usage(user_id)
    assert usage == 5
    
    mock_res.scalar.return_value = None
    usage = await repo.get_usage(user_id)
    assert usage == 0

@pytest.mark.asyncio
async def test_increment_usage_existing():
    session = AsyncMock()
    repo = UserChatUsageRepository(session)
    user_id = "test-user"
    
    mock_usage = UserChatUsage(user_id=user_id, count=5, usage_date=date.today())
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_usage
    session.execute.return_value = mock_res
    
    count = await repo.increment_usage(user_id)
    assert count == 6
    assert mock_usage.count == 6
    assert session.commit.called

@pytest.mark.asyncio
async def test_increment_usage_new():
    session = AsyncMock()
    session.add = MagicMock()
    repo = UserChatUsageRepository(session)
    user_id = "new-user"
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    
    count = await repo.increment_usage(user_id)
    assert count == 1
    assert session.add.called
    assert session.commit.called

def test_get_user_chat_usage_repository():
    session = MagicMock()
    repo = get_user_chat_usage_repository(session)
    assert isinstance(repo, UserChatUsageRepository)
