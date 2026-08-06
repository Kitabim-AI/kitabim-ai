import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import BatchOCRJob, Page
from app.services.batch_ocr_service import (
    submit_batch_ocr_job,
    poll_and_process_batch_ocr_jobs,
)


@pytest.mark.asyncio
async def test_submit_batch_ocr_job():
    mock_session = AsyncMock()
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.page_number = 1

    mock_doc = MagicMock()
    mock_fitz_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"test_image_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix
    mock_doc.load_page.return_value = mock_fitz_page

    with (
        patch(
            "app.services.batch_ocr_service._build_ocr_prompt",
            new_callable=AsyncMock,
        ) as mock_prompt,
        patch("app.services.batch_ocr_service.storage") as mock_storage,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
    ):
        mock_prompt.return_value = "Test Prompt"
        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = "gs://bucket/batch_ocr/inputs/job1.jsonl"

        mock_genai_client = MagicMock()
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/abc123"
        mock_genai_client.files.upload.return_value = mock_uploaded_file
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/123456"
        mock_genai_client.batches.create.return_value = mock_batch_job
        mock_client_fn.return_value = mock_genai_client

        batch_job = await submit_batch_ocr_job(
            mock_session,
            "book_123",
            [mock_page],
            mock_doc,
            "gemini-2.5-flash",
        )

        assert batch_job.book_id == "book_123"
        assert batch_job.gemini_batch_id == "batches/123456"
        assert batch_job.status == "submitted"
        assert batch_job.total_pages == 1
        mock_storage.upload_bytes.assert_called_once()
        mock_genai_client.files.upload.assert_called_once()
        mock_genai_client.batches.create.assert_called_once_with(
            model="gemini-2.5-flash", src="files/abc123"
        )

        jsonl_content = mock_storage.upload_bytes.call_args.args[0]
        request_line = json.loads(jsonl_content.decode("utf-8").splitlines()[0])
        assert (
            request_line["request"]["generation_config"]["thinking_config"][
                "thinking_budget"
            ]
            == 0
        )


@pytest.mark.asyncio
async def test_submit_batch_ocr_job_uses_thinking_level_for_v3_model():
    mock_session = AsyncMock()
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.page_number = 1

    mock_doc = MagicMock()
    mock_fitz_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"test_image_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix
    mock_doc.load_page.return_value = mock_fitz_page

    with (
        patch(
            "app.services.batch_ocr_service._build_ocr_prompt",
            new_callable=AsyncMock,
        ) as mock_prompt,
        patch("app.services.batch_ocr_service.storage") as mock_storage,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
    ):
        mock_prompt.return_value = "Test Prompt"
        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = "gs://bucket/batch_ocr/inputs/job1.jsonl"

        mock_genai_client = MagicMock()
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/abc123"
        mock_genai_client.files.upload.return_value = mock_uploaded_file
        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/123456"
        mock_genai_client.batches.create.return_value = mock_batch_job
        mock_client_fn.return_value = mock_genai_client

        await submit_batch_ocr_job(
            mock_session,
            "book_123",
            [mock_page],
            mock_doc,
            "gemini-3.6-flash",
        )

        jsonl_content = mock_storage.upload_bytes.call_args.args[0]
        request_line = json.loads(jsonl_content.decode("utf-8").splitlines()[0])
        thinking_config = request_line["request"]["generation_config"][
            "thinking_config"
        ]
        assert thinking_config == {"thinking_level": "MINIMAL"}


