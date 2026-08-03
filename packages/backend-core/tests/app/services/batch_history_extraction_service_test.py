import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.models import BatchHistoryExtractionJob, Book, Page
from app.services.batch_history_extraction_service import (
    submit_batch_history_extraction_job,
    poll_and_process_batch_history_jobs,
)


@pytest.mark.asyncio
async def test_submit_batch_history_extraction_job():
    mock_session = AsyncMock()

    # Mock Book and Pages queries
    mock_book = Book(id="book-123", title="ئۇيغۇر تارىخى", volume=1)
    mock_page1 = Page(id=1, book_id="book-123", page_number=1, text="تارىخىي مەزمۇن 1")
    mock_page2 = Page(id=2, book_id="book-123", page_number=2, text="تارىخىي مەزمۇن 2")

    mock_session.scalar.return_value = mock_book

    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [mock_page1, mock_page2]
    mock_session.execute.return_value = mock_pages_result

    with patch(
        "app.services.batch_history_extraction_service.storage.upload_bytes",
        new_callable=AsyncMock,
    ) as mock_upload, patch(
        "app.services.batch_history_extraction_service.storage.get_gs_uri",
        return_value="gs://bucket/batch_history/input.jsonl",
    ), patch(
        "app.services.batch_history_extraction_service._get_genai_client"
    ) as mock_get_client, patch(
        "app.services.batch_history_extraction_service._get_extraction_model",
        return_value="gemini-2.5-flash",
    ):
        mock_client = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "files/test-file-id"
        mock_client.files.upload.return_value = mock_file

        mock_batch = MagicMock()
        mock_batch.name = "batches/test-batch-123"
        mock_client.batches.create.return_value = mock_batch
        mock_get_client.return_value = mock_client

        job = await submit_batch_history_extraction_job(
            session=mock_session,
            book_id="book-123",
            min_significance=5,
            batch_size=15,
        )

        assert job.book_id == "book-123"
        assert job.gemini_batch_id == "batches/test-batch-123"
        assert job.status == "submitted"
        assert job.total_batches == 1
        mock_upload.assert_called_once()
        mock_client.batches.create.assert_called_once()


@pytest.mark.asyncio
async def test_poll_and_process_batch_history_jobs():
    mock_session = AsyncMock()

    mock_job = BatchHistoryExtractionJob(
        id="job-123",
        gemini_batch_id="batches/test-batch-123",
        book_id="book-123",
        status="submitted",
        min_significance=5,
        model_name="gemini-2.5-flash",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_active_res

    mock_book = Book(id="book-123", title="تارىخ", volume=1)
    mock_session.scalar.return_value = mock_book

    with patch(
        "app.services.batch_history_extraction_service._get_genai_client"
    ) as mock_get_client, patch(
        "app.services.batch_history_extraction_service.HistoryExtractionService._stage_entity",
        new_callable=AsyncMock,
    ) as mock_stage:
        mock_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "SUCCEEDED"
        mock_dest = MagicMock()
        mock_dest.file_name = "files/output-file-id"
        mock_dest.gcs_uri = None
        mock_batch_info.dest = mock_dest

        output_json = {
            "response": {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "entities": [
                                                {
                                                    "term": "سۇلتان سۇتۇق بۇغراخان",
                                                    "category": "figure",
                                                    "significance_score": 9,
                                                    "facts": [
                                                        {
                                                            "text": "قاراخانىيلار خانلىقىنىڭ خانى.",
                                                            "pages": [1],
                                                        }
                                                    ],
                                                }
                                            ]
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        }
        output_bytes = (json.dumps(output_json) + "\n").encode("utf-8")

        mock_client.batches.get.return_value = mock_batch_info
        mock_client.files.download.return_value = output_bytes
        mock_get_client.return_value = mock_client

        processed = await poll_and_process_batch_history_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "succeeded"
        mock_stage.assert_called_once()
