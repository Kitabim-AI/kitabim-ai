from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.worker.jobs.embedding_job import embedding_job


@pytest.mark.asyncio
async def test_embedding_job_resets_to_idle_when_new_unembedded_chunks_arrive_mid_run():
    mock_session = AsyncMock()

    # Session 1: update Book in_progress + get embed_gemini_model + select unembedded chunks
    chunks_res = MagicMock()
    chunks_res.scalars.return_value.all.return_value = [
        SimpleNamespace(id=1, text="بىرىنچى ئابزاس", text_hash="h1")
    ]
    # Final session count queries:
    # 1. initial_chunk_ids still unembedded -> 0
    # 2. newly added unembedded chunks (NOT IN initial_chunk_ids) -> 2
    initial_rem_res = MagicMock()
    initial_rem_res.scalar.return_value = 0
    remaining_res = MagicMock()
    remaining_res.scalar.return_value = 2

    def fake_execute(stmt, *args, **kwargs):
        sql_str = str(stmt)
        if "SELECT chunks" in sql_str:
            return chunks_res
        if "count(chunks.id)" in sql_str:
            if "NOT IN" in sql_str:
                return remaining_res
            return initial_rem_res
        return MagicMock()

    mock_session.execute.side_effect = fake_execute

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    mock_config_repo = MagicMock()
    mock_config_repo.get_value = AsyncMock(return_value="gemini-embedding-001")

    mock_embedder = MagicMock()
    mock_embedder.aembed_documents = AsyncMock(return_value=[[0.1, 0.2]])

    with (
        patch(
            "services.worker.jobs.embedding_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.embedding_job.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
        patch(
            "services.worker.jobs.embedding_job.GeminiEmbeddings",
            return_value=mock_embedder,
        ),
    ):
        await embedding_job({}, book_id="book-123")

    executed_updates = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in mock_session.execute.call_args_list
        if "UPDATE books" in str(call.args[0])
    ]
    assert any("embedding_milestone='idle'" in sql for sql in executed_updates)
    assert not any("embedding_milestone='complete'" in sql for sql in executed_updates)


@pytest.mark.asyncio
async def test_embedding_job_fails_and_increments_retry_when_batch_chunk_stays_unembedded():
    mock_session = AsyncMock()

    chunks_res = MagicMock()
    chunks_res.scalars.return_value.all.return_value = [
        SimpleNamespace(id=1, text="بىرىنچى ئابزاس", text_hash="h1")
    ]
    # Initial chunk id 1 remained unembedded after the loop
    initial_rem_res = MagicMock()
    initial_rem_res.scalar.return_value = 1

    def fake_execute(stmt, *args, **kwargs):
        sql_str = str(stmt)
        if "SELECT chunks" in sql_str:
            return chunks_res
        if "count(chunks.id)" in sql_str:
            return initial_rem_res
        return MagicMock()

    mock_session.execute.side_effect = fake_execute

    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = False

    mock_config_repo = MagicMock()
    mock_config_repo.get_value = AsyncMock(return_value="gemini-embedding-001")

    mock_embedder = MagicMock()
    mock_embedder.aembed_documents = AsyncMock(return_value=[[0.1, 0.2]])

    with (
        patch(
            "services.worker.jobs.embedding_job.db_session.async_session_factory",
            return_value=mock_cm,
        ),
        patch(
            "services.worker.jobs.embedding_job.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
        patch(
            "services.worker.jobs.embedding_job.GeminiEmbeddings",
            return_value=mock_embedder,
        ),
    ):
        await embedding_job({}, book_id="book-123")

    executed_updates = [
        str(call.args[0].compile(compile_kwargs={"literal_binds": True}))
        for call in mock_session.execute.call_args_list
        if "UPDATE books" in str(call.args[0])
    ]
    assert any("embedding_milestone='failed'" in sql for sql in executed_updates)
    assert any(
        "embedding_retry_count=(books.embedding_retry_count + 1)" in sql
        for sql in executed_updates
    )
    assert not any("embedding_milestone='idle'" in sql for sql in executed_updates)
