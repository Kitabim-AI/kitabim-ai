import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.auto_correct_job import auto_correct_job
from app.db.models import Page

@pytest.mark.asyncio
async def test_auto_correct_job_empty_pages_list():
    ctx = {"redis": AsyncMock()}
    page_ids = []
    
    # Mocking db_session.async_session_factory
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = []
        mock_session.execute.return_value = mock_result
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        await auto_correct_job(ctx, page_ids)
        
        # Check that no corrections were applied
        mock_session.execute.assert_called()

@pytest.mark.asyncio
async def test_auto_correct_job_success():
    ctx = {"redis": AsyncMock()}
    page_id = 1
    book_id = "book-1"
    page_ids = [page_id]
    
    # Mocking dependencies
    with patch("app.db.session.async_session_factory") as mock_session_factory, \
         patch("services.worker.jobs.auto_correct_job.get_correction_rules", new_callable=AsyncMock) as mock_get_rules, \
         patch("services.worker.jobs.auto_correct_job.apply_auto_corrections_to_page", new_callable=AsyncMock) as mock_apply, \
         patch("app.services.book_milestone_service.BookMilestoneService.update_book_milestones", new_callable=AsyncMock) as mock_update_milestones:
        
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Mock pages result
        mock_page = MagicMock(spec=Page)
        mock_page.id = page_id
        mock_page.book_id = book_id
        mock_page.page_number = 1
        
        mock_result = MagicMock()
        mock_result.scalars().all.return_value = [mock_page]
        mock_session.execute.return_value = mock_result
        
        # Mock correction rules
        mock_get_rules.return_value = {"word1": "word2"}
        
        # Mock apply_auto_corrections_to_page to return 1 correction applied
        mock_apply.return_value = 1
        
        await auto_correct_job(ctx, page_ids)
        
        # Check that apply was called with correction rules
        mock_apply.assert_called_with(mock_session, page_id, correction_rules={"word1": "word2"})
        
        # Check that milestone update was called for the book
        mock_update_milestones.assert_called_with(mock_session, book_id)
        
        # Verify commit was called
        mock_session.commit.assert_called()
