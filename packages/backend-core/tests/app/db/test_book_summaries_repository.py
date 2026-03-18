import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.book_summaries import BookSummariesRepository
from app.db.models import BookSummary

@pytest.mark.asyncio
async def test_summary_search():
    session = AsyncMock()
    repo = BookSummariesRepository(session)
    
    # Mocking fetchall() result
    mock_row = MagicMock()
    mock_row.book_id = "b1"
    
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res
    
    ids = await repo.summary_search([0.1]*768)
    assert ids == ["b1"]

@pytest.mark.asyncio
async def test_upsert():
    session = AsyncMock()
    repo = BookSummariesRepository(session)
    
    await repo.upsert("b1", "Summary text", [0.1]*768)
    
    assert session.execute.called
    assert session.flush.called

@pytest.mark.asyncio
async def test_get_by_book_id():
    session = AsyncMock()
    repo = BookSummariesRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = BookSummary(book_id="b1", summary="test")
    session.execute.return_value = mock_res
    
    res = await repo.get_by_book_id("b1")
    assert res.book_id == "b1"
