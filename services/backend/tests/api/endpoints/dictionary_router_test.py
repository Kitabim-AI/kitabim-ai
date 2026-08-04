import sys
from pathlib import Path
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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


@pytest.mark.asyncio
async def test_check_spelling_known_word():
    setup_paths()
    from api.endpoints.dictionary_router import check_spelling

    mock_session = AsyncMock()
    with patch(
        "app.db.repositories.dictionary_repository.DictionaryRepository.check_word_spelling",
        new_callable=AsyncMock,
        return_value={"is_known": True, "word": "كىتاب", "suggestions": []},
    ):
        result = await check_spelling(word="كىتاب", session=mock_session)

    assert result.is_known is True
    assert result.word == "كىتاب"
    assert result.suggestions == []


@pytest.mark.asyncio
async def test_check_spelling_unknown_word_returns_suggestions():
    setup_paths()
    from api.endpoints.dictionary_router import check_spelling

    mock_session = AsyncMock()
    with patch(
        "app.db.repositories.dictionary_repository.DictionaryRepository.check_word_spelling",
        new_callable=AsyncMock,
        return_value={
            "is_known": False,
            "word": "كىتاپ",
            "suggestions": [{"id": 1, "word": "كىتاب", "score": 0.8}],
        },
    ):
        result = await check_spelling(word="كىتاپ", session=mock_session)

    assert result.is_known is False
    assert len(result.suggestions) == 1
    assert result.suggestions[0].word == "كىتاب"


@pytest.mark.asyncio
async def test_delete_dictionary_entry():
    setup_paths()
    from api.endpoints.dictionary_router import delete_dictionary_entry
    from app.models.user import User, UserRole

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = (1,)
    mock_session.execute.return_value = mock_res

    mock_admin = User(
        id="admin-1",
        email="admin@example.com",
        display_name="Admin",
        role=UserRole.ADMIN,
        provider="google",
        provider_id="admin-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    result = await delete_dictionary_entry(
        entry_id=1, session=mock_session, current_user=mock_admin
    )

    assert result is None
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_dictionary_entry_not_found():
    setup_paths()
    from api.endpoints.dictionary_router import delete_dictionary_entry
    from app.models.user import User, UserRole
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = None
    mock_session.execute.return_value = mock_res

    mock_admin = User(
        id="admin-1",
        email="admin@example.com",
        display_name="Admin",
        role=UserRole.ADMIN,
        provider="google",
        provider_id="admin-1",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )

    with pytest.raises(HTTPException) as exc_info:
        await delete_dictionary_entry(
            entry_id=999, session=mock_session, current_user=mock_admin
        )

    assert exc_info.value.status_code == 404
    mock_session.commit.assert_not_called()
