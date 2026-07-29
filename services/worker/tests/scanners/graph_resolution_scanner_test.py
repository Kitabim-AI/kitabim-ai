import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.scanners.graph_resolution_scanner import (
    run_graph_resolution_scanner,
)


@pytest.mark.asyncio
async def test_run_graph_resolution_scanner_disabled():
    ctx = {"redis": AsyncMock()}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with patch(
            "services.worker.scanners.graph_resolution_scanner.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value:
            mock_get_value.return_value = "false"

            await run_graph_resolution_scanner(ctx)

            mock_get_value.assert_called_with("knowledge_graph_enabled", "false")
            ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_run_graph_resolution_scanner_no_rows_claimed():
    ctx = {"redis": AsyncMock()}
    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.graph_resolution_scanner.SystemConfigsRepository.get_value",
                new_callable=AsyncMock,
            ) as mock_get_value,
            patch(
                "services.worker.scanners.graph_resolution_scanner.GraphResolutionQueueRepository"
            ) as MockQueueRepo,
        ):
            mock_get_value.side_effect = ["true", "20"]
            queue_repo = AsyncMock()
            queue_repo.claim_batch.return_value = []
            MockQueueRepo.return_value = queue_repo

            await run_graph_resolution_scanner(ctx)

            ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_run_graph_resolution_scanner_enqueues_one_job_per_scope():
    ctx = {"redis": AsyncMock()}
    ctx["redis"].enqueue_job = AsyncMock(return_value=MagicMock())

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.graph_resolution_scanner.SystemConfigsRepository.get_value",
                new_callable=AsyncMock,
            ) as mock_get_value,
            patch(
                "services.worker.scanners.graph_resolution_scanner.GraphResolutionQueueRepository"
            ) as MockQueueRepo,
        ):
            mock_get_value.side_effect = ["true", "20"]

            row_fiction = MagicMock(scope="fiction", entity_id="e-fiction")
            row_nonfiction = MagicMock(scope="nonfiction", entity_id="e-nonfiction")
            queue_repo = AsyncMock()
            queue_repo.claim_batch.return_value = [row_fiction, row_nonfiction]
            MockQueueRepo.return_value = queue_repo

            await run_graph_resolution_scanner(ctx)

            assert ctx["redis"].enqueue_job.call_count == 2
            calls_by_job_id = {
                c.kwargs["_job_id"]: c.kwargs["entity_ids"]
                for c in ctx["redis"].enqueue_job.call_args_list
            }
            assert calls_by_job_id["graph_resolution:fiction:batch"] == ["e-fiction"]
            assert calls_by_job_id["graph_resolution:nonfiction:batch"] == [
                "e-nonfiction"
            ]


@pytest.mark.asyncio
async def test_run_graph_resolution_scanner_dedup_returns_none():
    ctx = {"redis": AsyncMock()}
    ctx["redis"].enqueue_job = AsyncMock(return_value=None)

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        with (
            patch(
                "services.worker.scanners.graph_resolution_scanner.SystemConfigsRepository.get_value",
                new_callable=AsyncMock,
            ) as mock_get_value,
            patch(
                "services.worker.scanners.graph_resolution_scanner.GraphResolutionQueueRepository"
            ) as MockQueueRepo,
        ):
            mock_get_value.side_effect = ["true", "20"]
            row = MagicMock(scope="nonfiction", entity_id="e1")
            queue_repo = AsyncMock()
            queue_repo.claim_batch.return_value = [row]
            MockQueueRepo.return_value = queue_repo

            # Should not raise even though enqueue_job returned None (already queued)
            await run_graph_resolution_scanner(ctx)
            ctx["redis"].enqueue_job.assert_called_once()
