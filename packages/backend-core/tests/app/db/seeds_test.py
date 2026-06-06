import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.db.seeds import seed_system_configs

@pytest.mark.asyncio
async def test_seed_system_configs():
    session = AsyncMock()
    with patch("app.db.seeds.SystemConfigsRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        # Mock get to return None (not existing)
        mock_repo.get = AsyncMock(return_value=None)
        mock_repo.create = AsyncMock()
        
        await seed_system_configs(session)
        assert mock_repo.create.called
        assert session.commit.called

@pytest.mark.asyncio
async def test_seed_system_configs_existing():
    session = AsyncMock()
    with patch("app.db.seeds.SystemConfigsRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        # Mock get to return something (existing)
        mock_repo.get = AsyncMock(return_value=MagicMock())
        mock_repo.create = AsyncMock()
        
        await seed_system_configs(session)
        assert not mock_repo.create.called


