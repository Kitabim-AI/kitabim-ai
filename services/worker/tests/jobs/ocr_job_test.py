import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.ocr_job import ocr_job
from app.db.models import Page, Book
import pathlib


BASE_CONFIG = {
    "gemini_ocr_model": "gemini-2.0-flash",
    "ocr_max_parallel_pages": "4",
    "gemini_ocr_timeout": "30",
    "ocr_max_retry_count": "3",
    "gemini_batch_ocr_enabled": "false",
    "gemini_batch_ocr_batch_size": "50",
}


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

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch("app.utils.redis_lock.MultiPageLock") as mock_lock_cls,
        patch("services.worker.jobs.ocr_job.fitz.open") as mock_fitz_open,
        patch("services.worker.jobs.ocr_job.settings") as mock_settings,
        patch("services.worker.jobs.ocr_job.storage") as mock_storage,
        patch(
            "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
        ) as mock_ocr_gemini,
        patch(
            "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ),
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

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch("app.utils.redis_lock.MultiPageLock") as mock_lock_cls,
        patch("services.worker.jobs.ocr_job.fitz.open") as mock_fitz_open,
        patch("services.worker.jobs.ocr_job.settings") as mock_settings,
        patch("services.worker.jobs.ocr_job.storage") as mock_storage,
        patch(
            "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
        ) as mock_ocr_gemini,
        patch(
            "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ),
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

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch("app.utils.redis_lock.MultiPageLock") as mock_lock_cls,
        patch("services.worker.jobs.ocr_job.fitz.open") as mock_fitz_open,
        patch("services.worker.jobs.ocr_job.settings") as mock_settings,
        patch("services.worker.jobs.ocr_job.storage") as mock_storage,
        patch(
            "services.worker.jobs.ocr_job.ocr_page_with_gemini", new_callable=AsyncMock
        ) as mock_ocr_gemini,
        patch(
            "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ),
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


@pytest.mark.asyncio
async def test_ocr_job_batch_mode_delegates_to_batch_submission():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"
    page_ids = [101]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

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

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch("app.utils.redis_lock.MultiPageLock") as mock_lock_cls,
        patch("services.worker.jobs.ocr_job.fitz.open") as mock_fitz_open,
        patch("services.worker.jobs.ocr_job.settings") as mock_settings,
        patch("services.worker.jobs.ocr_job.storage") as mock_storage,
        patch(
            "services.worker.jobs.ocr_job.submit_batch_ocr_job", new_callable=AsyncMock
        ) as mock_submit_batch,
        patch(
            "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ) as mock_update_milestone,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_lock = AsyncMock()
        mock_lock.__aenter__.return_value = page_ids
        mock_lock_cls.return_value = mock_lock

        mock_settings.uploads_dir = pathlib.Path("/tmp/uploads")
        mock_storage.download_file = AsyncMock()

        mock_get_value.side_effect = lambda key, default=None: {
            **BASE_CONFIG,
            "gemini_batch_ocr_enabled": "true",
        }.get(key, default)

        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        await ocr_job(ctx, book_id, page_ids)

        # Batch submission is delegated to (one chunk since 1 page < batch_size)
        mock_submit_batch.assert_called_once()
        called_pages = mock_submit_batch.call_args.args[2]
        assert [p.id for p in called_pages] == [101]

        # No failure path was hit, so the milestone update should NOT run here
        mock_update_milestone.assert_not_called()
        mock_doc.close.assert_called_once()


@pytest.mark.asyncio
async def test_ocr_job_batch_mode_submission_error_marks_pages_failed():
    ctx = {"redis": AsyncMock(), "worker_id": "test_worker"}
    book_id = "test-book"
    page_ids = [101]

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.add = MagicMock()

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

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.ocr_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch("app.utils.redis_lock.MultiPageLock") as mock_lock_cls,
        patch("services.worker.jobs.ocr_job.fitz.open") as mock_fitz_open,
        patch("services.worker.jobs.ocr_job.settings") as mock_settings,
        patch("services.worker.jobs.ocr_job.storage") as mock_storage,
        patch(
            "services.worker.jobs.ocr_job.submit_batch_ocr_job", new_callable=AsyncMock
        ) as mock_submit_batch,
        patch(
            "services.worker.jobs.ocr_job.BookMilestoneService.update_book_milestone_for_step",
            new_callable=AsyncMock,
        ) as mock_update_milestone,
    ):
        mock_session_factory.return_value.__aenter__.return_value = mock_session

        mock_lock = AsyncMock()
        mock_lock.__aenter__.return_value = page_ids
        mock_lock_cls.return_value = mock_lock

        mock_settings.uploads_dir = pathlib.Path("/tmp/uploads")
        mock_storage.download_file = AsyncMock()

        mock_get_value.side_effect = lambda key, default=None: {
            **BASE_CONFIG,
            "gemini_batch_ocr_enabled": "true",
        }.get(key, default)

        mock_doc = MagicMock()
        mock_fitz_open.return_value = mock_doc

        # Simulate a failure upstream of the Gemini API call itself (e.g. GCS
        # upload error) that submit_batch_ocr_job does not catch internally.
        mock_submit_batch.side_effect = Exception("GCS upload failed")

        await ocr_job(ctx, book_id, page_ids)

        found_failed_update = False
        for call in mock_session.execute.call_args_list:
            stmt = call[0][0]
            stmt_str = str(stmt).lower()
            if "update" in stmt_str and "page" in stmt_str:
                params = stmt.compile().params
                if params.get("ocr_milestone") == "failed":
                    found_failed_update = True
                    # retry_count is incremented via the SQL-side expression
                    # `Page.retry_count + 1`, so it compiles as a synthetic
                    # `retry_count_1` bind param rather than a literal `retry_count`.
                    assert params.get("retry_count_1") == 1
                    assert "GCS upload failed" in params.get("error")
        assert found_failed_update

        mock_update_milestone.assert_called_once_with(mock_session, book_id, "ocr")
        mock_doc.close.assert_called_once()
