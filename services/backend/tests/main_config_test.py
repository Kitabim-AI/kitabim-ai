import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, patch

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[3] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api.") or m == "main":
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_get_public_config_returns_collection_page_size():
    setup_paths()
    from main import get_public_config

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_value = AsyncMock(return_value="55")

    with patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository",
        return_value=mock_repo,
    ):
        result = await get_public_config(session=mock_session)

    assert result["collectionPageSize"] == 55
    assert "appId" in result


@pytest.mark.asyncio
async def test_get_public_config_falls_back_to_40_when_config_missing():
    setup_paths()
    from main import get_public_config

    mock_session = AsyncMock()
    mock_repo = AsyncMock()
    mock_repo.get_value = AsyncMock(return_value="40")

    with patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository",
        return_value=mock_repo,
    ):
        result = await get_public_config(session=mock_session)

    assert result["collectionPageSize"] == 40
