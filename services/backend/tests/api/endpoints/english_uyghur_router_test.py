import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def _mock_admin():
    from app.models.user import User, UserRole

    return User(
        id="admin-1",
        email="admin@example.com",
        display_name="Admin",
        role=UserRole.ADMIN,
        provider="google",
        provider_id="admin-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


@pytest.mark.asyncio
async def test_delete_english_uyghur_entry():
    setup_paths()
    from api.endpoints.english_uyghur_router import delete_english_uyghur_entry

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = (1,)
    mock_session.execute.return_value = mock_res

    result = await delete_english_uyghur_entry(
        entry_id=1, session=mock_session, current_user=_mock_admin()
    )

    assert result is None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_english_uyghur_entry_not_found():
    setup_paths()
    from api.endpoints.english_uyghur_router import delete_english_uyghur_entry
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = None
    mock_session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await delete_english_uyghur_entry(
            entry_id=999, session=mock_session, current_user=_mock_admin()
        )

    assert exc_info.value.status_code == 404
    mock_session.commit.assert_not_called()
