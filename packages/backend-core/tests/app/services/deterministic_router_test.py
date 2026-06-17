import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.context import QueryContext
from app.services.rag.agent.deterministic_handler import DeterministicRAGHandler


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=QueryContext)

    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute.return_value = mock_result

    ctx.session = session
    ctx.book_id = "book-123"
    ctx.is_global = False
    ctx.current_page = None
    ctx.character_categories = []
    ctx.context_book_ids = []
    ctx.history = []
    ctx.book = MagicMock()
    ctx.book.volume = 1
    ctx.book.graph_milestone = "idle"
    ctx.agent_model = "test-model"
    return ctx


@pytest.mark.asyncio
async def test_can_handle(mock_ctx):
    handler = DeterministicRAGHandler()
    mock_ctx.use_deterministic_router = True
    assert handler.can_handle(mock_ctx) is True

    mock_ctx.use_deterministic_router = False
    assert handler.can_handle(mock_ctx) is False


@pytest.mark.asyncio
async def test_extract_signals_pronouns(mock_ctx):
    handler = DeterministicRAGHandler()
    mock_ctx.history = [{"role": "user", "text": "Who is Yunus?"}]

    # 1. Exact pronoun
    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals("ئۇ كىم؟", mock_ctx)
        assert sig["needs_rewrite"] is True

        # 2. Pronoun with punctuation attached (boundary punctuation)
        sig = await handler.extract_signals("«ئۇ» نېمە قىلغان؟", mock_ctx)
        assert sig["needs_rewrite"] is True

        # 3. Topic-shift suffix (clitic)
        sig = await handler.extract_signals("ئۇچۇ؟", mock_ctx)
        assert sig["needs_rewrite"] is True

        # 4. Pronoun with no history -> should not need rewrite
        mock_ctx.history = []
        sig = await handler.extract_signals("ئۇ كىم؟", mock_ctx)
        assert sig["needs_rewrite"] is False


@pytest.mark.asyncio
async def test_extract_signals_volume_shift(mock_ctx):
    handler = DeterministicRAGHandler()
    mock_ctx.book.volume = 2

    # 1. Regex shift: 3-توم
    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals("3-تومدا نېمە بار؟", mock_ctx)
        assert sig["is_volume_shift"] is True
        assert sig["target_volume"] == 3

        # 2. Relative shift: كەيىنكى توم
        sig = await handler.extract_signals("كەيىنكى تومنى ئوقۇش", mock_ctx)
        assert sig["is_volume_shift"] is True
        assert sig["target_volume"] == 3

        # 3. Relative shift: ئالدىنقى توم
        sig = await handler.extract_signals("ئالدىنقى تومدا نېمە دېيىلگەن؟", mock_ctx)
        assert sig["is_volume_shift"] is True
        assert sig["target_volume"] == 1

        # 4. Relative shift safety: current_volume is None
        mock_ctx.book.volume = None
        sig = await handler.extract_signals("كەيىنكى توم", mock_ctx)
        assert sig["is_volume_shift"] is True
        assert sig["target_volume"] == 1


@pytest.mark.asyncio
async def test_classify_intent_skips(mock_ctx):
    handler = DeterministicRAGHandler()

    # Current page skips classification -> returns passage
    signals = {"top_intent": "current_page", "in_reader": True}
    intent = await handler.classify_intent(signals, "بۇ بەتتە نېمە بار؟", mock_ctx)
    assert intent == "passage"

    # Author but no title signals -> skips to passage
    signals = {"top_intent": "content_search", "has_author": True, "has_title": False}
    intent = await handler.classify_intent(
        signals, "سابىر يازغان كىتابلارنى ئاقتۇر", mock_ctx
    )
    assert intent == "passage"


@pytest.mark.asyncio
async def test_classify_intent_llm_call(mock_ctx):
    handler = DeterministicRAGHandler()
    signals = {"top_intent": "content_search", "has_title": True}

    # Mock the LLM output to return valid json
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value='{"intent": "identity"}')

    # Try patching the import in deterministic_handler as well as models module
    with patch(
        "app.services.rag.agent.deterministic_handler.build_text_llm",
        return_value=mock_llm,
    ), patch("app.llm.models.build_text_llm", return_value=mock_llm):
        try:
            intent = await handler.classify_intent(
                signals, "زوردۇن سابىر كىم؟", mock_ctx
            )
            assert intent == "identity"
        except Exception as e:
            import traceback

            traceback.print_exc()
            raise e


@pytest.mark.asyncio
async def test_execute_path_c_summary_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    signals = {"has_title": True}
    observations = []

    # Mock _dispatch_tool_with_retry
    # find_books_by_title returns empty book_ids
    # search_books_by_summary returns book-456
    # get_book_summary returns context text
    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "find_books_by_title":
            return {"ok": True, "book_ids": [], "found_count": 0}
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-456"], "found_count": 1}
        if tool_name == "get_book_summary":
            return {
                "ok": True,
                "context": "Book Summary Info",
                "summaries": [{"book_id": "book-456"}],
                "found_count": 1,
            }
        return {"ok": True}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "summary", signals, "ئانا يۇرت رومانىنى كۆرسەت", mock_ctx, observations
        ):
            pass

        # Check observations populated correctly
        tools_called = [o["tool"] for o in observations]
        assert "find_books_by_title" in tools_called
        assert "search_books_by_summary" in tools_called
        assert "get_book_summary" in tools_called

        # Fallback target book ID is retrieved
        summary_call = next(o for o in observations if o["tool"] == "get_book_summary")
        assert summary_call["args"]["book_ids"] == ["book-456"]


@pytest.mark.asyncio
async def test_universal_fallback_trigger(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []

    # Initial search returns 2 chunks (< 4)
    # search_books_by_summary returns book-789
    # second search_chunks returns 5 chunks
    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-789"], "found_count": 1}
        if tool_name == "search_chunks":
            # first call
            if tool_args.get("book_ids") == ["book-123"]:
                return {
                    "ok": True,
                    "chunks": [
                        {"text": "a", "score": 0.9},
                        {"text": "b", "score": 0.8},
                    ],
                    "found_count": 2,
                }
            # second call (fallback call)
            if tool_args.get("book_ids") == ["book-789"]:
                return {
                    "ok": True,
                    "chunks": [{"text": "x"} for _ in range(5)],
                    "found_count": 5,
                }
        return {"ok": True}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        # Initial search execution
        async for _ in handler._execute_tool(
            "search_chunks",
            {"query": "hello", "book_ids": ["book-123"]},
            mock_ctx,
            observations,
        ):
            pass
        assert len(observations) == 1

        # Trigger fallback
        async for _ in handler._run_universal_fallback("hello", mock_ctx, observations):
            pass

        # Fallback should have run search_books_by_summary and search_chunks on new ID
        tools_called = [o["tool"] for o in observations]
        assert tools_called == [
            "search_chunks",
            "search_books_by_summary",
            "search_chunks",
        ]

        # Last search chunk matches fallback book id
        assert observations[-1]["args"]["book_ids"] == ["book-789"]