@pytest.mark.asyncio
async def test_submit_batch_ocr_job_submission_failure():
    mock_session = AsyncMock()
    mock_page = MagicMock(spec=Page)
    mock_page.id = 101
    mock_page.page_number = 1

    mock_doc = MagicMock()
    mock_fitz_page = MagicMock()
    mock_pix = MagicMock()
    mock_pix.tobytes.return_value = b"test_image_bytes"
    mock_fitz_page.get_pixmap.return_value = mock_pix
    mock_doc.load_page.return_value = mock_fitz_page

    with (
        patch(
            "app.services.batch_ocr_service._build_ocr_prompt",
            new_callable=AsyncMock,
        ) as mock_prompt,
        patch("app.services.batch_ocr_service.storage") as mock_storage,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_prompt.return_value = "Test Prompt"
        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = "gs://bucket/batch_ocr/inputs/job1.jsonl"

        mock_genai_client = MagicMock()
        mock_genai_client.files.upload.side_effect = RuntimeError(
            "Gemini API unavailable"
        )
        mock_client_fn.return_value = mock_genai_client
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        batch_job = await submit_batch_ocr_job(
            mock_session,
            "book_123",
            [mock_page],
            mock_doc,
            "gemini-3.5-flash",
        )

        assert batch_job.status == "failed"
        assert batch_job.gemini_batch_id is None

        # One session.execute call: the Page update marking pages failed
        assert mock_session.execute.call_count == 1
        update_stmt = mock_session.execute.call_args_list[0].args[0]
        compiled = str(update_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'failed'" in compiled
        assert "retry_count" in compiled

        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_123", "ocr"
        )
        assert mock_session.commit.call_count == 2


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_succeeded():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_999"
    mock_job.gemini_batch_id = "batches/999"
    mock_job.book_id = "book_123"
    mock_job.page_ids = [101]
    mock_job.status = "submitted"
    mock_job.created_at = datetime.now(timezone.utc)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    mock_db_result.fetchall.return_value = [(101, 0)]
    mock_session.execute.return_value = mock_db_result

    jsonl_output = json.dumps(
        {
            "custom_id": "page_101",
            "response": {
                "candidates": [{"content": {"parts": [{"text": "ئۇيغۇرچە تېكىست"}]}}]
            },
            "error": None,
        }
    )

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch("app.services.batch_ocr_service.storage"),
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"
        mock_batch_info.dest = MagicMock(gcs_uri=None, file_name="files/output-job-999")
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_genai_client.files.download.return_value = jsonl_output.encode("utf-8")
        mock_client_fn.return_value = mock_genai_client

        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        assert processed_count == 1
        assert mock_job.status == "succeeded"
        assert mock_job.processed_pages == 1
        mock_genai_client.files.download.assert_called_once_with(
            file="files/output-job-999"
        )
        mock_milestone_svc.update_book_milestone_for_step.assert_called_with(
            mock_session, "book_123", "ocr"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_timeout():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_111"
    mock_job.gemini_batch_id = "batches/111"
    mock_job.book_id = "book_456"
    mock_job.page_ids = [201, 202]
    mock_job.status = "running"
    mock_job.created_at = datetime.now(timezone.utc) - timedelta(hours=30)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    mock_session.execute.return_value = mock_db_result

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        assert processed_count == 0
        assert mock_job.status == "failed"
        # Timed-out jobs are never checked against the Gemini API
        mock_client_fn.return_value.batches.get.assert_not_called()
        mock_milestone_svc.update_book_milestone_for_step.assert_called_with(
            mock_session, "book_456", "ocr"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_failed_state():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_222"
    mock_job.gemini_batch_id = "batches/222"
    mock_job.book_id = "book_789"
    mock_job.page_ids = [301]
    mock_job.status = "running"
    mock_job.created_at = datetime.now(timezone.utc)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    mock_session.execute.return_value = mock_db_result

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_FAILED"
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_client_fn.return_value = mock_genai_client
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        assert processed_count == 0
        assert mock_job.status == "failed"
        mock_milestone_svc.update_book_milestone_for_step.assert_called_with(
            mock_session, "book_789", "ocr"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_no_active_jobs():
    mock_session = AsyncMock()
    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = []
    mock_session.execute.return_value = mock_db_result

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        assert processed_count == 0
        mock_client_fn.assert_not_called()


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_empty_response_marks_failed():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_333"
    mock_job.gemini_batch_id = "batches/333"
    mock_job.book_id = "book_999"
    mock_job.page_ids = [401]
    mock_job.status = "submitted"
    mock_job.created_at = datetime.now(timezone.utc)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    mock_db_result.fetchall.return_value = [(401, 0)]
    mock_session.execute.return_value = mock_db_result

    jsonl_output = json.dumps(
        {
            "custom_id": "page_401",
            "response": {"candidates": []},
            "error": None,
        }
    )

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch("app.services.batch_ocr_service.storage"),
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"
        mock_batch_info.dest = MagicMock(gcs_uri=None, file_name="files/output-job-333")
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_genai_client.files.download.return_value = jsonl_output.encode("utf-8")
        mock_client_fn.return_value = mock_genai_client

        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        # The batch job itself completed; the individual empty-response page
        # is marked failed rather than silently succeeding with blank text.
        assert processed_count == 1
        assert mock_job.status == "succeeded"
        assert mock_job.processed_pages == 0

        # call 0 = the active_jobs SELECT, call 1 = the retry_counts SELECT,
        # call 2 = the failed-page UPDATE
        page_update_stmt = mock_session.execute.call_args_list[2].args[0]
        compiled = str(page_update_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'failed'" in compiled
        assert "retry_count" in compiled


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_degenerate_response_marks_failed():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_555"
    mock_job.gemini_batch_id = "batches/555"
    mock_job.book_id = "book_777"
    mock_job.page_ids = [403]
    mock_job.status = "submitted"
    mock_job.created_at = datetime.now(timezone.utc)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    mock_db_result.fetchall.return_value = [(403, 0)]
    mock_session.execute.return_value = mock_db_result

    jsonl_output = json.dumps(
        {
            "custom_id": "page_403",
            "response": {
                "candidates": [{"content": {"parts": [{"text": "سۆز " * 100}]}}]
            },
            "error": None,
        }
    )

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch("app.services.batch_ocr_service.storage"),
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(return_value="24")

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"
        mock_batch_info.dest = MagicMock(gcs_uri=None, file_name="files/output-job-555")
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_genai_client.files.download.return_value = jsonl_output.encode("utf-8")
        mock_client_fn.return_value = mock_genai_client

        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        # The batch job itself completed; the runaway-repetition page is
        # marked failed rather than being stored as real page content.
        assert processed_count == 1
        assert mock_job.status == "succeeded"
        assert mock_job.processed_pages == 0

        page_update_stmt = mock_session.execute.call_args_list[2].args[0]
        compiled = str(page_update_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'failed'" in compiled
        assert "retry_count" in compiled


@pytest.mark.asyncio
async def test_poll_and_process_batch_ocr_jobs_empty_response_exhausted_retries_skips_page():
    mock_session = AsyncMock()
    mock_job = MagicMock(spec=BatchOCRJob)
    mock_job.id = "job_444"
    mock_job.gemini_batch_id = "batches/444"
    mock_job.book_id = "book_888"
    mock_job.page_ids = [402]
    mock_job.status = "submitted"
    mock_job.created_at = datetime.now(timezone.utc)

    mock_db_result = MagicMock()
    mock_db_result.scalars().all.return_value = [mock_job]
    # Page 402 has already failed twice; ocr_max_retry_count is 3, so this
    # third failure should exhaust retries and gracefully skip the page
    # instead of looping through pipeline_driver's retry-reset again.
    mock_db_result.fetchall.return_value = [(402, 2)]
    mock_session.execute.return_value = mock_db_result

    jsonl_output = json.dumps(
        {
            "custom_id": "page_402",
            "response": {"candidates": []},
            "error": None,
        }
    )

    with (
        patch(
            "app.services.batch_ocr_service.SystemConfigsRepository"
        ) as mock_repo_cls,
        patch("app.services.batch_ocr_service._get_genai_client") as mock_client_fn,
        patch("app.services.batch_ocr_service.storage"),
        patch(
            "app.services.batch_ocr_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_repo = mock_repo_cls.return_value
        mock_repo.get_value = AsyncMock(
            side_effect=lambda key, default=None: {
                "gemini_batch_ocr_timeout_hours": "24",
                "ocr_max_retry_count": "3",
            }.get(key, default)
        )

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"
        mock_batch_info.dest = MagicMock(gcs_uri=None, file_name="files/output-job-444")
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_genai_client.files.download.return_value = jsonl_output.encode("utf-8")
        mock_client_fn.return_value = mock_genai_client

        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()

        processed_count = await poll_and_process_batch_ocr_jobs(mock_session)

        assert processed_count == 1
        # Skipped page counts toward succeeded_pages so the job/book can
        # still complete instead of getting stuck failed.
        assert mock_job.processed_pages == 1

        page_update_stmt = mock_session.execute.call_args_list[2].args[0]
        compiled = str(page_update_stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "'succeeded'" in compiled
        assert "retry_count" in compiled

        skip_events = [
            call.args[0]
            for call in mock_session.add.call_args_list
            if getattr(call.args[0], "event_type", None) == "ocr_succeeded"
        ]
        assert len(skip_events) == 1
        assert json.loads(skip_events[0].payload)["skipped"] is True
