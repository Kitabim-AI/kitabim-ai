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
async def test_update_proverb():
    setup_paths()
    from api.endpoints.proverbs_router import update_proverb, ProverbUpdate
    from app.db.models import Proverb
    from app.models.user import User, UserRole

    mock_session = AsyncMock()
    mock_proverb = Proverb(id=1, text="Original Proverb Text", volume=1, page_number=10)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_proverb
    mock_session.execute.return_value = mock_res

    mock_editor = User(
        id="editor-10",
        email="editor@example.com",
        display_name="Editor",
        role=UserRole.EDITOR,
        provider="google",
        provider_id="editor-10",
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )
    update_body = ProverbUpdate(text="Corrected Uyghur Proverb")

    with patch(
        "app.services.cache_service.cache_service.delete_pattern",
        new_callable=AsyncMock,
    ) as mock_delete:
        result = await update_proverb(
            proverb_id=1,
            body=update_body,
            session=mock_session,
            current_user=mock_editor,
        )

        assert result.text == "Corrected Uyghur Proverb"
        assert result.volume == 1
        assert result.page_number == 10
        mock_session.commit.assert_called_once()
        mock_delete.assert_any_call("proverb:*")
        mock_delete.assert_any_call("proverbs:*")


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
async def test_delete_proverb():
    setup_paths()
    from api.endpoints.proverbs_router import delete_proverb

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = (1,)
    mock_session.execute.return_value = mock_res

    with patch(
        "app.services.cache_service.cache_service.delete_pattern",
        new_callable=AsyncMock,
    ) as mock_delete:
        result = await delete_proverb(
            proverb_id=1, session=mock_session, current_user=_mock_admin()
        )

        assert result is None
        mock_session.commit.assert_called_once()
        mock_delete.assert_any_call("proverb:*")
        mock_delete.assert_any_call("proverbs:*")


@pytest.mark.asyncio
async def test_delete_proverb_not_found():
    setup_paths()
    from api.endpoints.proverbs_router import delete_proverb
    from fastapi import HTTPException

    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchone.return_value = None
    mock_session.execute.return_value = mock_res

    with pytest.raises(HTTPException) as exc_info:
        await delete_proverb(
            proverb_id=999, session=mock_session, current_user=_mock_admin()
        )

    assert exc_info.value.status_code == 404
    mock_session.commit.assert_not_called()
