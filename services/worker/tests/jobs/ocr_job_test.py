import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.ocr_job import ocr_job
from app.db.models import Page, Book
import pathlib


@pytest.mark.asyncio
async def test_ocr_job_success():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"
    page_ids = [101]

    # Mock DB Session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock page model
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.book_id = book_id
    mock_page.page_number = 1
    mock_page.retry_count = 0

    # Mock session query results
    mock_result_book = MagicMock()
    mock_result_book.scalar_one_or_none.return_value = MagicMock(
        spec=Book, file_name="test-book.pdf", title="Test Book"
    )

    mock_result_page = MagicMock()
    mock_result_page.scalars().all.return_value = [mock_page]

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from books" in stmt_str:
            return mock_result_book
        elif "from pages" in stmt_str:
            return mock_result_page
        else:
            return MagicMock()

    mock_session.execute.side_effect = mock_execute

    with patch("app.db.session.async_session_factory") as mock_session_factory, patch(
        "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
        new_callable=AsyncMock,
    ) as mock_get_value, patch(
        "app.utils.redis_lock.MultiPageLock"
    ) as mock_lock_cls, patch(
        "services.worker.jobs.ocr_job.fitz.open"
    ) as mock_fitz_open, patch(
        "services.worker.jobs.ocr_job.settings"
    ) as mock_settings, patch(
        "services.worker.jobs.ocr_job.storage"
    ) as mock_storage, patch(
        "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
    ) as mock_ocr_gemini, patch(
        "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
        new_callable=AsyncMock,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        # Mock Lock Manager
        mock_lock = AsyncMock()
        mock_lock.__aenter__.return_value = page_ids
        mock_lock_cls.return_value = mock_lock

        # Mock settings
        mock_settings.uploads_dir = pathlib.Path("/tmp/uploads")

        # Mock storage download_file
        mock_storage.download_file = AsyncMock()

        # Mock Configs
        mock_get_value.side_effect = lambda key, default=None: {
            "gemini_ocr_model": "gemini-2.0-flash",
            "ocr_max_parallel_pages": "4",
            "gemini_ocr_timeout": "30",
            "ocr_max_retry_count": "3",
        }.get(key, default)

        # Mock Fitz
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        # Mock OCR service response
        mock_ocr_gemini.return_value = "Ocr Text"

        # Execute
        await ocr_job(ctx, book_id, page_ids)

        # Verifications
        mock_ocr_gemini.assert_called_once()
        mock_session.commit.assert_called()

        found_success_update = False
        for call in mock_session.execute.call_args_list:
            stmt = call[0][0]
            stmt_str = str(stmt).lower()
            if "update" in stmt_str and "page" in stmt_str:
                params = stmt.compile().params
                if (
                    params.get("ocr_milestone") == "succeeded"
                    and params.get("text") == "Ocr Text"
                ):
                    found_success_update = True
        assert found_success_update


@pytest.mark.asyncio
async def test_ocr_job_failure_retry():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"
    page_ids = [101]

    # Mock DB Session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock page model (retry_count = 0, next retry is 1 < max 3, so should retry)
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.book_id = book_id
    mock_page.page_number = 1
    mock_page.retry_count = 0

    mock_result_book = MagicMock()
    mock_result_book.scalar_one_or_none.return_value = MagicMock(
        spec=Book, file_name="test-book.pdf", title="Test Book"
    )

    mock_result_page = MagicMock()
    mock_result_page.scalars().all.return_value = [mock_page]

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from books" in stmt_str:
            return mock_result_book
        elif "from pages" in stmt_str:
            return mock_result_page
        else:
            return MagicMock()

    mock_session.execute.side_effect = mock_execute

    with patch("app.db.session.async_session_factory") as mock_session_factory, patch(
        "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
        new_callable=AsyncMock,
    ) as mock_get_value, patch(
        "app.utils.redis_lock.MultiPageLock"
    ) as mock_lock_cls, patch(
        "services.worker.jobs.ocr_job.fitz.open"
    ) as mock_fitz_open, patch(
        "services.worker.jobs.ocr_job.settings"
    ) as mock_settings, patch(
        "services.worker.jobs.ocr_job.storage"
    ) as mock_storage, patch(
        "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
    ) as mock_ocr_gemini, patch(
        "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
        new_callable=AsyncMock,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_lock = AsyncMock()
        mock_lock.__aenter__.return_value = page_ids
        mock_lock_cls.return_value = mock_lock

        mock_settings.uploads_dir = pathlib.Path("/tmp/uploads")

        # Mock storage download_file
        mock_storage.download_file = AsyncMock()

        # Mock Configs
        mock_get_value.side_effect = lambda key, default=None: {
            "gemini_ocr_model": "gemini-2.0-flash",
            "ocr_max_parallel_pages": "4",
            "gemini_ocr_timeout": "30",
            "ocr_max_retry_count": "3",
        }.get(key, default)

        # Mock Fitz
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        # Mock OCR service to raise failure
        mock_ocr_gemini.side_effect = Exception("API Timeout")

        # Execute
        await ocr_job(ctx, book_id, page_ids)

        # Verifications
        found_failed_update = False
        for call in mock_session.execute.call_args_list:
            stmt = call[0][0]
            stmt_str = str(stmt).lower()
            if "update" in stmt_str and "page" in stmt_str:
                params = stmt.compile().params
                if (
                    params.get("ocr_milestone") == "failed"
                    and params.get("retry_count") == 1
                ):
                    found_failed_update = True
        assert found_failed_update


@pytest.mark.asyncio
async def test_ocr_job_failure_exhausted_skip():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"
    page_ids = [101]

    # Mock DB Session
    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

    # Mock page model (retry_count = 2, next retry is 3 >= max 3, so should skip)
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.book_id = book_id
    mock_page.page_number = 1
    mock_page.retry_count = 2

    mock_result_book = MagicMock()
    mock_result_book.scalar_one_or_none.return_value = MagicMock(
        spec=Book, file_name="test-book.pdf", title="Test Book"
    )

    mock_result_page = MagicMock()
    mock_result_page.scalars().all.return_value = [mock_page]

    async def mock_execute(stmt, *args, **kwargs):
        stmt_str = str(stmt).lower()
        if "from books" in stmt_str:
            return mock_result_book
        elif "from pages" in stmt_str:
            return mock_result_page
        else:
            return MagicMock()

    mock_session.execute.side_effect = mock_execute

    with patch("app.db.session.async_session_factory") as mock_session_factory, patch(
        "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
        new_callable=AsyncMock,
    ) as mock_get_value, patch(
        "app.utils.redis_lock.MultiPageLock"
    ) as mock_lock_cls, patch(
        "services.worker.jobs.ocr_job.fitz.open"
    ) as mock_fitz_open, patch(
        "services.worker.jobs.ocr_job.settings"
    ) as mock_settings, patch(
        "services.worker.jobs.ocr_job.storage"
    ) as mock_storage, patch(
        "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
    ) as mock_ocr_gemini, patch(
        "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
        new_callable=AsyncMock,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_lock = AsyncMock()
        mock_lock.__aenter__.return_value = page_ids
        mock_lock_cls.return_value = mock_lock

        mock_settings.uploads_dir = pathlib.Path("/tmp/uploads")

        # Mock storage download_file
        mock_storage.download_file = AsyncMock()

        # Mock Configs
        mock_get_value.side_effect = lambda key, default=None: {
            "gemini_ocr_model": "gemini-2.0-flash",
            "ocr_max_parallel_pages": "4",
            "gemini_ocr_timeout": "30",
            "ocr_max_retry_count": "3",
        }.get(key, default)

        # Mock Fitz
        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        # Mock OCR service to raise failure
        mock_ocr_gemini.side_effect = Exception("API Timeout")

        # Execute
        await ocr_job(ctx, book_id, page_ids)

        # Verifications
        found_skipped_update = False
        for call in mock_session.execute.call_args_list:
            stmt = call[0][0]
            stmt_str = str(stmt).lower()
            if "update" in stmt_str and "page" in stmt_str:
                params = stmt.compile().params
                if (
                    params.get("ocr_milestone") == "succeeded"
                    and params.get("text") == ""
                ):
                    found_skipped_update = True
                    assert params.get("retry_count") == 3
                    assert "OCR failed after 3 retries" in params.get("error")
        assert found_skipped_update
