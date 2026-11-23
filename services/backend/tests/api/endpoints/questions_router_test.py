import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_get_featured_questions_returns_id_and_question():
    setup_paths()
    from api.endpoints.questions_router import get_featured_questions
    from app.db.models import RAGEvaluation

    mock_session = AsyncMock()
    rows = [
        RAGEvaluation(id=10, question="سوئال 1", show_on_homepage=True),
        RAGEvaluation(id=11, question="سوئال 2", show_on_homepage=True),
    ]

    with patch(
        "api.endpoints.questions_router.RAGEvaluationsRepository.get_featured_question_items",
        AsyncMock(return_value=rows),
    ):
        res = await get_featured_questions(limit=20, session=mock_session)

    assert len(res) == 2
    assert res[0].id == 10
    assert res[0].question == "سوئال 1"
    assert res[1].id == 11
    assert res[1].question == "سوئال 2"


@pytest.mark.asyncio
async def test_get_featured_question_answer_cached_vs_miss():
    setup_paths()
    from api.endpoints.questions_router import get_featured_question_answer
    from app.db.models import RAGEvaluation

    mock_session = AsyncMock()
    qualifying = RAGEvaluation(
        id=10,
        question="سوئال 1",
        answer="تەييار جاۋاب [3-بەت](ref:book-1:3)",
        show_on_homepage=True,
        eval_status="completed",
        faithfulness_score=0.9,
        answer_relevance_score=0.85,
        context_precision_score=0.8,
        input_tokens=1400,
        output_tokens=300,
        cost_usd=0.00049,
    )

    with (
        patch(
            "api.endpoints.questions_router.RAGEvaluationsRepository.get_qualifying_sample_evaluation",
            AsyncMock(return_value=qualifying),
        ),
        patch(
            "api.endpoints.questions_router.RAGEvaluationsRepository.resolve_sample_used_book_ids",
            AsyncMock(return_value=["book-1"]),
        ),
    ):
        hit = await get_featured_question_answer(
            question="سوئال 1", eval_id=10, session=mock_session
        )

    assert hit.cached is True
    assert hit.eval_id == 10
    assert hit.answer == "تەييار جاۋاب [3-بەت](ref:book-1:3)"
    assert hit.used_book_ids == ["book-1"]
    assert hit.cost is not None
    assert hit.cost.input_tokens == 1400
    assert hit.cost.output_tokens == 300
    assert hit.cost.cost_usd == pytest.approx(0.00049)

    with patch(
        "api.endpoints.questions_router.RAGEvaluationsRepository.get_qualifying_sample_evaluation",
        AsyncMock(return_value=None),
    ):
        miss = await get_featured_question_answer(
            question="سوئال 1", eval_id=10, session=mock_session
        )

    assert miss.cached is False
    assert miss.answer is None
