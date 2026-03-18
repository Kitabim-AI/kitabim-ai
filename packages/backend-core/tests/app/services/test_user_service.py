import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from app.services.user_service import (
    get_user_by_id,
    get_user_by_email,
    get_user_by_provider,
    create_user,
    update_user_login,
    update_user_role,
    update_user_status,
    list_users
)
from app.models.user import UserRole
from app.db.models import User as UserDB

@pytest.fixture
def mock_user_db():
    u = UserDB(
        id=uuid4(),
        email="test@example.com",
        display_name="Test User",
        role="reader",
        provider="google",
        provider_id="123",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    return u

@pytest.mark.asyncio
async def test_get_user_by_id(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=mock_user_db)
        
        user = await get_user_by_id(session, str(mock_user_db.id))
        assert user.email == mock_user_db.email

@pytest.mark.asyncio
async def test_get_user_by_email(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_email = AsyncMock(return_value=mock_user_db)
        
        user = await get_user_by_email(session, "test@example.com")
        assert user.email == mock_user_db.email

@pytest.mark.asyncio
async def test_get_user_by_provider(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_by_provider = AsyncMock(return_value=mock_user_db)
        
        user = await get_user_by_provider(session, "google", "123")
        assert user.provider_id == "123"

@pytest.mark.asyncio
async def test_create_user():
    session = AsyncMock()
    with patch("app.utils.security.hash_ip_if_present", return_value="hashed_ip"):
        user = await create_user(
            session,
            email="new@example.com",
            display_name="New User",
            provider="google",
            provider_id="456",
            role=UserRole.READER,
            last_login_ip="1.2.3.4"
        )
        assert user.email == "new@example.com"
        assert session.add.called
        assert session.flush.called

@pytest.mark.asyncio
async def test_update_user_login():
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.update_one = AsyncMock(return_value=True)
        
        await update_user_login(session, "user-id", avatar_url="new-url", ip_address="1.2.3.4")
        assert mock_repo.update_one.called

@pytest.mark.asyncio
async def test_update_user_role(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.update_one = AsyncMock(return_value=True)
        mock_repo.get = AsyncMock(return_value=mock_user_db)
        
        user = await update_user_role(session, "user-id", UserRole.ADMIN)
        assert user is not None

@pytest.mark.asyncio
async def test_update_user_status(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.update_one = AsyncMock(return_value=True)
        mock_repo.get = AsyncMock(return_value=mock_user_db)
        
        user = await update_user_status(session, "user-id", False)
        assert user is not None

@pytest.mark.asyncio
async def test_list_users(mock_user_db):
    session = AsyncMock()
    with patch("app.services.user_service.UsersRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_many = AsyncMock(return_value=[mock_user_db])
        mock_repo.count_by_role = AsyncMock(return_value=1)
        
        users, total = await list_users(session, page=1, page_size=10, filter_dict={"role": "reader"})
        assert len(users) == 1
        assert total == 1
