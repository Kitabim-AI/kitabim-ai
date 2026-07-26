import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.scanners.event_dispatcher import run_event_dispatcher

CONFIG_PATCH_PATH = (
    "app.db.repositories.system_configs_repository.SystemConfigsRepository.get_value"
)


def _mock_event(event_id, event_type, page_id):
    event = MagicMock()
    event.id = event_id
    event.event_type = event_type
    event.page_id = page_id
    return event


@pytest.mark.asyncio
async def test_event_dispatcher_no_events():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_events_result

    with patch("app.db.session.async_session_factory") as mock_session_factory:
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_not_called()
        mock_session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_event_dispatcher_claims_and_batches_chunking_jobs():
    """With spell check disabled, ocr_succeeded still triggers chunking directly."""
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [
        _mock_event(1, "ocr_succeeded", 101),
        _mock_event(2, "ocr_succeeded", 102),
    ]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    # Both candidate pages are still idle for chunking and get claimed.
    mock_claim_select_result = MagicMock()
    mock_claim_select_result.fetchall.return_value = [
        (101, "book-a"),
        (102, "book-a"),
    ]

    mock_session.execute.side_effect = [
        mock_events_result,  # fetch unprocessed events
        mock_claim_select_result,  # claim SELECT for chunking candidates
        MagicMock(),  # UPDATE Page milestone -> in_progress
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
        patch(
            "services.worker.scanners.event_dispatcher.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ) as mock_update_milestone,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "false"

        await run_event_dispatcher(ctx)

        # One batched chunking_job call with both claimed pages, not two.
        mock_redis.enqueue_job.assert_called_once_with(
            "chunking_job", page_ids=[101, 102]
        )
        mock_update_milestone.assert_called_once_with(
            mock_session, "book-a", "chunking"
        )

        # Both events marked processed regardless of per-page claim outcome.
        processed_update_stmt = mock_session.execute.call_args_list[3].args[0]
        compiled = str(
            processed_update_stmt.compile(compile_kwargs={"literal_binds": True})
        )
        assert "true" in compiled.lower()


@pytest.mark.asyncio
async def test_event_dispatcher_skips_page_already_claimed_by_scanner():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(1, "ocr_succeeded", 101)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    # Page 101 is no longer idle (a concurrent scanner already claimed it) so
    # the claim SELECT (filtered on milestone == 'idle') returns nothing.
    mock_claim_select_result = MagicMock()
    mock_claim_select_result.fetchall.return_value = []

    mock_session.execute.side_effect = [
        mock_events_result,
        mock_claim_select_result,
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "false"

        await run_event_dispatcher(ctx)

        # No job dispatched — the page is already being handled elsewhere —
        # but the event is still marked processed so it isn't reprocessed.
        mock_redis.enqueue_job.assert_not_called()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_event_dispatcher_dispatches_embedding_job_for_chunking_succeeded():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(5, "chunking_succeeded", 201)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    mock_claim_select_result = MagicMock()
    mock_claim_select_result.fetchall.return_value = [(201, "book-b")]

    mock_session.execute.side_effect = [
        mock_events_result,
        mock_claim_select_result,  # claim SELECT for embedding candidates
        MagicMock(),  # UPDATE Page milestone -> in_progress
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
        patch(
            "services.worker.scanners.event_dispatcher.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ) as mock_update_milestone,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "false"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_called_once_with("embedding_job", page_ids=[201])
        mock_update_milestone.assert_called_once_with(
            mock_session, "book-b", "embedding"
        )


@pytest.mark.asyncio
async def test_event_dispatcher_embedding_succeeded_triggers_no_dispatch():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(9, "embedding_succeeded", 301)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events
    mock_session.execute.side_effect = [
        mock_events_result,
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "false"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_not_called()
        mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_event_dispatcher_ocr_succeeded_does_not_trigger_chunking_when_spell_check_enabled():
    """Once spell check is enabled, ocr_succeeded alone must NOT fire chunking —
    it has to wait for spell_check_succeeded/failed instead."""
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(1, "ocr_succeeded", 101)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events
    mock_session.execute.side_effect = [
        mock_events_result,
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "true"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_not_called()
        mock_session.commit.assert_called_once()


@pytest.mark.parametrize("event_type", ["spell_check_succeeded", "spell_check_failed"])
@pytest.mark.asyncio
async def test_event_dispatcher_spell_check_done_triggers_chunking_when_enabled(
    event_type,
):
    """Both a successful and a failed spell check must unblock chunking —
    chunking shouldn't wait forever just because spell check errored."""
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(1, event_type, 101)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    mock_claim_select_result = MagicMock()
    mock_claim_select_result.fetchall.return_value = [(101, "book-a")]

    mock_session.execute.side_effect = [
        mock_events_result,
        mock_claim_select_result,  # claim SELECT for chunking candidates
        MagicMock(),  # UPDATE Page milestone -> in_progress
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
        patch(
            "services.worker.scanners.event_dispatcher.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ),
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "true"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_called_once_with("chunking_job", page_ids=[101])
