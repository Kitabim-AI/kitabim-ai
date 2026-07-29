"""Tests for the RAG answer-quality LLM judge (services/rag/judge.py)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.judge import score_answer


def _mock_llm(response_text: str):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response_text)
    return llm


@pytest.mark.asyncio
async def test_score_answer_happy_path():
    llm = _mock_llm(
        '{"faithfulness": 0.9, "answer_relevance": 0.8, "context_precision": 0.7}'
    )
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        scores = await score_answer(
            question="سوئال", answer="جاۋاب", context="مەزمۇن", model="gemini-test"
        )

    assert scores.faithfulness == 0.9
    assert scores.answer_relevance == 0.8
    assert scores.context_precision == 0.7


@pytest.mark.asyncio
async def test_score_answer_clamps_out_of_range_scores():
    llm = _mock_llm(
        '{"faithfulness": 1.5, "answer_relevance": -0.3, "context_precision": 0.5}'
    )
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        scores = await score_answer(
            question="q", answer="a", context="c", model="gemini-test"
        )

    assert scores.faithfulness == 1.0
    assert scores.answer_relevance == 0.0
    assert scores.context_precision == 0.5


@pytest.mark.asyncio
async def test_score_answer_extracts_json_from_surrounding_text():
    llm = _mock_llm(
        'Here is the result:\n{"faithfulness": 0.4, "answer_relevance": 0.6, '
        '"context_precision": 0.2}\nThanks.'
    )
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        scores = await score_answer(
            question="q", answer="a", context="c", model="gemini-test"
        )

    assert scores.faithfulness == 0.4


@pytest.mark.asyncio
async def test_score_answer_raises_on_no_json_object():
    llm = _mock_llm("I cannot evaluate this answer.")
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        with pytest.raises(ValueError, match="no JSON object"):
            await score_answer(
                question="q", answer="a", context="c", model="gemini-test"
            )


@pytest.mark.asyncio
async def test_score_answer_raises_on_missing_field():
    llm = _mock_llm('{"faithfulness": 0.9, "answer_relevance": 0.8}')
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        with pytest.raises(ValueError, match="missing/invalid score fields"):
            await score_answer(
                question="q", answer="a", context="c", model="gemini-test"
            )


@pytest.mark.asyncio
async def test_score_answer_raises_on_non_numeric_field():
    llm = _mock_llm(
        '{"faithfulness": "high", "answer_relevance": 0.8, "context_precision": 0.5}'
    )
    with patch("app.services.rag.judge.build_text_llm", return_value=llm):
        with pytest.raises(ValueError, match="missing/invalid score fields"):
            await score_answer(
                question="q", answer="a", context="c", model="gemini-test"
            )
