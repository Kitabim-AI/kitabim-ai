import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.scanners.chunking_scanner import run_chunking_scanner


@pytest.mark.asyncio
async def test_chunking_scanner_dispatches_job_for_ready_structure_books():
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}
    mock_session = AsyncMock()

    mock_claim_result = MagicMock()
    mock_claim_result.fetchall.return_value = [("book-1",), ("book-2",)]
    mock_session.execute.side_effect = [
        mock_claim_result,  # claim SELECT on Book
        MagicMock(),  # UPDATE Book -> in_progress
    ]

    with patch("app.db.session.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await run_chunking_scanner(ctx)

    assert mock_redis.enqueue_job.call_count == 2
    mock_redis.enqueue_job.assert_any_call("chunking_job", book_id="book-1")
    mock_redis.enqueue_job.assert_any_call("chunking_job", book_id="book-2")


@pytest.mark.asyncio
async def test_chunking_scanner_reverts_milestone_when_enqueue_returns_none():
    mock_redis = AsyncMock()
    mock_redis.enqueue_job.return_value = None
    ctx = {"redis": mock_redis, "worker_id": "test_worker"}
    mock_session = AsyncMock()

    mock_claim_result = MagicMock()
    mock_claim_result.fetchall.return_value = [("book-1",)]
    mock_session.execute.side_effect = [
        mock_claim_result,  # claim SELECT on Book
        MagicMock(),  # UPDATE Book -> in_progress
        MagicMock(),  # UPDATE Book -> idle on dropped job
    ]

    with patch("app.db.session.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await run_chunking_scanner(ctx)

    assert mock_session.execute.call_count == 3
    revert_stmt = mock_session.execute.call_args_list[2].args[0]
    compiled = str(revert_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "chunking_milestone='idle'" in compiled


@pytest.mark.asyncio
async def test_chunking_scanner_no_idle_books():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with patch("app.db.session.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await run_chunking_scanner(ctx)

    ctx["redis"].enqueue_job.assert_not_called()


@pytest.mark.asyncio
async def test_chunking_scanner_requires_structure_complete_in_query():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    mock_empty = MagicMock()
    mock_empty.fetchall.return_value = []
    mock_session.execute.return_value = mock_empty

    with patch("app.db.session.async_session_factory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        await run_chunking_scanner(ctx)

    claim_stmt = mock_session.execute.call_args_list[0].args[0]
    compiled = str(claim_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ocr_milestone" in compiled
    assert "structure_milestone" in compiled
    assert "complete" in compiled
    assert "chunking_milestone" in compiled
    assert "idle" in compiled
