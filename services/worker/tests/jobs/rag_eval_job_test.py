"""Tests for rag_eval_job (services/worker/jobs/rag_eval_job.py)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from services.worker.jobs.rag_eval_job import rag_eval_job
from app.services.rag.judge import JudgeScores


def _make_mock_row(question="q", answer="a", context="c"):
    row = MagicMock()
    row.question = question
    row.answer = answer
    row.retrieved_context = context
    return row


@pytest.mark.asyncio
async def test_rag_eval_job_success():
    ctx = {"redis": AsyncMock()}
    row = _make_mock_row()

    mock_session = AsyncMock()

    with patch("app.db.session.async_session_factory") as mock_factory, patch(
        "services.worker.jobs.rag_eval_job.RAGEvaluationsRepository"
    ) as mock_repo_cls, patch(
        "services.worker.jobs.rag_eval_job.SystemConfigsRepository"
    ) as mock_config_cls, patch(
        "services.worker.jobs.rag_eval_job.score_answer", new_callable=AsyncMock
    ) as mock_score:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=row)
        mock_repo.update_one = AsyncMock()

        mock_config_cls.return_value.get_value = AsyncMock(
            return_value="gemini-judge-test"
        )

        mock_score.return_value = JudgeScores(
            faithfulness=0.9, answer_relevance=0.8, context_precision=0.7
        )

        await rag_eval_job(ctx, 42)

    mock_score.assert_awaited_once_with(
        question="q", answer="a", context="c", model="gemini-judge-test"
    )
    mock_repo.update_one.assert_awaited_once_with(
        42,
        faithfulness_score=0.9,
        answer_relevance_score=0.8,
        context_precision_score=0.7,
        eval_status="completed",
    )
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rag_eval_job_row_not_found():
    ctx = {"redis": AsyncMock()}
    mock_session = AsyncMock()

    with patch("app.db.session.async_session_factory") as mock_factory, patch(
        "services.worker.jobs.rag_eval_job.RAGEvaluationsRepository"
    ) as mock_repo_cls, patch(
        "services.worker.jobs.rag_eval_job.score_answer", new_callable=AsyncMock
    ) as mock_score:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=None)
        mock_repo.update_one = AsyncMock()

        await rag_eval_job(ctx, 999)

    mock_score.assert_not_awaited()
    mock_repo.update_one.assert_not_awaited()
    mock_session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_rag_eval_job_judge_failure_marks_failed_without_raising():
    ctx = {"redis": AsyncMock()}
    row = _make_mock_row()
    mock_session = AsyncMock()

    with patch("app.db.session.async_session_factory") as mock_factory, patch(
        "services.worker.jobs.rag_eval_job.RAGEvaluationsRepository"
    ) as mock_repo_cls, patch(
        "services.worker.jobs.rag_eval_job.SystemConfigsRepository"
    ) as mock_config_cls, patch(
        "services.worker.jobs.rag_eval_job.score_answer", new_callable=AsyncMock
    ) as mock_score:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=row)
        mock_repo.update_one = AsyncMock()

        mock_config_cls.return_value.get_value = AsyncMock(
            return_value="gemini-judge-test"
        )
        mock_score.side_effect = ValueError("malformed judge output")

        # Must NOT raise — single-attempt policy, failure is recorded, not propagated
        await rag_eval_job(ctx, 42)

    mock_repo.update_one.assert_awaited_once_with(42, eval_status="failed")
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_rag_eval_job_handles_missing_answer_and_context():
    """A row with null answer/retrieved_context (shouldn't happen in practice,
    but the job must not crash) passes empty strings to the judge."""
    ctx = {"redis": AsyncMock()}
    row = _make_mock_row(answer=None, context=None)
    mock_session = AsyncMock()

    with patch("app.db.session.async_session_factory") as mock_factory, patch(
        "services.worker.jobs.rag_eval_job.RAGEvaluationsRepository"
    ) as mock_repo_cls, patch(
        "services.worker.jobs.rag_eval_job.SystemConfigsRepository"
    ) as mock_config_cls, patch(
        "services.worker.jobs.rag_eval_job.score_answer", new_callable=AsyncMock
    ) as mock_score:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=None)

        mock_repo = mock_repo_cls.return_value
        mock_repo.get = AsyncMock(return_value=row)
        mock_repo.update_one = AsyncMock()
        mock_config_cls.return_value.get_value = AsyncMock(return_value="model")
        mock_score.return_value = JudgeScores(0.0, 0.0, 0.0)

        await rag_eval_job(ctx, 1)

    mock_score.assert_awaited_once_with(
        question="q", answer="", context="", model="model"
    )
