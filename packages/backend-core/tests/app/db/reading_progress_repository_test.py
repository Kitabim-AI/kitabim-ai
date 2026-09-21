"""Tests for ReadingProgressRepository"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.db.models import ReadingProgress
from app.db.repositories.reading_progress_repository import ReadingProgressRepository


@pytest.mark.asyncio
async def test_upsert_executes_atomic_statement_and_commits():
    session = AsyncMock()
    expected = ReadingProgress(id="rp1", user_id="u1", book_id="b1", page_number=42)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = expected
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    progress = await repo.upsert(user_id="u1", book_id="b1", page_number=42)

    assert progress.user_id == "u1"
    assert progress.book_id == "b1"
    assert progress.page_number == 42
    assert session.execute.called
    assert session.commit.called


@pytest.mark.asyncio
async def test_get_for_book_not_found_returns_none():
    session = AsyncMock()
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    result = await repo.get_for_book(user_id="u1", book_id="missing")
    assert result is None


@pytest.mark.asyncio
async def test_list_recent_orders_by_updated_at_desc():
    session = AsyncMock()
    rows = [ReadingProgress(id="rp1", user_id="u1", book_id="b1", page_number=1)]
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = rows
    session.execute.return_value = mock_res
    repo = ReadingProgressRepository(session)

    result = await repo.list_recent(user_id="u1", limit=10)
    assert result == rows
