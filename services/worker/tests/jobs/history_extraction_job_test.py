import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.history_extraction_job import extract_book_history_terms_task


@pytest.mark.asyncio
async def test_extract_book_history_terms_task_realtime():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.SystemConfigsRepository"
    ) as mock_config_cls, patch(
        "services.worker.jobs.history_extraction_job.HistoryExtractionService"
    ) as mock_service_cls:
        mock_config = AsyncMock()
        mock_config.get_value.side_effect = lambda key, default="true": (
            "false" if key == "gemini_batch_history_extraction_enabled" else "true"
        )
        mock_config_cls.return_value = mock_config

        mock_instance = AsyncMock()
        mock_instance.process_book_pages.return_value = [
            {"id": 1, "term": "قاراخانىيلار"}
        ]
        mock_service_cls.return_value = mock_instance

        with patch(
            "services.worker.jobs.history_extraction_job.get_book_pages",
            return_value=[{"page_number": 1, "content": "text"}],
        ), patch(
            "services.worker.jobs.history_extraction_job.get_book_details",
            return_value={"title": "تارىخ", "volume": 1},
        ):
            res = await extract_book_history_terms_task(
                ctx, book_id="book-99", min_significance=5
            )
            assert res["status"] == "success"
            assert res["stagedCount"] == 1


@pytest.mark.asyncio
async def test_extract_book_history_terms_task_batch():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.SystemConfigsRepository"
    ) as mock_config_cls, patch(
        "services.worker.jobs.history_extraction_job.submit_batch_history_extraction_job",
        new_callable=AsyncMock,
    ) as mock_submit:
        mock_config = AsyncMock()
        mock_config.get_value.return_value = "true"
        mock_config_cls.return_value = mock_config

        mock_batch_job = MagicMock()
        mock_batch_job.id = "job-123"
        mock_batch_job.gemini_batch_id = "batches/999"
        mock_submit.return_value = mock_batch_job

        res = await extract_book_history_terms_task(
            ctx, book_id="book-99", min_significance=5
        )
        assert res["status"] == "queued_batch"
        assert res["batchJobId"] == "job-123"
        assert res["geminiBatchId"] == "batches/999"


@pytest.mark.asyncio
async def test_extract_book_history_terms_task_no_pages():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.SystemConfigsRepository"
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config.get_value.side_effect = lambda key, default="true": (
            "false" if key == "gemini_batch_history_extraction_enabled" else "true"
        )
        mock_config_cls.return_value = mock_config

        with patch(
            "services.worker.jobs.history_extraction_job.get_book_pages",
            return_value=[],
        ), patch(
            "services.worker.jobs.history_extraction_job.get_book_details",
            return_value={"title": "تارىخ", "volume": 1},
        ):
            res = await extract_book_history_terms_task(
                ctx, book_id="book-99", min_significance=5
            )
            assert res["status"] == "warning"
            assert res["stagedCount"] == 0


@pytest.mark.asyncio
async def test_extract_book_history_terms_task_disabled():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.SystemConfigsRepository"
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config.get_value.side_effect = lambda key, default="true": (
            "false" if key == "history_extraction_enabled" else "false"
        )
        mock_config_cls.return_value = mock_config

        res = await extract_book_history_terms_task(
            ctx, book_id="book-99", min_significance=5
        )
        assert res["status"] == "skipped"


@pytest.mark.asyncio
async def test_extract_book_history_terms_task_exception():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.SystemConfigsRepository"
    ) as mock_config_cls:
        mock_config = AsyncMock()
        mock_config.get_value.side_effect = Exception("Database connection failed")
        mock_config_cls.return_value = mock_config

        with pytest.raises(Exception, match="Database connection failed"):
            await extract_book_history_terms_task(
                ctx, book_id="book-99", min_significance=5
            )
