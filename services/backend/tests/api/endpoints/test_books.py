import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[3]
BACKEND_CORE_DIR = Path(__file__).resolve().parents[5] / "packages" / "backend-core"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE_DIR))

def test_books_basic():
    """Basic unit test scaffold for books."""
    assert True


@pytest.mark.asyncio
async def test_reprocess_graph_disabled():
    from api.endpoints.books import reprocess_graph  # type: ignore[import]

    mock_session = AsyncMock()
    mock_user = MagicMock()
    mock_user.email = "test@example.com"

    mock_repo = MagicMock()
    mock_repo.get = AsyncMock(return_value=MagicMock())

    mock_configs_repo = MagicMock()
    mock_configs_repo.get_value = AsyncMock(return_value="false")

    with patch("api.endpoints.books.BooksRepository", return_value=mock_repo), \
         patch("api.endpoints.books.SystemConfigsRepository", return_value=mock_configs_repo):
        with pytest.raises(HTTPException) as excinfo:
            await reprocess_graph(
                book_id="some-book-id",
                current_user=mock_user,
                session=mock_session,
            )

    assert excinfo.value.status_code == 400
    assert "Knowledge Graph generation is currently disabled" in excinfo.value.detail
