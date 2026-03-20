import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.spell_check_scanner import run_spell_check_scanner

@pytest.mark.asyncio
async def test_spell_check_scanner_no_work():
    ctx = {"redis": AsyncMock()}
    
    with patch("app.db.session.async_session_factory") as mock_session_factory, \
         patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", new_callable=AsyncMock) as mock_config:
        
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Use side_effect to return correct types for different config keys
        def config_side_effect(key, default=None):
            if key == "spell_check_enabled":
                return "true"
            if key == "scanner_page_limit":
                return "100"
            return default
            
        mock_config.side_effect = config_side_effect
        # Mocking empty result for active books
        mock_active_res = MagicMock()
        mock_active_res.fetchall.return_value = []
        # Mocking empty candidates
        mock_candidates_res = MagicMock()
        mock_candidates_res.fetchall.return_value = []
        
        # Return none for all executes
        mock_session.execute.side_effect = [mock_active_res, mock_candidates_res]
        
        await run_spell_check_scanner(ctx)
        
        # Verify redis.enqueue_job was NOT called
        ctx["redis"].enqueue_job.assert_not_called()

@pytest.mark.asyncio
async def test_spell_check_scanner_dispatches_job():
    ctx = {"redis": AsyncMock()}
    book_id = "book-1"
    page_id = 1
    
    with patch("app.db.session.async_session_factory") as mock_session_factory, \
         patch("app.db.repositories.system_configs.SystemConfigsRepository.get_value", new_callable=AsyncMock) as mock_config, \
         patch("app.services.book_milestone_service.BookMilestoneService.update_book_milestone_for_step", new_callable=AsyncMock) as mock_update_milestone:
        
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        # Use side_effect to return correct types for different config keys
        def config_side_effect(key, default=None):
            if key == "spell_check_enabled":
                return "true"
            if key == "scanner_page_limit":
                return "100"
            return default
            
        mock_config.side_effect = config_side_effect
        
        # Result for active books query
        mock_active_res = MagicMock()
        mock_active_res.fetchall.return_value = [] # Empty active books
        
        # Result for candidates query
        mock_candidates_res = MagicMock()
        mock_candidates_res.fetchall.return_value = [(book_id,)]
        
        # Result for claim pages query
        mock_claim_res = MagicMock()
        mock_claim_res.fetchall.return_value = [(page_id,)]
        
        # Result for getting book_ids from pages
        mock_book_ids_res = MagicMock()
        mock_book_ids_res.fetchall.return_value = [(book_id,)]
        
        # Side effects for session.execute
        mock_session.execute.side_effect = [
            mock_active_res,
            mock_candidates_res,
            mock_claim_res,
            MagicMock(), # update(Page)
            mock_book_ids_res,
            MagicMock(), # update(Book)
        ]
        
        await run_spell_check_scanner(ctx)
        
        # Verify milestone update was called
        mock_update_milestone.assert_called_with(mock_session, book_id, 'spell_check')
        # Verify redis job enqueued
        ctx["redis"].enqueue_job.assert_called_with("spell_check_job", page_ids=[page_id])
        # Verify commit
        mock_session.commit.assert_called()
