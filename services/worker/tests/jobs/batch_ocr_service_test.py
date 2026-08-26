import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import BatchOCRJob
from app.services.batch_ocr_service import _ingest_batch_ocr_results


@pytest.mark.asyncio
async def test_ingest_batch_ocr_results_blank_page_succeeds():
    """Verify that legitimately blank pages (empty transcription, finishReason=STOP) are marked succeeded."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [(101, 0)]
    mock_session.execute.return_value = mock_res
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    job = BatchOCRJob(
        id="job-1",
        book_id="book-1",
        page_ids=[101],
        status="running",
        total_pages=1,
    )

    batch_job_info = MagicMock()
    batch_job_info.dest = MagicMock()
    batch_job_info.dest.gcs_uri = None
    batch_job_info.dest.file_name = "files/test-out"

    # Simulate Gemini output with 0-length text on finishReason=STOP (blank page)
    result_line = json.dumps(
        {
            "custom_id": "page_101",
            "response": {
                "candidates": [
                    {
                        "content": {"parts": [{"text": ""}]},
                        "finishReason": "STOP",
                        "index": 0,
                    }
                ]
            },
        }
    )

    client = MagicMock()
    client.files.download.return_value = result_line.encode("utf-8")

    with patch(
        "app.services.batch_ocr_service.BookMilestoneService.update_book_milestone_for_step",
        new_callable=AsyncMock,
    ):
        await _ingest_batch_ocr_results(
            session=mock_session,
            job=job,
            batch_job_info=batch_job_info,
            client=client,
            ocr_max_retry_count=3,
        )

    assert job.status == "succeeded"
    assert job.processed_pages == 1
    # Check that session.add was called for PipelineEvent (ocr_succeeded)
    added_events = [
        arg[0][0]
        for arg in mock_session.add.call_args_list
        if hasattr(arg[0][0], "event_type")
    ]
    assert len(added_events) == 1
    assert added_events[0].event_type == "ocr_succeeded"


@pytest.mark.asyncio
async def test_ingest_batch_ocr_results_blocked_prompt_records_failure():
    """Verify that a prompt blocked response records a failure/retry."""
    mock_session = AsyncMock()
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [(102, 0)]
    mock_session.execute.return_value = mock_res
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()

    job = BatchOCRJob(
        id="job-2",
        book_id="book-2",
        page_ids=[102],
        status="running",
        total_pages=1,
    )

    batch_job_info = MagicMock()
    batch_job_info.dest = MagicMock()
    batch_job_info.dest.gcs_uri = None
    batch_job_info.dest.file_name = "files/test-out-2"

    result_line = json.dumps(
        {
            "custom_id": "page_102",
            "response": {
                "promptFeedback": {"blockReason": "OTHER"},
            },
        }
    )

    client = MagicMock()
    client.files.download.return_value = result_line.encode("utf-8")

    with patch(
        "app.services.batch_ocr_service.BookMilestoneService.update_book_milestone_for_step",
        new_callable=AsyncMock,
    ):
        await _ingest_batch_ocr_results(
            session=mock_session,
            job=job,
            batch_job_info=batch_job_info,
            client=client,
            ocr_max_retry_count=3,
        )

    assert job.status == "succeeded"
    assert job.processed_pages == 0
    added_events = [
        arg[0][0]
        for arg in mock_session.add.call_args_list
        if hasattr(arg[0][0], "event_type")
    ]
    assert len(added_events) == 1
    assert added_events[0].event_type == "ocr_failed"
