import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from app.db.repositories.users import UsersRepository, get_users_repository, RefreshTokensRepository, get_refresh_tokens_repository
from app.db.models import User, RefreshToken

@pytest.mark.asyncio
async def test_find_by_email():
    session = AsyncMock()
    repo = UsersRepository(session)
    email = "test@example.com"
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = User(id=uuid4(), email=email)
    session.execute.return_value = mock_res
    
    res = await repo.find_by_email(email)
    assert res.email == email

@pytest.mark.asyncio
async def test_find_by_provider():
    session = AsyncMock()
    repo = UsersRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = User(id=uuid4(), provider="google", provider_id="123")
    session.execute.return_value = mock_res
    
    res = await repo.find_by_provider("google", "123")
    assert res is not None
    assert res.provider_id == "123"

@pytest.mark.asyncio
async def test_find_many_users():
    session = AsyncMock()
    repo = UsersRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [User(id=uuid4())]
    session.execute.return_value = mock_res
    
    res = await repo.find_many(role="user", is_active=True, search="test")
    assert len(res) == 1

@pytest.mark.asyncio
async def test_update_last_login():
    session = AsyncMock()
    repo = UsersRepository(session)
    user_id = uuid4()
    
    with patch.object(repo, "update_one", return_value=None) as mock_update:
        await repo.update_last_login(user_id, ip_address="1.2.3.4")
        assert mock_update.called



@pytest.mark.asyncio
async def test_count_by_role():
    session = AsyncMock()
    repo = UsersRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 10
    session.execute.return_value = mock_res
    
    count = await repo.count_by_role(role="admin", search="find")
    assert count == 10

@pytest.mark.asyncio
async def test_users_refresh_tokens_repo():
    session = AsyncMock()
    repo = RefreshTokensRepository(session)
    user_id = uuid4()
    
    # find_by_jti
    jti = uuid4()
    with patch.object(repo, "get", return_value=RefreshToken(jti=jti)):
        res = await repo.find_by_jti(jti)
        assert res.jti == jti
    
    # find_by_user
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [RefreshToken(user_id=user_id)]
    session.execute.return_value = mock_res
    res = await repo.find_by_user(user_id)
    assert len(res) == 1
    
    # delete_by_user
    mock_res.rowcount = 2
    res = await repo.delete_by_user(user_id)
    assert res == 2
    
    # delete_expired
    res = await repo.delete_expired()
    assert res == 2

def test_get_user_factories():
    session = MagicMock()
    assert isinstance(get_users_repository(session), UsersRepository)
    assert isinstance(get_refresh_tokens_repository(session), RefreshTokensRepository)
