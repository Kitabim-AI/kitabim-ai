import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import BatchLlmSpellCheckJob, Page
from app.services.batch_llm_spell_check_service import (
    submit_batch_llm_spell_check,
    poll_and_process_batch_llm_spell_check_jobs,
)


@pytest.mark.asyncio
async def test_submit_batch_llm_spell_check_builds_jsonl_and_creates_job():
    mock_session = AsyncMock()

    page1 = Page(id=1, book_id="book-1", page_number=1, text="page one text")
    page2 = Page(id=2, book_id="book-1", page_number=2, text="page two text")

    mock_pages_result = MagicMock()
    mock_pages_result.scalars.return_value.all.return_value = [page1, page2]

    mock_all_pages_result = MagicMock()
    mock_all_pages_result.scalars.return_value.all.return_value = [page1, page2]

    mock_session.execute.side_effect = [mock_pages_result, mock_all_pages_result]

    with (
        patch(
            "app.services.batch_llm_spell_check_service.storage.upload_bytes",
            new_callable=AsyncMock,
        ) as mock_upload,
        patch(
            "app.services.batch_llm_spell_check_service.storage.get_gs_uri",
            return_value="gs://bucket/batch_llm_spell_check/input.jsonl",
        ),
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service._get_llm_spell_check_model",
            new_callable=AsyncMock,
            return_value="gemini-3.1-flash-lite",
        ),
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_file = MagicMock()
        mock_file.name = "files/test-file-id"
        mock_client.files.upload.return_value = mock_file

        mock_batch = MagicMock()
        mock_batch.name = "batches/test-batch-123"
        mock_client.batches.create.return_value = mock_batch
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        job = await submit_batch_llm_spell_check(
            book_id="book-1", page_ids=[1, 2], session=mock_session
        )

        assert job.book_id == "book-1"
        assert job.gemini_batch_id == "batches/test-batch-123"
        assert job.status == "submitting"
        assert set(job.page_ids) == {1, 2}
        mock_upload.assert_called_once()
        mock_client.batches.create.assert_called_once()
        assert mock_repo.set_llm_spell_check_status.call_count == 2

        # Verify the uploaded JSONL used the correct custom_id -> page_id mapping
        uploaded_bytes = mock_upload.call_args[0][0]
        lines = uploaded_bytes.decode("utf-8").strip().split("\n")
        custom_ids = {json.loads(line)["custom_id"] for line in lines}
        assert custom_ids == {"1", "2"}


@pytest.mark.asyncio
async def test_poll_and_process_succeeded_job_applies_corrections_and_commits_per_page():
    mock_session = AsyncMock()

    mock_job = BatchLlmSpellCheckJob(
        id=1,
        gemini_batch_id="batches/test-batch-123",
        book_id="book-1",
        page_ids=[1],
        status="running",
        model_name="gemini-3.1-flash-lite",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_active_res

    page = Page(id=1, book_id="book-1", page_number=1, text="original text")
    mock_session.get = AsyncMock(return_value=page)

    with (
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "SUCCEEDED"
        mock_dest = MagicMock()
        mock_dest.file_name = "files/output-file-id"
        mock_dest.gcs_uri = None
        mock_batch_info.dest = mock_dest
        mock_client.batches.get.return_value = mock_batch_info

        output_line = json.dumps(
            {
                "custom_id": "1",
                "response": {
                    "candidates": [{"content": {"parts": [{"text": "corrected text"}]}}]
                },
            }
        )
        mock_client.files.download.return_value = output_line.encode("utf-8")
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "succeeded"
        assert page.text == "corrected text"
        mock_repo.set_llm_spell_check_status.assert_any_call("book-1", 1, "succeeded")


@pytest.mark.asyncio
async def test_poll_and_process_failed_job_resets_all_pages_to_failed():
    mock_session = AsyncMock()

    mock_job = BatchLlmSpellCheckJob(
        id=2,
        gemini_batch_id="batches/test-batch-456",
        book_id="book-1",
        page_ids=[1, 2],
        status="running",
        model_name="gemini-3.1-flash-lite",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_active_res

    page1 = Page(id=1, book_id="book-1", page_number=1, text="text 1")
    page2 = Page(id=2, book_id="book-1", page_number=2, text="text 2")

    async def mock_get(model, page_id):
        return page1 if page_id == 1 else page2

    mock_session.get = mock_get

    with (
        patch(
            "app.services.batch_llm_spell_check_service._get_genai_client"
        ) as mock_get_client,
        patch(
            "app.services.batch_llm_spell_check_service.PagesRepository"
        ) as mock_repo_cls,
    ):
        mock_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "FAILED"
        mock_client.batches.get.return_value = mock_batch_info
        mock_get_client.return_value = mock_client

        mock_repo = MagicMock()
        mock_repo.set_llm_spell_check_status = AsyncMock(return_value=True)
        mock_repo_cls.return_value = mock_repo

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "failed"
        calls = mock_repo.set_llm_spell_check_status.call_args_list
        assert ("book-1", 1, "failed") in [c.args for c in calls]
        assert ("book-1", 2, "failed") in [c.args for c in calls]


@pytest.mark.asyncio
async def test_poll_and_process_one_job_exception_does_not_stop_others():
    mock_session = AsyncMock()

    job_ok = BatchLlmSpellCheckJob(
        id=1,
        gemini_batch_id="batches/ok",
        book_id="book-1",
        page_ids=[1],
        status="running",
    )
    job_broken = BatchLlmSpellCheckJob(
        id=2,
        gemini_batch_id="batches/broken",
        book_id="book-2",
        page_ids=[2],
        status="running",
    )

    mock_active_res = MagicMock()
    mock_active_res.scalars.return_value.all.return_value = [job_broken, job_ok]
    mock_session.execute.return_value = mock_active_res

    with patch(
        "app.services.batch_llm_spell_check_service._get_genai_client"
    ) as mock_get_client:
        mock_client = MagicMock()

        def get_side_effect(name):
            if name == "batches/broken":
                raise RuntimeError("Gemini API error")
            info = MagicMock()
            info.state = "RUNNING"
            return info

        mock_client.batches.get.side_effect = get_side_effect
        mock_get_client.return_value = mock_client

        processed = await poll_and_process_batch_llm_spell_check_jobs(mock_session)

        # job_ok transitions to "running" (already was) -> not counted as processed,
        # job_broken raises and is caught -> loop completes without raising.
        assert processed == 0
        assert job_ok.status == "running"
