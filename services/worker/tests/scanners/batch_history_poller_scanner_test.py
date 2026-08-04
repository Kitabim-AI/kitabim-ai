import pytest
from unittest.mock import AsyncMock, patch
from services.worker.scanners.batch_history_poller_scanner import (
    run_batch_history_poller_scanner,
)


@pytest.mark.asyncio
async def test_run_batch_history_poller_scanner_success():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.scanners.batch_history_poller_scanner.poll_and_process_batch_history_jobs",
            new_callable=AsyncMock,
        ) as mock_poll:
            mock_poll.return_value = 2

            await run_batch_history_poller_scanner(ctx)

            mock_poll.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_run_batch_history_poller_scanner_no_jobs():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.scanners.batch_history_poller_scanner.poll_and_process_batch_history_jobs",
            new_callable=AsyncMock,
        ) as mock_poll:
            mock_poll.return_value = 0

            await run_batch_history_poller_scanner(ctx)

            mock_poll.assert_called_once_with(mock_session)


@pytest.mark.asyncio
async def test_run_batch_history_poller_scanner_exception_logged():
    ctx = {}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.scanners.batch_history_poller_scanner.poll_and_process_batch_history_jobs",
            new_callable=AsyncMock,
        ) as mock_poll:
            mock_poll.side_effect = Exception("Database error")

            # Scanner must catch exception and log, not raise
            await run_batch_history_poller_scanner(ctx)

            mock_poll.assert_called_once_with(mock_session)
