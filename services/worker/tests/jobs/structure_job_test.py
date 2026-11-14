from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.worker.jobs.structure_job import structure_job


@pytest.mark.asyncio
async def test_structure_job_persists_structure_and_enqueues_chunking():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    mock_book_res = MagicMock()
    mock_book_res.first.return_value = ("complete",)
    mock_session.execute.return_value = mock_book_res

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.jobs.structure_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.structure_job.BookStructureService.analyze_and_persist_book_structure",
            new_callable=AsyncMock,
            return_value={"content_pages_assigned": 10, "sections_extracted": 3},
        ) as mock_analyze,
    ):
        await structure_job(ctx, "book-123")

        mock_analyze.assert_awaited_once_with(mock_session, "book-123")
        mock_redis.enqueue_job.assert_awaited_once_with(
            "chunking_job", book_id="book-123"
        )


@pytest.mark.asyncio
async def test_structure_job_defers_when_ocr_is_incomplete():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    mock_book_res = MagicMock()
    mock_book_res.first.return_value = ("in_progress",)
    mock_session.execute.return_value = mock_book_res

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.jobs.structure_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.structure_job.BookStructureService.analyze_and_persist_book_structure",
            new_callable=AsyncMock,
        ) as mock_analyze,
    ):
        await structure_job(ctx, "book-123")

        mock_analyze.assert_not_awaited()
        mock_redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_job_reruns_when_dirtied_during_analysis():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    # 1st select: ocr_milestone == 'complete'
    # 2nd select (after 1st analyze): structure_milestone == 'idle' (dirtied by concurrent edit)
    # 3rd select (after 2nd analyze): structure_milestone == 'in_progress' (clean)
    res_ocr = MagicMock()
    res_ocr.first.return_value = ("complete",)
    res_dirty = MagicMock()
    res_dirty.first.return_value = ("idle",)
    res_clean = MagicMock()
    res_clean.first.return_value = ("in_progress",)
    res_update = MagicMock()

    call_results = [res_ocr, res_update, res_dirty, res_update, res_clean, res_update]
    mock_session.execute.side_effect = call_results

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.jobs.structure_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.structure_job.BookStructureService.analyze_and_persist_book_structure",
            new_callable=AsyncMock,
            return_value={"sections_count": 4, "content_page_offset": 2},
        ) as mock_analyze,
    ):
        await structure_job(ctx, "book-123")

        assert mock_analyze.await_count == 2
        mock_redis.enqueue_job.assert_awaited_once_with(
            "chunking_job", book_id="book-123"
        )


@pytest.mark.asyncio
async def test_structure_job_does_not_enqueue_duplicate_chunking_when_chunking_already_running():
    from datetime import datetime, timezone

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    res_ocr = MagicMock()
    res_ocr.first.return_value = ("complete",)
    res_after = MagicMock()
    active_claim_ts = datetime.now(timezone.utc)
    res_after.first.return_value = ("in_progress", "in_progress", active_claim_ts)
    res_update = MagicMock()

    mock_session.execute.side_effect = [res_ocr, res_update, res_after, res_update]

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.jobs.structure_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.structure_job.BookStructureService.analyze_and_persist_book_structure",
            new_callable=AsyncMock,
            return_value={"sections_count": 2, "content_page_offset": 1},
        ) as mock_analyze,
    ):
        await structure_job(ctx, "book-123")

        mock_analyze.assert_awaited_once()
        mock_redis.enqueue_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_structure_job_cancelled_error_marks_failed_and_increments_retry():
    import asyncio

    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    mock_session = AsyncMock()
    res_ocr = MagicMock()
    res_ocr.first.return_value = ("complete",)
    res_update = MagicMock()
    mock_session.execute.side_effect = [res_ocr, res_update, res_update]

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    with (
        patch(
            "services.worker.jobs.structure_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.structure_job.BookStructureService.analyze_and_persist_book_structure",
            new_callable=AsyncMock,
            side_effect=asyncio.CancelledError(),
        ),
    ):
        with pytest.raises(asyncio.CancelledError):
            await structure_job(ctx, "book-123")

        assert mock_session.commit.await_count >= 1
