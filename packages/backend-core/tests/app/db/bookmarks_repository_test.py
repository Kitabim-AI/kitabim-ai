"""Tests for BookmarksRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import Bookmark
from app.db.repositories.bookmarks_repository import BookmarksRepository


def _session_returning_added_bookmark():
    """create() commits, then reloads the new row with its book attached
    (selectinload). Make that reload return the object passed to add()."""
    session = AsyncMock()
    added = {}
    session.add = MagicMock(side_effect=lambda obj: added.setdefault("obj", obj))

    async def execute(stmt, *args, **kwargs):
        res = MagicMock()
        res.scalar_one.return_value = added["obj"]
        return res

    session.execute = AsyncMock(side_effect=execute)
    return session


@pytest.mark.asyncio
async def test_create_bookmark_whole_page():
    session = _session_returning_added_bookmark()
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
    # The reload selects the new row so the response includes its book.
    reload_sql = str(session.execute.await_args.args[0])
    assert "FROM bookmarks" in reload_sql and "bookmarks.id" in reload_sql


@pytest.mark.asyncio
async def test_create_bookmark_with_quote():
    session = _session_returning_added_bookmark()
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
    reload_res = MagicMock()
    reload_res.scalar_one.return_value = existing
    # 1st execute: ownership-checked get(); 2nd: reload with the book attached.
    session.execute.side_effect = [get_res, reload_res]
    repo = BookmarksRepository(session)

    result = await repo.rename(bookmark_id="bm1", user_id="u1", name="New")

    assert result is not None
    assert result.name == "New"
    assert session.commit.called
    assert session.execute.await_count == 2


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
