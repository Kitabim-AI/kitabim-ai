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
async def test_delete_history_entry():
    setup_paths()
    from api.endpoints.history_dictionary_router import delete_history_entry

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = (1,)
    mock_session.execute.return_value = mock_res

    result = await delete_history_entry(
        entry_id=1, session=mock_session, current_user=_mock_admin()
    )

    assert result is None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_history_entry_not_found():
    setup_paths()
    from api.endpoints.history_dictionary_router import delete_history_entry
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = None
    mock_session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await delete_history_entry(
            entry_id=999, session=mock_session, current_user=_mock_admin()
        )

    assert exc_info.value.status_code == 404
    mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_search_history_dictionary():
    setup_paths()
    from api.endpoints.history_dictionary_router import search_history_dictionary

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_item = MagicMock()
    mock_item.id = 1
    mock_item.term = "كاسى"
    mock_item.transliteration = "Kasi"
    mock_item.definition = "ھىندىستاندىكى قەدىمكى دۆلەت"
    mock_item.letter_group = "ك"

    mock_res.scalars.return_value.all.return_value = [mock_item]
    mock_session.execute.return_value = mock_res

    res = await search_history_dictionary(q="دۆلەت", limit=10, session=mock_session)

    assert len(res) == 1
    assert res[0].term == "كاسى"
    mock_session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_search_history_dictionary_empty_query():
    setup_paths()
    from api.endpoints.history_dictionary_router import search_history_dictionary

    mock_session = AsyncMock()
    res = await search_history_dictionary(q="   ", limit=10, session=mock_session)

    assert res == []
    mock_session.execute.assert_not_called()
