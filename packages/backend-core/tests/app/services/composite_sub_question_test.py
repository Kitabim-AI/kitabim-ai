"""Tests for _execute_workflow_stream's composite (multi sub-question)
handling: sub-questions must run concurrently (real wall-clock win, not
just "doesn't crash"), merge results back in original sub-question order
regardless of completion order, and propagate a failure from any one of
them.
"""

import asyncio
import time

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.context import QueryContext
from app.services.rag.agent.deterministic_handler import DeterministicRAGHandler

_DELAY = 0.05


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=QueryContext)

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute.return_value = mock_result

    ctx.session = session
    ctx.book_id = "global"
    ctx.is_global = True
    ctx.current_page = None
    ctx.character_categories = []
    ctx.context_book_ids = []
    ctx.history = []
    ctx.book = None
    ctx.agent_model = "test-model"
    ctx.user_id = "test-user"
    ctx.enriched_question = None
    ctx.question = "combined question"
    return ctx


def _open_passage_signals(sub_index: int) -> dict:
    return {
        "top_intent": "content_search",
        "has_title": False,
        "has_author": False,
        "is_volume_shift": False,
        "in_reader": False,
        "has_context_books": False,
        "intent": "passage",
        "sub_index": sub_index,
    }


@pytest.mark.asyncio
async def test_composite_sub_questions_run_concurrently_and_preserve_order(mock_ctx):
    handler = DeterministicRAGHandler()
    sub_items = [
        {"question": "Who wrote book A?"},
        {"question": "What is book B about?"},
    ]

    async def mock_extract_signals(question, ctx):
        return {
            "top_intent": "content_search",
            "is_composite": True,
            "sub_questions": sub_items,
            "needs_rewrite": False,
        }

    call_order = []

    async def mock_build_sub_signals(sub_item, ctx):
        index = sub_items.index(sub_item)
        call_order.append(("start", index))
        await asyncio.sleep(_DELAY)
        call_order.append(("end", index))
        return _open_passage_signals(index)

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "search_chunks"
        return {
            "ok": True,
            "chunks": [{"text": f"c{i}", "score": 0.9} for i in range(4)],
            "found_count": 4,
        }

    handler.extract_signals = mock_extract_signals
    handler._build_sub_signals_from_llm = mock_build_sub_signals

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        observations = []
        result_event = None
        start = time.monotonic()
        async for ev in handler._execute_workflow_stream(
            mock_ctx, "combined question", observations
        ):
            if ev.get("type") == "result":
                result_event = ev
        elapsed = time.monotonic() - start

    # Concurrency: two 0.05s-delayed sub-questions should overlap, not sum.
    # Sequential would take >= 2 * _DELAY; parallel should stay well under.
    assert (
        elapsed < 1.5 * _DELAY
    ), f"sub-questions did not appear to run concurrently: took {elapsed:.3f}s"
    # Both started before either finished — proves genuine overlap, not
    # just "fast enough by coincidence".
    assert call_order[0] == ("start", 0)
    assert call_order[1] == ("start", 1)

    # Order preserved: original sub-question order, not completion order.
    assert result_event["sub_questions"] == [
        "Who wrote book A?",
        "What is book B about?",
    ]

    # Both sub-questions' tool calls made it into the merged observations,
    # in original sub-question order.
    tools_called = [o["tool"] for o in observations]
    assert tools_called == ["search_chunks", "search_chunks"]


@pytest.mark.asyncio
async def test_composite_sub_question_failure_propagates(mock_ctx):
    handler = DeterministicRAGHandler()
    sub_items = [{"question": "good question"}, {"question": "bad question"}]

    async def mock_extract_signals(question, ctx):
        return {
            "top_intent": "content_search",
            "is_composite": True,
            "sub_questions": sub_items,
            "needs_rewrite": False,
        }

    async def mock_build_sub_signals(sub_item, ctx):
        index = sub_items.index(sub_item)
        if index == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(_DELAY * 3)  # slower — should be cancelled, not awaited out
        return _open_passage_signals(index)

    handler.extract_signals = mock_extract_signals
    handler._build_sub_signals_from_llm = mock_build_sub_signals

    with pytest.raises(RuntimeError, match="boom"):
        observations = []
        async for _ in handler._execute_workflow_stream(
            mock_ctx, "combined question", observations
        ):
            pass
