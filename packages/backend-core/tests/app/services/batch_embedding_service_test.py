import json
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import BatchEmbeddingJob, Chunk
from app.services.batch_embedding_service import (
    submit_batch_embedding_job,
    poll_and_process_batch_embedding_jobs,
    _get_embedding_dimensionality,
)


def test_embedding_dimensionality_helper():
    assert _get_embedding_dimensionality("gemini-embedding-2") == 3072
    assert _get_embedding_dimensionality("models/gemini-embedding-2") == 3072
    assert _get_embedding_dimensionality("text-embedding-004") == 768


@pytest.mark.asyncio
async def test_submit_batch_embedding_job_success():
    mock_session = AsyncMock()

    mock_chunk1 = MagicMock(spec=Chunk)
    mock_chunk1.id = 1
    mock_chunk1.book_id = "book_a"
    mock_chunk1.page_number = 1
    mock_chunk1.text = "Hello world chunk 1"

    mock_chunk2 = MagicMock(spec=Chunk)
    mock_chunk2.id = 2
    mock_chunk2.book_id = "book_b"
    mock_chunk2.page_number = 5
    mock_chunk2.text = "Hello world chunk 2"

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        (mock_chunk1, 101),
        (mock_chunk2, 102),
    ]
    mock_session.execute.return_value = mock_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch("app.services.batch_embedding_service.storage") as mock_storage,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
    ):
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_embedding_model": "models/gemini-embedding-2",
            "gemini_batch_embedding_max_chunks_per_job": "5000",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = (
            "gs://bucket/batch_embedding/inputs/job1.jsonl"
        )

        mock_genai_client = MagicMock()
        mock_uploaded_file = MagicMock()
        mock_uploaded_file.name = "files/embed_file_123"
        mock_genai_client.files.upload.return_value = mock_uploaded_file

        mock_batch_job = MagicMock()
        mock_batch_job.name = "batches/embed_999"
        mock_genai_client.batches.create_embeddings.return_value = mock_batch_job
        mock_client_fn.return_value = mock_genai_client

        jobs = await submit_batch_embedding_job(mock_session, [101, 102])

        assert len(jobs) == 1
        job = jobs[0]
        assert set(job.book_ids) == {"book_a", "book_b"}
        assert set(job.page_ids) == {101, 102}
        assert set(job.chunk_ids) == {1, 2}
        assert job.gemini_batch_id == "batches/embed_999"
        assert job.status == "submitted"
        assert job.total_chunks == 2

        mock_storage.upload_bytes.assert_called_once()
        mock_genai_client.files.upload.assert_called_once()
        mock_genai_client.batches.create_embeddings.assert_called_once_with(
            model="gemini-embedding-2", src="files/embed_file_123"
        )

        jsonl_content = mock_storage.upload_bytes.call_args.args[0]
        lines = jsonl_content.decode("utf-8").splitlines()
        assert len(lines) == 2
        line1 = json.loads(lines[0])
        assert line1["custom_id"] == "chunk_1"
        assert line1["request"]["output_dimensionality"] == 3072


@pytest.mark.asyncio
async def test_submit_batch_embedding_job_no_chunks():
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute.return_value = mock_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_embedding_model": "models/gemini-embedding-2",
            "gemini_batch_embedding_max_chunks_per_job": "5000",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        page_result = MagicMock()
        page_result.fetchall.return_value = [("book_a",)]
        mock_session.execute.side_effect = [mock_result, MagicMock(), page_result]

        jobs = await submit_batch_embedding_job(mock_session, [101])

        assert jobs == []
        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_a", "embedding"
        )


