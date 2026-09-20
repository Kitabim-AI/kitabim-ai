import sys
from datetime import datetime, timezone
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


def make_user(user_id="user-1"):
    from app.models.user import User

    user = MagicMock(spec=User)
    user.id = user_id
    user.role = "reader"
    return user


@pytest.mark.asyncio
async def test_upsert_progress_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import (
        upsert_progress_endpoint,
        UpsertProgressRequest,
    )
    from app.db.models import ReadingProgress

    session = AsyncMock()
    with_repo = ReadingProgress(
        user_id="user-1",
        book_id="book-1",
        page_number=42,
        updated_at=datetime.now(timezone.utc),
    )
    with _mock_repo(
        "api.endpoints.bookmarks_router.ReadingProgressRepository", "upsert", with_repo
    ):
        response = await upsert_progress_endpoint(
            book_id="book-1",
            req=UpsertProgressRequest(page_number=42),
            current_user=make_user(),
            session=session,
        )

    assert response["bookId"] == "book-1"
    assert response["pageNumber"] == 42


@pytest.mark.asyncio
async def test_get_progress_for_book_returns_none_when_missing():
    setup_paths()
    from api.endpoints.bookmarks_router import get_progress_for_book_endpoint

    session = AsyncMock()
    with _mock_repo(
        "api.endpoints.bookmarks_router.ReadingProgressRepository", "get_for_book", None
    ):
        response = await get_progress_for_book_endpoint(
            book_id="book-1", current_user=make_user(), session=session
        )

    assert response["pageNumber"] is None


@pytest.mark.asyncio
async def test_list_progress_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import list_progress_endpoint
    from app.db.models import ReadingProgress, Book

    session = AsyncMock()
    row = ReadingProgress(
        user_id="user-1",
        book_id="book-1",
        page_number=5,
        updated_at=datetime.now(timezone.utc),
    )
    row.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo(
        "api.endpoints.bookmarks_router.ReadingProgressRepository", "list_recent", [row]
    ):
        response = await list_progress_endpoint(
            current_user=make_user(), session=session
        )

    assert response["items"][0]["bookId"] == "book-1"
    assert response["items"][0]["bookTitle"] == "My Book"
    assert response["items"][0]["pageNumber"] == 5


@pytest.mark.asyncio
async def test_create_bookmark_endpoint():
    setup_paths()
    from api.endpoints.bookmarks_router import (
        create_bookmark_endpoint,
        CreateBookmarkRequest,
    )
    from app.db.models import Bookmark, Book

    session = AsyncMock()
    bookmark = Bookmark(
        id="bm1",
        user_id="user-1",
        book_id="book-1",
        page_number=3,
        name="My mark",
        created_at=datetime.now(timezone.utc),
    )
    bookmark.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo(
        "api.endpoints.bookmarks_router.BookmarksRepository", "create", bookmark
    ):
        response = await create_bookmark_endpoint(
            book_id="book-1",
            req=CreateBookmarkRequest(page_number=3, name="My mark"),
            current_user=make_user(),
            session=session,
        )

    assert response["id"] == "bm1"
    assert response["name"] == "My mark"
    assert response["quoteText"] is None


@pytest.mark.asyncio
async def test_list_bookmarks_endpoint_with_book_filter():
    setup_paths()
    from api.endpoints.bookmarks_router import list_bookmarks_endpoint
    from app.db.models import Bookmark, Book

    session = AsyncMock()
    bookmark = Bookmark(
        id="bm1",
        user_id="user-1",
        book_id="book-1",
        page_number=3,
        name="My mark",
        created_at=datetime.now(timezone.utc),
    )
    bookmark.book = Book(id="book-1", title="My Book", content_hash="h")
    with _mock_repo(
        "api.endpoints.bookmarks_router.BookmarksRepository", "list", [bookmark]
    ) as mock_repo_class:
        response = await list_bookmarks_endpoint(
            book_id="book-1", current_user=make_user(), session=session
        )
        mock_repo_class.return_value.list.assert_called_once_with(
            user_id="user-1", book_id="book-1"
        )

    assert len(response["bookmarks"]) == 1


@pytest.mark.asyncio
async def test_rename_bookmark_endpoint_not_found_raises_404():
    setup_paths()
    from api.endpoints.bookmarks_router import (
        rename_bookmark_endpoint,
        RenameBookmarkRequest,
    )
    from fastapi import HTTPException

    session = AsyncMock()
    with _mock_repo(
        "api.endpoints.bookmarks_router.BookmarksRepository", "rename", None
    ):
        with pytest.raises(HTTPException) as exc_info:
            await rename_bookmark_endpoint(
                bookmark_id="missing",
                req=RenameBookmarkRequest(name="New"),
                current_user=make_user(),
                session=session,
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_bookmark_endpoint_not_found_raises_404():
    setup_paths()
    from api.endpoints.bookmarks_router import delete_bookmark_endpoint
    from fastapi import HTTPException

    session = AsyncMock()
    with _mock_repo(
        "api.endpoints.bookmarks_router.BookmarksRepository", "delete", False
    ):
        with pytest.raises(HTTPException) as exc_info:
            await delete_bookmark_endpoint(
                bookmark_id="missing", current_user=make_user(), session=session
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_bookmark_endpoint_success():
    setup_paths()
    from api.endpoints.bookmarks_router import delete_bookmark_endpoint

    session = AsyncMock()
    with _mock_repo(
        "api.endpoints.bookmarks_router.BookmarksRepository", "delete", True
    ):
        response = await delete_bookmark_endpoint(
            bookmark_id="bm1", current_user=make_user(), session=session
        )

    assert response == {"success": True}


def _mock_repo(target_path: str, method_name: str, return_value):
    """Patch <RepositoryClass>(session).<method_name> to return return_value"""
    from unittest.mock import patch

    mock_instance = MagicMock()
    setattr(mock_instance, method_name, AsyncMock(return_value=return_value))
    return patch(target_path, return_value=mock_instance)
