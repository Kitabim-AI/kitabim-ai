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
async def test_event_dispatcher_claims_and_dispatches_structure_job():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [
        _mock_event(1, "ocr_succeeded", 101),
        _mock_event(2, "ocr_succeeded", 102),
    ]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    mock_page_books_res = MagicMock()
    mock_page_books_res.fetchall.return_value = [("book-a",)]

    mock_claim_books_res = MagicMock()
    mock_claim_books_res.fetchall.return_value = [("book-a",)]

    mock_session.execute.side_effect = [
        mock_events_result,  # fetch unprocessed events
        mock_page_books_res,  # distinct book_ids for candidate pages
        mock_claim_books_res,  # claim SELECT on Book
        MagicMock(),  # UPDATE Book structure_milestone -> in_progress
        MagicMock(),  # UPDATE PipelineEvent processed=True
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "false"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_called_once_with(
            "structure_job", book_id="book-a"
        )


@pytest.mark.asyncio
async def test_event_dispatcher_skips_book_not_yet_ready_for_structure():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(1, "ocr_succeeded", 101)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    mock_page_books_res = MagicMock()
    mock_page_books_res.fetchall.return_value = [("book-a",)]

    mock_claim_books_res = MagicMock()
    mock_claim_books_res.fetchall.return_value = []

    mock_session.execute.side_effect = [
        mock_events_result,
        mock_page_books_res,
        mock_claim_books_res,
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


@pytest.mark.parametrize("event_type", ["spell_check_succeeded", "spell_check_failed"])
@pytest.mark.asyncio
async def test_event_dispatcher_spell_check_done_triggers_structure_when_enabled(
    event_type,
):
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}

    events = [_mock_event(1, event_type, 101)]

    mock_session = AsyncMock()
    mock_events_result = MagicMock()
    mock_events_result.scalars().all.return_value = events

    mock_page_books_res = MagicMock()
    mock_page_books_res.fetchall.return_value = [("book-a",)]

    mock_claim_books_res = MagicMock()
    mock_claim_books_res.fetchall.return_value = [("book-a",)]

    mock_session.execute.side_effect = [
        mock_events_result,
        mock_page_books_res,
        mock_claim_books_res,
        MagicMock(),
        MagicMock(),
    ]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(CONFIG_PATCH_PATH, new_callable=AsyncMock) as mock_config,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_config.return_value = "true"

        await run_event_dispatcher(ctx)

        mock_redis.enqueue_job.assert_called_once_with(
            "structure_job", book_id="book-a"
        )