@pytest.mark.asyncio
async def test_submit_batch_embedding_job_submission_failure():
    mock_session = AsyncMock()

    mock_chunk = MagicMock(spec=Chunk)
    mock_chunk.id = 10
    mock_chunk.book_id = "book_x"
    mock_chunk.page_number = 1
    mock_chunk.text = "Error chunk"

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(mock_chunk, 201)]
    mock_session.execute.return_value = mock_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch("app.services.batch_embedding_service.storage") as mock_storage,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_embedding_model": "text-embedding-004",
            "gemini_batch_embedding_max_chunks_per_job": "5000",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = "gs://bucket/inputs/job_err.jsonl"

        mock_genai_client = MagicMock()
        mock_genai_client.files.upload.side_effect = Exception("API quota exceeded")
        mock_client_fn.return_value = mock_genai_client

        jobs = await submit_batch_embedding_job(mock_session, [201])

        assert len(jobs) == 1
        job = jobs[0]
        assert job.status == "failed"
        assert "API quota exceeded" in job.error
        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_x", "embedding"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_embedding_jobs_success():
    mock_session = AsyncMock()

    mock_job = MagicMock(spec=BatchEmbeddingJob)
    mock_job.id = "job_100"
    mock_job.gemini_batch_id = "batches/b100"
    mock_job.status = "submitted"
    mock_job.book_ids = ["book_a"]
    mock_job.page_ids = [101]
    mock_job.chunk_ids = [1]
    mock_job.created_at = datetime.now(timezone.utc)
    mock_job.gcs_output_uri = None

    mock_job_result = MagicMock()
    mock_job_result.scalars.return_value.all.return_value = [mock_job]

    chunk_rows_res = MagicMock()
    chunk_rows_res.fetchall.return_value = [(1, "book_a", 1)]

    page_rows_res = MagicMock()
    page_rows_res.fetchall.return_value = [(101, "book_a", 1, 0)]

    mock_session.execute.side_effect = [
        mock_job_result,
        MagicMock(),  # update Chunk
        chunk_rows_res,
        page_rows_res,
        MagicMock(),  # update Page
    ]

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_batch_embedding_timeout_hours": "24",
            "gemini_batch_embedding_max_retry_count": "3",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"
        mock_batch_info.dest = "files/out_123"
        mock_genai_client.batches.get.return_value = mock_batch_info

        dummy_vector = [0.1] * 768
        output_jsonl = json.dumps(
            {
                "custom_id": "chunk_1",
                "response": {"embedding": {"values": dummy_vector}},
            }
        ).encode("utf-8")
        mock_genai_client.files.download.return_value = output_jsonl
        mock_client_fn.return_value = mock_genai_client

        processed = await poll_and_process_batch_embedding_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "succeeded"
        assert mock_job.processed_chunks == 1
        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_a", "embedding"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_embedding_jobs_timeout():
    mock_session = AsyncMock()

    mock_job = MagicMock(spec=BatchEmbeddingJob)
    mock_job.id = "job_stale"
    mock_job.gemini_batch_id = "batches/stale"
    mock_job.status = "submitted"
    mock_job.book_ids = ["book_stale"]
    mock_job.page_ids = [500]
    mock_job.created_at = datetime.now(timezone.utc) - timedelta(hours=25)

    mock_job_result = MagicMock()
    mock_job_result.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_job_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_batch_embedding_timeout_hours": "24",
            "gemini_batch_embedding_max_retry_count": "3",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        processed = await poll_and_process_batch_embedding_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "failed"
        assert "timed out" in mock_job.error
        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_stale", "embedding"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_embedding_jobs_dest_object():
    """Verifies handling when dest is an object with a file_name attribute."""
    mock_session = AsyncMock()

    mock_job = MagicMock(spec=BatchEmbeddingJob)
    mock_job.id = "job_dest_obj"
    mock_job.gemini_batch_id = "batches/b_dest_obj"
    mock_job.status = "submitted"
    mock_job.book_ids = ["book_dest"]
    mock_job.page_ids = [200]
    mock_job.chunk_ids = [10]
    mock_job.created_at = datetime.now(timezone.utc)
    mock_job.gcs_output_uri = None

    mock_job_result = MagicMock()
    mock_job_result.scalars.return_value.all.return_value = [mock_job]

    chunk_rows_res = MagicMock()
    chunk_rows_res.fetchall.return_value = [(10, "book_dest", 1)]

    page_rows_res = MagicMock()
    page_rows_res.fetchall.return_value = [(200, "book_dest", 1, 0)]

    mock_session.execute.side_effect = [
        mock_job_result,
        MagicMock(),  # update Chunk
        chunk_rows_res,
        page_rows_res,
        MagicMock(),  # update Page
    ]

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_batch_embedding_timeout_hours": "24",
            "gemini_batch_embedding_max_retry_count": "3",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "JOB_STATE_SUCCEEDED"

        # Mock dest as an object with .file_name attribute (mimicking BatchJobDestination)
        mock_dest_obj = MagicMock()
        mock_dest_obj.file_name = "files/embed_out_object_789"
        mock_batch_info.dest = mock_dest_obj

        mock_genai_client.batches.get.return_value = mock_batch_info

        dummy_vector = [0.2] * 768
        output_jsonl = json.dumps(
            {
                "custom_id": "chunk_10",
                "response": {"embedding": {"values": dummy_vector}},
            }
        ).encode("utf-8")
        mock_genai_client.files.download.return_value = output_jsonl
        mock_client_fn.return_value = mock_genai_client

        processed = await poll_and_process_batch_embedding_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "succeeded"
        mock_genai_client.files.download.assert_called_once_with(
            file="files/embed_out_object_789"
        )


