import pytest
from unittest.mock import AsyncMock, patch

from app.services.ocr_auto_heal_service import BookAutoHealResult
from services.worker.jobs.book_auto_correct_job import book_auto_correct_job


@pytest.mark.asyncio
async def test_book_auto_correct_job_runs_and_releases_lock():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=True)
    mock_redis.delete = AsyncMock()
    ctx = {"redis": mock_redis}

    fake_result = BookAutoHealResult(
        book_id="book-99",
        pages_scanned=10,
        pages_modified=2,
        rule_replacements=1,
        ocr_heals=3,
        total_replacements=4,
    )

    with (
        patch("app.db.session.async_session_factory") as mock_sf,
        patch(
            "services.worker.jobs.book_auto_correct_job.auto_heal_book_pages",
            new_callable=AsyncMock,
            return_value=fake_result,
        ) as mock_heal,
    ):
        mock_session = AsyncMock()
        mock_sf.return_value.__aenter__.return_value = mock_session

        await book_auto_correct_job(ctx, book_id="book-99", updated_by="admin@test.com")

    mock_heal.assert_awaited_once_with(
        mock_session, "book-99", updated_by="admin@test.com"
    )
    mock_redis.delete.assert_awaited_once_with("lock:book_auto_correct:book-99")


@pytest.mark.asyncio
async def test_book_auto_correct_job_skips_when_lock_already_held():
    mock_redis = AsyncMock()
    mock_redis.set = AsyncMock(return_value=False)
    mock_redis.delete = AsyncMock()
    ctx = {"redis": mock_redis}

    with patch(
        "services.worker.jobs.book_auto_correct_job.auto_heal_book_pages",
        new_callable=AsyncMock,
    ) as mock_heal:
        await book_auto_correct_job(ctx, book_id="book-99")

    mock_heal.assert_not_awaited()
    mock_redis.delete.assert_not_awaited()
