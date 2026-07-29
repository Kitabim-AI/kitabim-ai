import pytest
from unittest.mock import AsyncMock, patch
from services.worker.jobs.graph_resolution_job import graph_resolution_job


@pytest.mark.asyncio
async def test_graph_resolution_job_resolves_each_entity_in_its_own_session():
    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.graph_resolution_job.GraphRepository"
        ) as MockGraphRepo,
        patch(
            "services.worker.jobs.graph_resolution_job.resolve_entity", new=AsyncMock()
        ) as mock_resolve_entity,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_graph_repo = AsyncMock()
        MockGraphRepo.return_value = mock_graph_repo

        await graph_resolution_job({}, ["e1", "e2"])

        assert mock_resolve_entity.call_count == 2
        called_entity_ids = {c[0][2] for c in mock_resolve_entity.call_args_list}
        assert called_entity_ids == {"e1", "e2"}
        mock_graph_repo.close.assert_called_once()


@pytest.mark.asyncio
async def test_graph_resolution_job_one_failure_does_not_abort_the_batch():
    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.graph_resolution_job.GraphRepository"
        ) as MockGraphRepo,
        patch(
            "services.worker.jobs.graph_resolution_job.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "services.worker.jobs.graph_resolution_job.resolve_entity", new=AsyncMock()
        ) as mock_resolve_entity,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        MockGraphRepo.return_value = AsyncMock()
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo

        mock_resolve_entity.side_effect = [Exception("boom"), None]

        # Must not raise — failures are isolated per-entity.
        await graph_resolution_job({}, ["bad-entity", "good-entity"])

        assert mock_resolve_entity.call_count == 2
        queue_repo.mark_status.assert_called_once_with("bad-entity", "failed")


@pytest.mark.asyncio
async def test_graph_resolution_job_empty_list_closes_repo():
    with patch(
        "services.worker.jobs.graph_resolution_job.GraphRepository"
    ) as MockGraphRepo:
        mock_graph_repo = AsyncMock()
        MockGraphRepo.return_value = mock_graph_repo

        await graph_resolution_job({}, [])

        mock_graph_repo.close.assert_called_once()
