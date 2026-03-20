import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.stale_watchdog import run_stale_watchdog

@pytest.mark.asyncio
async def test_stale_watchdog_no_stale_pages():
    ctx = {"redis": AsyncMock()}
    
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Mocking an empty result from execute
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_session.execute.return_value = mock_result
        
        await run_stale_watchdog(ctx)
        
        # Verify execute was called with update stmt
        mock_session.execute.assert_called()
        # Verify commit was called
        mock_session.commit.assert_called()

@pytest.mark.asyncio
async def test_stale_watchdog_reset_stale_pages():
    ctx = {"redis": AsyncMock()}
    stale_page_id = 1
    stale_book_id = "book-1"
    
    with patch("app.db.session.async_session_factory") as mock_session_factory, \
         patch("services.worker.scanners.stale_watchdog.BookMilestoneService.update_book_milestones", new_callable=AsyncMock) as mock_update_milestones:
        
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Mocking a returned stale page result from update returning Page.id, Page.book_id
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [(stale_page_id, stale_book_id)]
        mock_session.execute.return_value = mock_result
        
        await run_stale_watchdog(ctx)
        
        # Verify book milestone update was called for the book of the stale page
        mock_update_milestones.assert_called_with(mock_session, stale_book_id)
        # Verify commit was called
        mock_session.commit.assert_called()
