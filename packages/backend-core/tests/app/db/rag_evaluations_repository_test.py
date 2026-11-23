import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, UTC
from app.db.repositories.rag_evaluations_repository import (
    RAGEvaluationsRepository,
    get_rag_evaluations_repository,
    is_qualifying_sample_answer,
)
from app.db.models import RAGEvaluation


@pytest.mark.asyncio
async def test_create_evaluation():
    session = AsyncMock()
    repo = RAGEvaluationsRepository(session)

    # Mock return values for create
    mock_eval = RAGEvaluation(id=1, question="Q?")
    with patch.object(repo, "create", return_value=mock_eval):
        res = await repo.create_evaluation(
            book_id="b1",
            is_global=False,
            question="Q?",
            current_page=1,
            retrieved_count=3,
            context_chars=100,
            scores=[0.9, 0.8],
            category_filter=["cat1"],
            latency_ms=150,
            answer_chars=200,
            user_id="u1",
        )
        assert res.id == 1
        assert res.question == "Q?"


@pytest.mark.asyncio
async def test_get_recent_evaluations():
    session = AsyncMock()
    repo = RAGEvaluationsRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [RAGEvaluation(id=1)]
    session.execute.return_value = mock_res

    res = await repo.get_recent_evaluations(limit=10, book_id="b1")
    assert len(res) == 1


@pytest.mark.asyncio
async def test_get_average_latency():
    session = AsyncMock()
    repo = RAGEvaluationsRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = 123.45
    session.execute.return_value = mock_res

    avg = await repo.get_average_latency(
        since=datetime.now(UTC) - timedelta(days=1), book_id="b1"
    )
    assert avg == 123.45

    mock_res.scalar_one_or_none.return_value = None
    avg = await repo.get_average_latency()
    assert avg == 0.0


@pytest.mark.asyncio
async def test_get_stats_summary():
    session = AsyncMock()
    repo = RAGEvaluationsRepository(session)

    mock_row = MagicMock()
    mock_row.total_queries = 100
    mock_row.avg_latency_ms = 150.0
    mock_row.avg_retrieved = 5.0
    mock_row.avg_context_chars = 1000.0
    mock_row.avg_answer_chars = 500.0

    mock_res = MagicMock()
    mock_res.fetchone.return_value = mock_row
    session.execute.return_value = mock_res

    stats = await repo.get_stats_summary(since=datetime.now(UTC))
    assert stats["total_queries"] == 100
    assert stats["avg_latency_ms"] == 150.0


def test_get_rag_evaluations_repository():
    session = MagicMock()
    repo = get_rag_evaluations_repository(session)
    assert isinstance(repo, RAGEvaluationsRepository)


def test_is_qualifying_sample_answer_checks_80_percent_threshold():
    passing = RAGEvaluation(
        id=10,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="مەھمۇد قەشقەرى مەشھۇر ئالىم.",
        eval_status="completed",
        faithfulness_score=0.8,
        answer_relevance_score=0.85,
        context_precision_score=0.9,
        context_recall_score=None,
    )
    assert is_qualifying_sample_answer(passing) is True

    low_precision = RAGEvaluation(
        id=11,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="مەھمۇد قەشقەرى مەشھۇر ئالىم.",
        eval_status="completed",
        faithfulness_score=0.95,
        answer_relevance_score=0.9,
        context_precision_score=0.79,
    )
    assert is_qualifying_sample_answer(low_precision) is False

    queued_row = RAGEvaluation(
        id=12,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="مەھمۇد قەشقەرى مەشھۇر ئالىم.",
        eval_status="queued",
        faithfulness_score=0.9,
        answer_relevance_score=0.9,
        context_precision_score=0.9,
    )
    assert is_qualifying_sample_answer(queued_row) is False

    empty_answer = RAGEvaluation(
        id=13,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="   ",
        eval_status="completed",
        faithfulness_score=0.9,
        answer_relevance_score=0.9,
        context_precision_score=0.9,
    )
    assert is_qualifying_sample_answer(empty_answer) is False


@pytest.mark.asyncio
async def test_get_qualifying_sample_evaluation_and_used_books():
    session = AsyncMock()
    repo = RAGEvaluationsRepository(session)

    qualifying_row = RAGEvaluation(
        id=42,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="جاۋاب [12-بەت](ref:book-123:12) ۋە [قۇرئان](ref:quran:1:1)",
        show_on_homepage=True,
        eval_status="completed",
        faithfulness_score=0.82,
        answer_relevance_score=0.88,
        context_precision_score=0.80,
    )
    hit_res = MagicMock()
    hit_res.scalar_one_or_none.return_value = qualifying_row
    session.execute.return_value = hit_res

    found = await repo.get_qualifying_sample_evaluation(
        question="مەھمۇد قەشقەرى كىم؟", eval_id=42
    )
    assert found is qualifying_row

    msg_res = MagicMock()
    msg_res.scalar_one_or_none.return_value = ["book-000"]
    session.execute.return_value = msg_res
    book_ids = await repo.resolve_sample_used_book_ids(qualifying_row)
    assert book_ids == ["book-000", "book-123"]

    below_threshold_row = RAGEvaluation(
        id=43,
        question="مەھمۇد قەشقەرى كىم؟",
        answer="جاۋاب",
        show_on_homepage=True,
        eval_status="completed",
        faithfulness_score=0.9,
        answer_relevance_score=0.75,
        context_precision_score=0.9,
    )
    miss_res = MagicMock()
    miss_res.scalar_one_or_none.return_value = below_threshold_row
    session.execute.return_value = miss_res

    not_found = await repo.get_qualifying_sample_evaluation(
        question="مەھمۇد قەشقەرى كىم؟", eval_id=43
    )
    assert not_found is None
