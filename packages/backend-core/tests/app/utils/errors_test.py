import pytest
from unittest.mock import AsyncMock, patch
from app.utils.errors import record_book_error

@pytest.mark.asyncio
async def test_record_book_error():
    session = AsyncMock()
    with patch("app.utils.errors.BooksRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.update_one = AsyncMock(return_value=True)
        
        await record_book_error(session, "book-1", "parsing_failed", "Error message")
        assert mock_repo.update_one.called
        assert session.flush.called

@pytest.mark.asyncio
async def test_record_book_error_none():
    # Should not crash if session or book_id is missing
    await record_book_error(None, None, "test", "test")
