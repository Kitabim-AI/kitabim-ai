import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.stale_watchdog_scanner import run_stale_watchdog


def _mock_empty():
    m = MagicMock()
    m.fetchall.return_value = []
    return m


@pytest.mark.asyncio
async def test_stale_watchdog_no_stale_pages():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [b"worker:heartbeat:worker-1"])
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Page is in progress on active worker-1 and was claimed 5 mins ago (not stale)
        mock_pages_result = MagicMock()
        recent_time = datetime.now(timezone.utc) - timedelta(minutes=5)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "worker-1", recent_time)
        ]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            mock_pages_result,  # Pages query
            _mock_empty(),  # Book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        assert mock_session.execute.call_count == 6
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

        # Page is in progress on dead worker and claimed 3 mins ago (stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=3)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "dead-worker", claimed_time)
        ]

        # Mock the update return value for pages
        mock_update_result = MagicMock()
        mock_update_result.fetchall.return_value = [(1, "book-1")]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            mock_pages_result,
            mock_update_result,
            _mock_empty(),  # book update
            _mock_empty(),  # stale llm spell query
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

        # Page is in progress on dead worker but claimed 30 seconds ago (within grace period, not stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(seconds=30)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "dead-worker", claimed_time)
        ]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            mock_pages_result,
            _mock_empty(),  # book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        assert mock_session.execute.call_count == 6
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

        # Page is in progress on active worker but claimed 35 mins ago (exceeds STALE_THRESHOLD_MINUTES, stale)
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=35)
        mock_pages_result.fetchall.return_value = [
            (1, "book-1", "active-worker", claimed_time)
        ]

        mock_update_result = MagicMock()
        mock_update_result.fetchall.return_value = [(1, "book-1")]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            mock_pages_result,
            mock_update_result,
            _mock_empty(),  # book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        mock_update_milestones.assert_called_with(mock_session, "book-1")
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_exempts_active_batch_embedding_pages():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Page 999 is locked in an active BatchEmbeddingJob
        mock_embed_result = MagicMock()
        mock_embed_result.fetchall.return_value = [([999],)]

        # Page 999 is in progress and claimed 40 mins ago
        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=40)
        mock_pages_result.fetchall.return_value = [
            (999, "book-1", "dead-worker", claimed_time)
        ]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            mock_embed_result,  # batch embedding
            _mock_empty(),  # batch LLM spell check
            mock_pages_result,
            _mock_empty(),  # book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        # Page 999 should be exempted, so update(Page) is NOT called
        assert mock_session.execute.call_count == 6
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_exempts_active_batch_llm_spell_check_pages():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Page 888 is locked in an active BatchLlmSpellCheckJob
        mock_spell_result = MagicMock()
        mock_spell_result.fetchall.return_value = [([888],)]

        mock_pages_result = MagicMock()
        claimed_time = datetime.now(timezone.utc) - timedelta(minutes=40)
        mock_pages_result.fetchall.return_value = [
            (888, "book-1", "dead-worker", claimed_time)
        ]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            mock_spell_result,  # batch LLM spell check
            mock_pages_result,
            _mock_empty(),  # book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        # Page 888 exempted, update(Page) NOT called
        assert mock_session.execute.call_count == 6
        mock_session.commit.assert_called()


@pytest.mark.asyncio
async def test_stale_watchdog_resets_stuck_llm_spell_check_pages():
    mock_redis = AsyncMock()
    mock_redis.scan.return_value = (0, [])
    ctx = {"redis": mock_redis}

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_stale_llm = MagicMock()
        mock_stale_llm.fetchall.return_value = [(101,)]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            _mock_empty(),  # Pages query
            _mock_empty(),  # book update
            mock_stale_llm,  # stale llm spell query
            _mock_empty(),  # update(Page) setting failed
        ]

        await run_stale_watchdog(ctx)

        # 7 calls because the update for stuck llm spell check was executed
        assert mock_session.execute.call_count == 7
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

        mock_book_result = MagicMock()
        mock_book_result.fetchall.return_value = [(stale_book_id,)]

        mock_session.execute.side_effect = [
            _mock_empty(),  # batch OCR
            _mock_empty(),  # batch embedding
            _mock_empty(),  # batch LLM spell check
            _mock_empty(),  # Pages query
            mock_book_result,  # book update
            _mock_empty(),  # stale llm spell query
        ]

        await run_stale_watchdog(ctx)

        assert mock_session.execute.call_count == 6
        mock_session.commit.assert_called()
