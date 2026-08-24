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
        mock_repo.delete_one = AsyncMock()

        await seed_system_configs(session)
        assert not mock_repo.create.called


@pytest.mark.asyncio
async def test_seed_system_configs_migrates_legacy_key():
    session = AsyncMock()
    legacy_config = MagicMock(value="legacy-value", description="legacy description")

    async def mock_get(key):
        if key == "gemini_chat_model":
            return legacy_config
        return None

    with patch("app.db.seeds.SystemConfigsRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(side_effect=mock_get)
        mock_repo.create = AsyncMock()
        mock_repo.delete_one = AsyncMock()

        await seed_system_configs(session)

        mock_repo.create.assert_any_await(
            key="rag_gemini_chat_model",
            value="legacy-value",
            description="legacy description",
        )
        mock_repo.delete_one.assert_any_await("gemini_chat_model")
        assert session.commit.called
