from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from services.worker.scanners.embedding_scanner import run_embedding_scanner


def test_embedding_scanner_basic():
    """Basic unit test scaffold for embedding_scanner."""
    assert True


@pytest.mark.asyncio
async def test_embedding_scanner_isolates_per_book_submission_failure():
    """If batch submission raises on book-1, book-1 is marked failed and book-2 is still processed."""
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}

    claim_session = AsyncMock()
    claim_res = MagicMock()
    claim_res.fetchall.return_value = [("book-1",), ("book-2",)]
    claim_session.execute.return_value = claim_res

    book1_session = AsyncMock()
    book1_count_res = MagicMock()
    book1_count_res.scalar.return_value = 50
    book1_session.execute.return_value = book1_count_res

    book1_fail_session = AsyncMock()

    book2_session = AsyncMock()
    book2_count_res = MagicMock()
    book2_count_res.scalar.return_value = 50
    book2_session.execute.return_value = book2_count_res

    sessions = [claim_session, book1_session, book1_fail_session, book2_session]

    def make_cm():
        s = sessions.pop(0)
        cm = AsyncMock()
        cm.__aenter__.return_value = s
        cm.__aexit__.return_value = False
        return cm

    mock_config_repo = MagicMock()
    mock_config_repo.get_value = AsyncMock(return_value="true")

    async def fake_submit(session, book_id):
        if book_id == "book-1":
            raise RuntimeError("GCS upload error")
        return []

    with (
        patch(
            "services.worker.scanners.embedding_scanner.db_session.async_session_factory",
            side_effect=make_cm,
        ),
        patch(
            "services.worker.scanners.embedding_scanner.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
        patch(
            "services.worker.scanners.embedding_scanner.submit_batch_embedding_job",
            side_effect=fake_submit,
        ) as mock_submit,
    ):
        await run_embedding_scanner(ctx)

    assert mock_submit.await_count == 2
    fail_sql = str(
        book1_fail_session.execute.call_args.args[0].compile(
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "embedding_milestone='failed'" in fail_sql
    assert "embedding_retry_count=(books.embedding_retry_count + 1)" in fail_sql
