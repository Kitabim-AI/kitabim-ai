from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.worker.scanners.structure_scanner import run_structure_scanner


@pytest.mark.asyncio
async def test_run_structure_scanner_claims_books_and_enqueues_jobs():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("book-1",), ("book-2",)]
    mock_session.execute.side_effect = [mock_result, MagicMock()]

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.scanners.structure_scanner.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.scanners.structure_scanner.SystemConfigsRepository"
        ) as mock_config_cls,
    ):
        mock_config = AsyncMock()
        mock_config.get_value.return_value = "false"
        mock_config_cls.return_value = mock_config

        await run_structure_scanner(ctx)

        assert mock_redis.enqueue_job.call_count == 2
        mock_redis.enqueue_job.assert_any_call("structure_job", book_id="book-1")
        mock_redis.enqueue_job.assert_any_call("structure_job", book_id="book-2")
