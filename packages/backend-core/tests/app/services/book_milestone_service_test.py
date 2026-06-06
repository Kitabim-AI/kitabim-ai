import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.book_milestone_service import BookMilestoneService
from app.db.models import Book

def test_compute_milestone_status():
    service = BookMilestoneService()
    
    # All done
    assert service.compute_milestone_status(10, 0, 0, 10) == 'complete'
    
    # Partial failure but all finished
    assert service.compute_milestone_status(8, 2, 0, 10) == 'partial_failure'
    
    # All failed
    assert service.compute_milestone_status(0, 10, 0, 10) == 'failed'
    
    # In progress (some done)
    assert service.compute_milestone_status(5, 0, 0, 10) == 'in_progress'
    
    # In progress (active)
    assert service.compute_milestone_status(0, 0, 5, 10) == 'in_progress'
    
    # Idle
    assert service.compute_milestone_status(0, 0, 0, 10) == 'idle'
    
    # Total 0
    assert service.compute_milestone_status(0, 0, 0, 0) == 'idle'

@pytest.mark.asyncio
async def test_update_book_milestones():
    db = AsyncMock()
    book_id = "test-book-123"
    
    # Mocking the page stats query result
    mock_stats = MagicMock()
    mock_stats.total = 10
    mock_stats.ocr_done = 10
    mock_stats.ocr_failed = 0
    mock_stats.ocr_active = 0
    mock_stats.chunking_done = 5
    mock_stats.chunking_failed = 0
    mock_stats.chunking_active = 0
    mock_stats.embedding_done = 0
    mock_stats.embedding_failed = 0
    mock_stats.embedding_active = 0
    mock_stats.spell_check_done = 0
    mock_stats.spell_check_failed = 0
    mock_stats.spell_check_active = 0
    
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_stats
    db.execute.side_effect = [mock_result, AsyncMock()]
    
    # Mocking the book fetch
    mock_book = Book(id=book_id)
    mock_book_result = MagicMock()
    mock_book_result.scalar_one_or_none.return_value = mock_book
    db.execute.side_effect = [mock_result, mock_book_result]
    
    await BookMilestoneService.update_book_milestones(db, book_id)
    
    assert mock_book.ocr_milestone == 'complete'
    assert mock_book.chunking_milestone == 'in_progress'
    assert mock_book.embedding_milestone == 'idle'
    assert mock_book.spell_check_milestone == 'idle'

@pytest.mark.asyncio
async def test_update_book_milestone_for_step():
    db = AsyncMock()
    book_id = "test-book-456"
    
    # Mock ocr step stats
    mock_stats = MagicMock()
    mock_stats.total = 10
    mock_stats.done = 10
    mock_stats.failed = 0
    mock_stats.active = 0
    
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = mock_stats
    
    # Mock book fetch
    mock_book = Book(id=book_id, ocr_milestone='idle')
    mock_book_result = MagicMock()
    mock_book_result.scalar_one_or_none.return_value = mock_book
    
    db.execute.side_effect = [mock_result, mock_book_result]
    
    await BookMilestoneService.update_book_milestone_for_step(db, book_id, 'ocr')
    
    assert mock_book.ocr_milestone == 'complete'

@pytest.mark.asyncio
async def test_update_book_milestones_no_stats():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    # Should return early and not fail
    await BookMilestoneService.update_book_milestones(db, "b1")

@pytest.mark.asyncio
async def test_update_book_milestone_for_step_unknown():
    db = AsyncMock()
    with pytest.raises(ValueError, match="Unknown step: oops"):
        await BookMilestoneService.update_book_milestone_for_step(db, "b1", "oops")

@pytest.mark.asyncio
async def test_update_book_milestone_for_step_no_stats():
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.one_or_none.return_value = None
    db.execute.return_value = mock_result
    
    # Should return early
    await BookMilestoneService.update_book_milestone_for_step(db, "b1", "ocr")
