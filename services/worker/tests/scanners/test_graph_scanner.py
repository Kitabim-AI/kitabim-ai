import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.graph_scanner import run_graph_scanner


@pytest.mark.asyncio
async def test_run_graph_scanner_disabled():
    ctx = {"redis": AsyncMock()}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        with patch("services.worker.scanners.graph_scanner.SystemConfigsRepository.get_value", new_callable=AsyncMock) as mock_get_value:
            mock_get_value.return_value = "false"
            
            await run_graph_scanner(ctx)
            
            mock_get_value.assert_called_with("knowledge_graph_enabled", "false")
            mock_session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_run_graph_scanner_enabled_no_books():
    ctx = {"redis": AsyncMock()}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        with patch("services.worker.scanners.graph_scanner.SystemConfigsRepository.get_value", new_callable=AsyncMock) as mock_get_value:
            mock_get_value.side_effect = ["true", "5"]
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = []
            mock_session.execute.return_value = mock_result
            
            await run_graph_scanner(ctx)
            
            mock_session.execute.assert_called_once()
            ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_run_graph_scanner_enabled_with_books():
    ctx = {"redis": AsyncMock()}
    book_id = "book-123"
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = MagicMock()
        mock_session.execute = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        
        with patch("services.worker.scanners.graph_scanner.SystemConfigsRepository.get_value", new_callable=AsyncMock) as mock_get_value:
            mock_get_value.side_effect = ["true", "5"]
            
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [(book_id,)]
            mock_session.execute.return_value = mock_result
            
            await run_graph_scanner(ctx)
            
            assert mock_session.execute.call_count == 2
            mock_session.commit.assert_called_once()
            ctx["redis"].enqueue_job.assert_called_once_with(
                "knowledge_graph_job",
                book_id=book_id,
                _job_id=f"knowledge_graph:{book_id}"
            )
