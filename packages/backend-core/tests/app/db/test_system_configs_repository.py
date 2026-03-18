import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.system_configs import SystemConfigsRepository
from app.db.models import SystemConfig

@pytest.mark.asyncio
async def test_get_value_cached():
    session = AsyncMock()
    repo = SystemConfigsRepository(session)
    
    with patch("app.db.repositories.system_configs.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value="cached_val")
        
        val = await repo.get_value("test_key")
        assert val == "cached_val"
        mock_cache.get.assert_called_with("config:test_key")

@pytest.mark.asyncio
async def test_get_value_db():
    session = AsyncMock()
    repo = SystemConfigsRepository(session)
    
    with patch("app.db.repositories.system_configs.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()
        # Mock repo.get which is call to base repository
        repo.get = AsyncMock(return_value=SystemConfig(key="test_key", value="db_val"))
        
        val = await repo.get_value("test_key")
        assert val == "db_val"
        mock_cache.set.assert_called()

@pytest.mark.asyncio
async def test_set_value_update():
    session = AsyncMock()
    repo = SystemConfigsRepository(session)
    
    mock_config = SystemConfig(key="key", value="old")
    repo.get = AsyncMock(return_value=mock_config)
    
    with patch("app.db.repositories.system_configs.cache_service") as mock_cache:
        mock_cache.delete = AsyncMock()
        await repo.set_value("key", "new", "desc")
        
        assert mock_config.value == "new"
        assert mock_config.description == "desc"
        assert session.commit.called
        mock_cache.delete.assert_called_with("config:key")

@pytest.mark.asyncio
async def test_set_value_create():
    session = AsyncMock()
    repo = SystemConfigsRepository(session)
    
    repo.get = AsyncMock(return_value=None)
    repo.create = AsyncMock(return_value=SystemConfig(key="key", value="new"))
    
    with patch("app.db.repositories.system_configs.cache_service") as mock_cache:
        mock_cache.delete = AsyncMock()
        config = await repo.set_value("key", "new")
        
        assert config.key == "key"
        repo.create.assert_called()
        mock_cache.delete.assert_called_with("config:key")