@pytest.mark.asyncio
async def test_submit_batch_embedding_job_page_boundary_packing():
    """Verifies whole pages are kept together in sub-batches."""
    mock_session = AsyncMock()

    # Page 1 has 2 chunks
    chunk1 = MagicMock(spec=Chunk, id=1, book_id="book_1", page_number=1, text="c1")
    chunk2 = MagicMock(spec=Chunk, id=2, book_id="book_1", page_number=1, text="c2")
    # Page 2 has 1 chunk
    chunk3 = MagicMock(spec=Chunk, id=3, book_id="book_1", page_number=2, text="c3")

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        (chunk1, 101),
        (chunk2, 101),
        (chunk3, 102),
    ]
    mock_session.execute.return_value = mock_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch("app.services.batch_embedding_service.storage") as mock_storage,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
    ):
        mock_config_repo = AsyncMock()
        # Set max_chunks_per_job to 2.
        # Page 1 has 2 chunks (fits in job 1). Page 2 has 1 chunk (would exceed 2 if combined, goes to job 2).
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_embedding_model": "models/gemini-embedding-2",
            "gemini_batch_embedding_max_chunks_per_job": "2",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_storage.upload_bytes = AsyncMock()
        mock_storage.get_gs_uri.return_value = "gs://bucket/inputs/job.jsonl"

        mock_genai_client = MagicMock()
        mock_uploaded_file = MagicMock(name="files/f123")
        mock_genai_client.files.upload.return_value = mock_uploaded_file
        mock_genai_client.batches.create_embeddings.return_value = MagicMock(
            name="batches/b123"
        )
        mock_client_fn.return_value = mock_genai_client

        jobs = await submit_batch_embedding_job(mock_session, [101, 102])

        assert len(jobs) == 2
        # Job 0 has Page 101 chunks [1, 2]
        assert set(jobs[0].page_ids) == {101}
        assert set(jobs[0].chunk_ids) == {1, 2}
        # Job 1 has Page 102 chunk [3]
        assert set(jobs[1].page_ids) == {102}
        assert set(jobs[1].chunk_ids) == {3}


@pytest.mark.asyncio
async def test_poll_and_process_batch_embedding_jobs_failed_state():
    """Verifies handling when Gemini batch job returns FAILED state."""
    mock_session = AsyncMock()

    mock_job = MagicMock(spec=BatchEmbeddingJob)
    mock_job.id = "job_failed"
    mock_job.gemini_batch_id = "batches/b_failed"
    mock_job.status = "submitted"
    mock_job.book_ids = ["book_fail"]
    mock_job.page_ids = [301]
    mock_job.created_at = datetime.now(timezone.utc)

    mock_job_result = MagicMock()
    mock_job_result.scalars.return_value.all.return_value = [mock_job]
    mock_session.execute.return_value = mock_job_result

    with (
        patch(
            "app.services.batch_embedding_service.SystemConfigsRepository"
        ) as mock_config_repo_cls,
        patch(
            "app.services.batch_embedding_service._get_genai_client"
        ) as mock_client_fn,
        patch(
            "app.services.batch_embedding_service.BookMilestoneService"
        ) as mock_milestone_svc,
    ):
        mock_milestone_svc.update_book_milestone_for_step = AsyncMock()
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_batch_embedding_timeout_hours": "24",
            "gemini_batch_embedding_max_retry_count": "3",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        mock_genai_client = MagicMock()
        mock_batch_info = MagicMock()
        mock_batch_info.state = "FAILED"
        mock_genai_client.batches.get.return_value = mock_batch_info
        mock_client_fn.return_value = mock_genai_client

        processed = await poll_and_process_batch_embedding_jobs(mock_session)

        assert processed == 1
        assert mock_job.status == "failed"
        mock_milestone_svc.update_book_milestone_for_step.assert_called_once_with(
            mock_session, "book_fail", "embedding"
        )


@pytest.mark.asyncio
async def test_poll_and_process_batch_embedding_jobs_no_active_jobs():
    """Verifies fast return when no active jobs exist."""
    mock_session = AsyncMock()
    mock_job_result = MagicMock()
    mock_job_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_job_result

    with patch(
        "app.services.batch_embedding_service.SystemConfigsRepository"
    ) as mock_config_repo_cls:
        mock_config_repo = AsyncMock()
        mock_config_repo.get_value.side_effect = lambda key, default=None: {
            "gemini_batch_embedding_timeout_hours": "24",
            "gemini_batch_embedding_max_retry_count": "3",
        }.get(key, default)
        mock_config_repo_cls.return_value = mock_config_repo

        processed = await poll_and_process_batch_embedding_jobs(mock_session)
        assert processed == 0
