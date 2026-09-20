"""Tests for BookmarksRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import Bookmark
from app.db.repositories.bookmarks_repository import BookmarksRepository


@pytest.mark.asyncio
async def test_create_bookmark_whole_page():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BookmarksRepository(session)

    bookmark = await repo.create(
        user_id="u1", book_id="b1", page_number=42, name="Page 42"
    )

    assert bookmark.user_id == "u1"
    assert bookmark.page_number == 42
    assert bookmark.name == "Page 42"
    assert bookmark.quote_text is None
    assert session.add.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_create_bookmark_with_quote():
    session = AsyncMock()
    session.add = MagicMock()
    repo = BookmarksRepository(session)

    bookmark = await repo.create(
        user_id="u1",
        book_id="b1",
        page_number=10,
        name="Nice line",
        quote_text="a quoted passage",
    )

    assert bookmark.quote_text == "a quoted passage"


@pytest.mark.asyncio
async def test_list_scoped_to_book():
    session = AsyncMock()
    rows = [Bookmark(id="bm1", user_id="u1", book_id="b1", page_number=1, name="A")]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = rows
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.list(user_id="u1", book_id="b1")
    assert result == rows


@pytest.mark.asyncio
async def test_get_returns_none_for_other_users_bookmark():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.get(bookmark_id="bm1", user_id="someone-else")
    assert result is None


@pytest.mark.asyncio
async def test_rename_updates_name_when_owned():
    session = AsyncMock()
    existing = Bookmark(id="bm1", user_id="u1", book_id="b1", page_number=1, name="Old")
    get_res = MagicMock()
    get_res.scalar_one_or_none.return_value = existing
    session.execute.return_value = get_res
    repo = BookmarksRepository(session)

    result = await repo.rename(bookmark_id="bm1", user_id="u1", name="New")

    assert result is not None
    assert result.name == "New"
    assert session.commit.called


@pytest.mark.asyncio
async def test_delete_returns_true_when_row_deleted():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.delete(bookmark_id="bm1", user_id="u1")
    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_not_owned_or_missing():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.rowcount = 0
    session.execute.return_value = mock_res
    repo = BookmarksRepository(session)

    result = await repo.delete(bookmark_id="bm1", user_id="u1")
    assert result is False
