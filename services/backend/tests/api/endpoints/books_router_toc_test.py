import pytest
from unittest.mock import AsyncMock
import sys
from pathlib import Path
import importlib.util

BACKEND_DIR = Path(__file__).resolve().parents[3]
BACKEND_CORE_DIR = Path(__file__).resolve().parents[5] / "packages" / "backend-core"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(BACKEND_CORE_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_CORE_DIR))

BOOKS_PATH = BACKEND_DIR / "api" / "endpoints" / "books_router.py"
spec = importlib.util.spec_from_file_location(
    "test_books_toc_endpoint_module", BOOKS_PATH
)
books_endpoint = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(books_endpoint)

from datetime import datetime, timezone

from app.models.schemas import PageTocUpdate
from app.models.user import User, UserRole


def make_user():
    return User(
        id="u1",
        email="editor@example.com",
        display_name="Editor",
        role=UserRole.EDITOR,
        provider="google",
        provider_id="g-1",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_set_page_toc_marks_and_deletes_chunks(monkeypatch):
    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = True
    mock_chunks_repo = AsyncMock()
    mock_chunks_repo.delete_by_page.return_value = 4

    monkeypatch.setattr(
        books_endpoint, "PagesRepository", lambda session: mock_pages_repo
    )
    monkeypatch.setattr(
        books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo
    )

    session = AsyncMock()
    result = await books_endpoint.set_page_toc(
        book_id="b1",
        page_num=5,
        body=PageTocUpdate(is_toc=True),
        current_user=make_user(),
        session=session,
    )

    mock_pages_repo.set_is_toc.assert_awaited_once_with(
        "b1", 5, True, "editor@example.com"
    )
    mock_chunks_repo.delete_by_page.assert_awaited_once_with("b1", 5)
    assert result == {"status": "ok", "isToc": True}
    assert session.commit.called


@pytest.mark.asyncio
async def test_set_page_toc_unmark_does_not_touch_chunks(monkeypatch):
    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = True
    mock_chunks_repo = AsyncMock()

    monkeypatch.setattr(
        books_endpoint, "PagesRepository", lambda session: mock_pages_repo
    )
    monkeypatch.setattr(
        books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo
    )

    session = AsyncMock()
    result = await books_endpoint.set_page_toc(
        book_id="b1",
        page_num=5,
        body=PageTocUpdate(is_toc=False),
        current_user=make_user(),
        session=session,
    )

    mock_pages_repo.set_is_toc.assert_awaited_once_with(
        "b1", 5, False, "editor@example.com"
    )
    mock_chunks_repo.delete_by_page.assert_not_called()
    assert result == {"status": "ok", "isToc": False}


@pytest.mark.asyncio
async def test_set_page_toc_404_for_unknown_page(monkeypatch):
    from fastapi import HTTPException

    mock_pages_repo = AsyncMock()
    mock_pages_repo.set_is_toc.return_value = False
    mock_chunks_repo = AsyncMock()

    monkeypatch.setattr(
        books_endpoint, "PagesRepository", lambda session: mock_pages_repo
    )
    monkeypatch.setattr(
        books_endpoint, "ChunksRepository", lambda session: mock_chunks_repo
    )

    with pytest.raises(HTTPException) as exc_info:
        await books_endpoint.set_page_toc(
            book_id="b1",
            page_num=999,
            body=PageTocUpdate(is_toc=True),
            current_user=make_user(),
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == 404
    mock_chunks_repo.delete_by_page.assert_not_called()
