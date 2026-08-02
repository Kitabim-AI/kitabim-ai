import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from services.worker.jobs.history_extraction_job import extract_book_history_terms_task


@pytest.mark.asyncio
async def test_extract_book_history_terms_task():
    mock_session = AsyncMock()
    mock_session_factory = MagicMock()
    mock_session_factory.return_value.__aenter__.return_value = mock_session

    ctx = {"db_session_factory": mock_session_factory}

    with patch(
        "services.worker.jobs.history_extraction_job.HistoryExtractionService"
    ) as mock_service_cls:
        mock_instance = AsyncMock()
        mock_instance.process_book_pages.return_value = [
            {"id": 1, "term": "قاراخانىيلار"}
        ]
        mock_service_cls.return_value = mock_instance

        with patch(
            "services.worker.jobs.history_extraction_job.get_book_pages",
            return_value=[{"page_number": 1, "content": "text"}],
        ):
            with patch(
                "services.worker.jobs.history_extraction_job.get_book_details",
                return_value={"title": "تارىخ", "volume": 1},
            ):
                res = await extract_book_history_terms_task(
                    ctx, book_id="book-99", min_significance=5
                )
                assert res["status"] == "success"
                assert res["stagedCount"] == 1
