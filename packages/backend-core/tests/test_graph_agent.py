"""Integration tests for run_graph_workflow_stream with mocked ADK runner."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _make_ctx(**kw):
    ctx = MagicMock()
    ctx.question = kw.get("question", "what is this book about")
    ctx.current_page = kw.get("current_page", None)
    ctx.is_global = kw.get("is_global", False)
    ctx.book = kw.get("book", None)
    ctx.use_knowledge_graph_in_chat = kw.get("use_knowledge_graph_in_chat", False)
    ctx.history = kw.get("history", [])
    ctx.context_book_ids = kw.get("context_book_ids", [])
    ctx.character_categories = kw.get("character_categories", [])
    ctx.book_id = kw.get("book_id", "abc")
    ctx.agent_model = "gemini-2.0-flash"
    ctx.user_id = "test-user"
    ctx.enriched_question = None
    ctx.used_book_ids = []
    ctx.retrieved_count = 0
    ctx.scores = []
    ctx.agent_steps = None
    ctx.agent_tools_called = []
    ctx.agent_retry_count = None
    ctx.agent_final_chunk_count = None
    ctx.graded_context = None
    ctx.use_deterministic_router = False
    return ctx


async def _make_empty_runner(*args, **kwargs):
    """Async generator that yields nothing — simulates agent with no tool calls."""
    return
    yield  # noqa: unreachable — makes this a valid async generator


def _patch_runner(mock_runner_cls):
    """Set up a patched InMemoryRunner that returns nothing."""
    instance = mock_runner_cls.return_value
    session = MagicMock()
    session.user_id = "test-user"
    session.id = "session-1"
    instance.session_service.create_session = AsyncMock(return_value=session)
    instance.run_async = _make_empty_runner
    return instance


@pytest.mark.asyncio
async def test_first_event_is_planning():
    """The very first event yielded must be planning with an intent field."""
    from app.services.rag.agent.graph_agent import run_graph_workflow_stream

    ctx = _make_ctx()
    with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
        _patch_runner(Mock)
        events = [e async for e in run_graph_workflow_stream(ctx, ctx.question)]

    assert events[0]["type"] == "planning"
    assert "intent" in events[0]
    assert events[0]["intent"] in ("current_page", "content_search")


@pytest.mark.asyncio
async def test_last_event_is_result_with_required_fields():
    """The last event must always be a result event with all required fields."""
    from app.services.rag.agent.graph_agent import run_graph_workflow_stream

    ctx = _make_ctx()
    with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
        _patch_runner(Mock)
        events = [e async for e in run_graph_workflow_stream(ctx, ctx.question)]

    result_events = [e for e in events if e.get("type") == "result"]
    assert (
        len(result_events) == 1
    ), f"Expected exactly 1 result event, got {len(result_events)}"

    result = result_events[0]
    assert "graded_context" in result
    assert "sub_questions" in result
    assert "observations" in result
    assert "before_count" in result
    assert "after_count" in result
    assert "llm_calls" in result


@pytest.mark.asyncio
async def test_empty_agent_produces_no_docs_context():
    """When agent makes no tool calls, graded_context should be the no-docs sentinel."""
    from app.services.rag.agent.graph_agent import run_graph_workflow_stream

    ctx = _make_ctx()
    with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
        _patch_runner(Mock)
        events = [e async for e in run_graph_workflow_stream(ctx, ctx.question)]

    result = next(e for e in events if e.get("type") == "result")
    assert "NO RELEVANT DOCUMENTS" in result["graded_context"]
    assert result["before_count"] == 0


@pytest.mark.asyncio
async def test_ctx_is_mutated_with_eval_fields():
    """After run, ctx.used_book_ids and ctx.agent_steps should be set."""
    from app.services.rag.agent.graph_agent import run_graph_workflow_stream

    ctx = _make_ctx()
    with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
        _patch_runner(Mock)
        async for _ in run_graph_workflow_stream(ctx, ctx.question):
            pass

    # After the workflow, ctx eval fields must be set (even if 0/empty)
    assert isinstance(ctx.used_book_ids, list)
    assert ctx.agent_steps is not None


@pytest.mark.asyncio
async def test_multi_question_triggers_decompose_event():
    """Two question marks → decompose event should appear when LLM returns splits."""
    from app.services.rag.agent.graph_agent import run_graph_workflow_stream

    ctx = _make_ctx()
    two_q = "كىم يازغان؟ قاچان يازغان؟"

    # Mock LLM split to return 2 questions
    async def _fake_llm_split(question, model_name):
        return ["كىم يازغان؟", "قاچان يازغان؟"]

    with (
        patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock,
        patch(
            "app.services.rag.agent.graph_agent._llm_split_question",
            new=_fake_llm_split,
        ),
    ):
        _patch_runner(Mock)
        events = [e async for e in run_graph_workflow_stream(ctx, two_q)]

    decompose_events = [e for e in events if e.get("type") == "decompose"]
    assert len(decompose_events) == 1
    assert decompose_events[0]["count"] == 2
