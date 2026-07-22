import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.stale_watchdog_scanner import run_stale_watchdog


@pytest.mark.asyncio
async def test_stale_watchdog_no_stale_pages():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [b"worker:heartbeat:worker-1"])
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # No pages locked by an active Gemini Batch OCR job
        mock_batch_result = MagicMock()
        mock_batch_result.fetchall.return_value = []

        # Page is in progress on active worker-1 and was claimed 5 mins ago (not stale)
        mock_pages_result = MagicMock()
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "worker-1", recent_time)
        ]

        # Book result
        mock_books_result = MagicMock()
        mock_books_result.fetchall.return_value = []

        mock_session.execute.side_effect = [
            mock_batch_result,
            mock_pages_result,
            mock_books_result,
        ]

        await run_stale_watchdog(ctx)

        # Execute should be called three times (select active batch pages,
        # select Pages, update Book) and NOT update Page.
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_reset_dead_worker():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])  # No active workers
    ctx = {"redis": mock_redis}

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.scanners.stale_watchdog_scanner.BookMilestoneService.update_book_milestones",
            new_callable=AsyncMock,
        ) as mock_update_milestones,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # No pages locked by an active Gemini Batch OCR job
        mock_batch_result = MagicMock()
        mock_batch_result.fetchall.return_value = []

        # Page is in progress on dead worker and claimed 3 mins ago (stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=3)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "dead-worker", claimed_time)
        ]

        # Mock the update return value for pages
        mock_update_result = MagicMock()
        mock_update_result.fetchall.return_value = [(1, "book-1")]

        # Mock the update return value for books
        mock_books_result = MagicMock()
        mock_books_result.fetchall.return_value = []

        mock_session.execute.side_effect = [
            mock_batch_result,
            mock_pages_result,
            mock_update_result,
            mock_books_result,
        ]

        await run_stale_watchdog(ctx)

        # Verify book milestones were updated for book-1
        mock_update_milestones.assert_called_with(mock_session, "book-1")
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_dead_worker_grace_period():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])  # No active workers
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # No pages locked by an active Gemini Batch OCR job
        mock_batch_result = MagicMock()
        mock_batch_result.fetchall.return_value = []

        # Page is in progress on dead worker but claimed 30 seconds ago (within grace period, not stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "dead-worker", claimed_time)
        ]

        # Book result
        mock_books_result = MagicMock()
        mock_books_result.fetchall.return_value = []

        mock_session.execute.side_effect = [
            mock_batch_result,
            mock_pages_result,
            mock_books_result,
        ]

        await run_stale_watchdog(ctx)

        # Execute should be called three times (select active batch pages,
        # select Pages, update Book) and NOT update Page.
        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_reset_hung_active_worker():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [b"worker:heartbeat:active-worker"])
    ctx = {"redis": mock_redis}

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.scanners.stale_watchdog_scanner.BookMilestoneService.update_book_milestones",
            new_callable=AsyncMock,
        ) as mock_update_milestones,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # No pages locked by an active Gemini Batch OCR job
        mock_batch_result = MagicMock()
        mock_batch_result.fetchall.return_value = []

        # Page is in progress on active worker but claimed 35 mins ago (exceeds STALE_THRESHOLD_MINUTES, stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=35)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "active-worker", claimed_time)
        ]

        # Mock the update return value for pages
        mock_update_result = MagicMock()
        mock_update_result.fetchall.return_value = [(1, "book-1")]

        # Mock the update return value for books
        mock_books_result = MagicMock()
        mock_books_result.fetchall.return_value = []

        mock_session.execute.side_effect = [
            mock_batch_result,
            mock_pages_result,
            mock_update_result,
            mock_books_result,
        ]

        await run_stale_watchdog(ctx)

        # Verify book milestones were updated for book-1
        mock_update_milestones.assert_called_with(mock_session, "book-1")
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_reset_stale_books():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])
    ctx = {"redis": mock_redis}
    stale_book_id = "book-2"

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_batch_result = MagicMock()
        mock_batch_result.fetchall.return_value = []

        mock_page_result = MagicMock()
        mock_page_result.fetchall.return_value = []

        mock_book_result = MagicMock()
        mock_book_result.fetchall.return_value = [(stale_book_id,)]

        mock_session.execute.side_effect = [
            mock_batch_result,
            mock_page_result,
            mock_book_result,
        ]

        await run_stale_watchdog(ctx)

        assert mock_session.execute.call_count == 3
        mock_session.commit.assert_called()
