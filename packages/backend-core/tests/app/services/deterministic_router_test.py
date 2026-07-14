import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.context import QueryContext
from app.services.rag.agent.deterministic_handler import (
    DeterministicRAGHandler,
    _extract_dictionary_term,
)


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

    async def mock_analyze(question, ctx):
        needs_rewrite = False
        rewritten_question = None
        if len(ctx.history) > 0 and ("ئۇ" in question or "ئۇچۇ" in question):
            needs_rewrite = True
            rewritten_question = "Mock standalone question"
        return {
            "is_current_page_query": False,
            "is_volume_shift": False,
            "target_volume": None,
            "needs_rewrite": needs_rewrite,
            "rewritten_question": rewritten_question,
            "catalog_subtype": None,
            "intent": "passage",
            "is_composite": False,
            "sub_questions": None,
        }

    handler._llm_analyze_query = mock_analyze

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

    async def mock_analyze(question, ctx):
        is_volume_shift = False
        target_volume = None
        if "توم" in question:
            is_volume_shift = True
            if "3" in question:
                target_volume = 3
            elif "كەيىنكى" in question:
                target_volume = (
                    (ctx.book.volume + 1) if ctx.book.volume is not None else 1
                )
            elif "ئالدىنقى" in question:
                target_volume = (
                    (ctx.book.volume - 1) if ctx.book.volume is not None else 1
                )
        return {
            "is_current_page_query": False,
            "is_volume_shift": is_volume_shift,
            "target_volume": target_volume,
            "needs_rewrite": False,
            "rewritten_question": None,
            "catalog_subtype": None,
            "intent": "passage",
            "is_composite": False,
            "sub_questions": None,
        }

    handler._llm_analyze_query = mock_analyze

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
async def test_extract_signals_fallback_to_keywords(mock_ctx):
    handler = DeterministicRAGHandler()
    mock_ctx.history = [{"role": "user", "text": "Who is Yunus?"}]

    # Mock _llm_analyze_query to raise an error to trigger keyword fallback path
    handler._llm_analyze_query = AsyncMock(side_effect=Exception("API Timeout"))

    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals("ئۇ كىم؟", mock_ctx)
        assert sig["needs_rewrite"] is True


@pytest.mark.asyncio
async def test_extract_signals_fallback_dictionary_question(mock_ctx):
    handler = DeterministicRAGHandler()
    handler._llm_analyze_query = AsyncMock(side_effect=Exception("API Timeout"))

    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals("democracy نىڭ ئۇيغۇرچىسى نېمە؟", mock_ctx)

    assert sig["intent"] == "dictionary"
    assert sig["dictionary_subtype"] == "english_uyghur"
    assert sig["dictionary_term"] == "democracy"


def test_extract_dictionary_term():
    assert _extract_dictionary_term("ئىنقىلاب دېگەن نېمە؟") == "ئىنقىلاب"
    assert _extract_dictionary_term("democracy نىڭ ئۇيغۇرچىسى نېمە؟") == "democracy"
    assert _extract_dictionary_term("«ئەركىنلىك» مەنىسى نېمە؟") == "ئەركىنلىك"


@pytest.mark.asyncio
async def test_classify_intent_skips(mock_ctx):
    handler = DeterministicRAGHandler()

    # Pre-extracted intent in signals -> returns directly
    signals = {"intent": "summary"}
    intent = await handler.classify_intent(signals, "test query", mock_ctx)
    assert intent == "summary"

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
    with (
        patch(
            "app.services.rag.agent.deterministic_handler.build_text_llm",
            return_value=mock_llm,
        ),
        patch("app.llm.models.build_text_llm", return_value=mock_llm),
    ):
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
        assert "search_chunks" in tools_called

        # Fallback target book ID is retrieved
        summary_call = next(o for o in observations if o["tool"] == "get_book_summary")
        assert summary_call["args"]["book_ids"] == ["book-456"]

        search_chunks_call = next(
            o for o in observations if o["tool"] == "search_chunks"
        )
        assert search_chunks_call["args"]["book_ids"] == ["book-456"]


@pytest.mark.asyncio
async def test_execute_path_c_summary_includes_all_sister_volumes(mock_ctx):
    """A named title resolving to 6 sister volumes must pass all 6 to
    get_book_summary — the 5-ID cap exists to bound unrelated-book results,
    not to truncate a single book's own volume series."""
    handler = DeterministicRAGHandler()
    signals = {"has_title": True}
    observations = []

    sister_volume_ids = [f"book-{i}" for i in range(1, 7)]
    sister_volume_books = [
        {
            "id": book_id,
            "title": "ئانا يۇرت",
            "author": "زوردۇن سابىر",
            "volume": i,
        }
        for i, book_id in enumerate(sister_volume_ids, start=1)
    ]

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "find_books_by_title":
            return {
                "ok": True,
                "book_ids": sister_volume_ids,
                "books": sister_volume_books,
                "found_count": len(sister_volume_ids),
            }
        if tool_name == "get_book_summary":
            return {
                "ok": True,
                "context": "Book Summary Info",
                "summaries": [{"book_id": bid} for bid in tool_args["book_ids"]],
                "found_count": len(tool_args["book_ids"]),
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

        summary_call = next(o for o in observations if o["tool"] == "get_book_summary")
        assert summary_call["args"]["book_ids"] == sister_volume_ids


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
                    "chunks": [{"text": "x", "score": 0.8} for _ in range(5)],
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


@pytest.mark.asyncio
async def test_universal_fallback_trigger_weak_score(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []

    # Initial search returns 2 chunks (< 4)
    # search_books_by_summary returns book-789
    # second search_chunks returns 5 chunks but with weak score (0.5)
    # third search_chunks is a global fallback call (book_ids=None)
    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-789"], "found_count": 1}
        if tool_name == "search_chunks":
            if tool_args.get("book_ids") == ["book-123"]:
                return {
                    "ok": True,
                    "chunks": [
                        {"text": "a", "score": 0.9},
                        {"text": "b", "score": 0.8},
                    ],
                    "found_count": 2,
                }
            if tool_args.get("book_ids") == ["book-789"]:
                return {
                    "ok": True,
                    "chunks": [{"text": "x", "score": 0.5} for _ in range(5)],
                    "found_count": 5,
                }
            if tool_args.get("book_ids") is None:
                return {
                    "ok": True,
                    "chunks": [{"text": "global", "score": 0.85}],
                    "found_count": 1,
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

        # Trigger fallback
        async for _ in handler._run_universal_fallback("hello", mock_ctx, observations):
            pass

        # Fallback should have run summary search, scoped search, and then global search due to weak score
        tools_called = [o["tool"] for o in observations]
        assert tools_called == [
            "search_chunks",
            "search_books_by_summary",
            "search_chunks",
            "search_chunks",
        ]

        # Last search chunk is global
        assert observations[-1]["args"]["book_ids"] is None
        assert observations[-1]["result"]["chunks"][0]["text"] == "global"


@pytest.mark.asyncio
async def test_execute_path_h_passage_global_search(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []

    # Path H, intent=passage: no context, no title/author, should query chunks globally directly
    signals = {
        "top_intent": "content_search",
        "has_title": False,
        "has_author": False,
        "is_volume_shift": False,
        "in_reader": False,
        "has_context_books": False,
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-999"], "found_count": 1}
        if tool_name == "search_chunks":
            if tool_args.get("book_ids") is None:
                # First call: global search
                return {
                    "ok": True,
                    "chunks": [{"text": "x", "score": 0.9}],
                    "found_count": 1,
                }
            elif tool_args.get("book_ids") == ["book-999"]:
                # Second call: fallback search within discovered books
                return {
                    "ok": True,
                    "chunks": [{"text": "y", "score": 0.9} for _ in range(4)],
                    "found_count": 4,
                }
        return {"ok": True}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "passage", signals, "ئېگىز تاغ سىرتىدا نېمە بار؟", mock_ctx, observations
        ):
            pass

        tools_called = [o["tool"] for o in observations]
        assert tools_called == [
            "search_chunks",
            "search_books_by_summary",
            "search_chunks",
        ]
        # First search chunks was global
        assert observations[0]["args"]["book_ids"] is None
        # Second search chunks was targeted
        assert observations[2]["args"]["book_ids"] == ["book-999"]


@pytest.mark.asyncio
async def test_execute_path_identity_query_knowledge_graph(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []

    async def mock_dispatch(tool_name, tool_args, ctx):
        return {"ok": True, "book_ids": ["book-123"], "found_count": 1}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        mock_ctx.context_book_ids = ["book-123"]
        mock_ctx.book_id = "book-123"
        async for _ in handler.execute_path(
            "identity", {}, "جانىبەك سۇلتان كىم؟", mock_ctx, observations
        ):
            pass

        tools_called = [o["tool"] for o in observations]
        assert "query_knowledge_graph" in tools_called


@pytest.mark.asyncio
async def test_execute_path_dictionary_translation(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "dictionary_subtype": "english_uyghur",
        "dictionary_term": "democracy",
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "translate_english_to_uyghur"
        assert tool_args == {"term": "democracy"}
        return {
            "ok": True,
            "context": "[Dictionary Source: English-Uyghur Dictionary, English: democracy]\nدېموكراتىيە",
            "entries": [{"english": "democracy", "uyghur": "دېموكراتىيە"}],
            "found_count": 1,
        }

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "dictionary",
            signals,
            "democracy نىڭ ئۇيغۇرچىسى نېمە؟",
            mock_ctx,
            observations,
        ):
            pass

    assert [o["tool"] for o in observations] == ["translate_english_to_uyghur"]


@pytest.mark.asyncio
async def test_execute_path_dictionary_history_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "dictionary_subtype": "history_term",
        "dictionary_term": "زىيائۇر راخمان",
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "lookup_history_term":
            return {"ok": True, "context": "", "entries": [], "found_count": 0}
        if tool_name == "search_language_sources":
            return {
                "ok": True,
                "context": "[Dictionary Source: Names Dictionary, Name: زىيائۇر راخمان]\nThis name exists in the names dictionary.",
                "results": {},
                "found_count": 1,
            }
        return {"ok": True, "found_count": 0}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "dictionary",
            signals,
            "زىيائۇر راخمان كىم؟",
            mock_ctx,
            observations,
        ):
            pass

    assert [o["tool"] for o in observations] == [
        "lookup_history_term",
        "search_language_sources",
    ]


@pytest.mark.asyncio
async def test_execute_path_dictionary_history_to_chunks_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "dictionary_subtype": "history_term",
        "dictionary_term": "كەربەلا ۋەقەسى",
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "lookup_history_term":
            return {"ok": True, "context": "", "entries": [], "found_count": 0}
        if tool_name == "search_language_sources":
            return {"ok": True, "context": "", "results": {}, "found_count": 0}
        if tool_name == "search_chunks":
            return {
                "ok": True,
                "chunks": [{"text": "كەربەلا ۋەقەسى"}],
                "found_count": 1,
            }
        return {"ok": True, "found_count": 0}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "dictionary",
            signals,
            "كەربەلا ۋەقەسى قانداق ۋەقە؟",
            mock_ctx,
            observations,
        ):
            pass

    assert [o["tool"] for o in observations] == [
        "lookup_history_term",
        "search_language_sources",
        "search_chunks",
    ]


@pytest.mark.asyncio
async def test_execute_path_dictionary_names(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "dictionary_subtype": "names",
        "dictionary_term": "ب",
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "lookup_uyghur_name"
        assert tool_args == {"term": "ب"}
        return {
            "ok": True,
            "context": "[Dictionary Source: Names Dictionary, Letter Group: ب]\nHere are Uyghur person names starting with the letter 'ب':\nباباجان, باباخان",
            "entries": [
                {"name": "باباجان", "letter_group": "ب"},
                {"name": "باباخان", "letter_group": "ب"},
            ],
            "found_count": 2,
        }

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "dictionary",
            signals,
            "ئۇيغۇرلاردا ب ھەرىپىدىن باشلانغان قانداق كىشى ئىسىملىرى بار؟",
            mock_ctx,
            observations,
        ):
            pass

    assert [o["tool"] for o in observations] == ["lookup_uyghur_name"]


@pytest.mark.asyncio
async def test_fallback_names_signals(mock_ctx):
    handler = DeterministicRAGHandler()

    # Mock LLM query analysis to raise an error so that keyword fallback is triggered
    async def mock_llm_analyze(question, ctx):
        raise ValueError("Simulate LLM error to trigger fallback")

    handler._llm_analyze_query = mock_llm_analyze

    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals(
            "ب ھەرىپىدىن باشلانغان كىشى ئىسىملىرى بارمۇ؟", mock_ctx
        )
        assert sig["intent"] == "dictionary"
        assert sig["dictionary_subtype"] == "names"
        assert sig["dictionary_term"] == "ب"


@pytest.mark.asyncio
async def test_execute_path_dictionary_proverbs(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "dictionary_subtype": "proverbs",
        "dictionary_term": "بىلىم",
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "lookup_proverbs"
        assert tool_args == {"term": "بىلىم"}
        return {
            "ok": True,
            "context": '[Dictionary/Culture Source: Uyghur Proverbs, Text: بىلىم يوق سەت]\nThis is a Uyghur proverb: "بىلىم يوق سەت"',
            "entries": [
                {"id": 1, "text": "بىلىم يوق سەت", "volume": 1, "page_number": 12},
            ],
            "found_count": 1,
        }

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "dictionary",
            signals,
            "بىلىم ھەققىدە ماقال-تەمسىللەر بارمۇ؟",
            mock_ctx,
            observations,
        ):
            pass

    assert [o["tool"] for o in observations] == ["lookup_proverbs"]


@pytest.mark.asyncio
async def test_fallback_proverbs_signals(mock_ctx):
    handler = DeterministicRAGHandler()

    # Mock LLM query analysis to raise an error so that keyword fallback is triggered
    async def mock_llm_analyze(question, ctx):
        raise ValueError("Simulate LLM error to trigger fallback")

    handler._llm_analyze_query = mock_llm_analyze

    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals(
            "بىلىم ھەققىدە ماقال-تەمسىللەر بارمۇ؟", mock_ctx
        )
        assert sig["intent"] == "dictionary"
        assert sig["dictionary_subtype"] == "proverbs"
        assert sig["dictionary_term"] == "بىلىم ھەققىدە"


def test_extract_dictionary_term_proverbs():
    assert _extract_dictionary_term("بىلىم ھەققىدە ماقال-تەمسىللەر") == "بىلىم ھەققىدە"
    assert _extract_dictionary_term("ئىلىم ھەققىدە ماقاللار") == "ئىلىم ھەققىدە"
    assert _extract_dictionary_term("proverb about truth") == "about truth"


@pytest.mark.asyncio
async def test_fallback_quran_signals(mock_ctx):
    handler = DeterministicRAGHandler()

    # Mock LLM query analysis to raise an error to trigger keyword fallback
    async def mock_llm_analyze(question, ctx):
        raise ValueError("Simulate LLM error to trigger fallback")

    handler._llm_analyze_query = mock_llm_analyze

    with patch(
        "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
        return_value=[],
    ):
        sig = await handler.extract_signals(
            "قۇرئان كەرىمدىكى 2-سۈرە 255-ئايەتنىڭ ئۇيغۇرچە مەنىسى نېمە؟", mock_ctx
        )
        assert sig["intent"] == "quran"
        assert sig["quran_surah"] == 2
        assert sig["quran_ayah"] == 255

        sig_keyword = await handler.extract_signals(
            "قۇرئاندىكى تەقۋادارلىق ھەققىدىكى ئايەتلەر قايسىلار؟", mock_ctx
        )
        assert sig_keyword["intent"] == "quran"
        assert sig_keyword["quran_surah"] is None
        assert sig_keyword["quran_ayah"] is None
        assert (
            sig_keyword["quran_query"]
            == "قۇرئاندىكى تەقۋادارلىق ھەققىدىكى ئايەتلەر قايسىلار؟"
        )


@pytest.mark.asyncio
async def test_execute_path_quran(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {
        "quran_surah": 1,
        "quran_ayah": 1,
        "quran_query": None,
    }

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "search_quran"
        assert tool_args == {"surah": 1, "ayah": 1, "q": "سۈرە 1-ئايەت 1"}
        return {
            "ok": True,
            "context": "Holy Quran Verse Context",
            "entries": [{"surah": 1, "ayah": 1}],
            "found_count": 1,
        }

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "quran",
            signals,
            "سۈرە 1-ئايەت 1",
            mock_ctx,
            observations,
        ):
            pass


@pytest.mark.asyncio
async def test_execute_path_catalog_author_of_no_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {"catalog_subtype": "author_of"}

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "get_book_author":
            return {
                "ok": True,
                "context": "The book 'ئانا يۇرت' was written by زوردۇن سابىر.",
                "title": "ئانا يۇرت",
                "author": "زوردۇن سابىر",
            }
        raise AssertionError(f"Unexpected tool call: {tool_name}")

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "catalog", signals, "ئانا يۇرتنى كىم يازغان؟", mock_ctx, observations
        ):
            pass

    # A direct match should not trigger the semantic-discovery fallback.
    assert [o["tool"] for o in observations] == ["get_book_author"]


@pytest.mark.asyncio
async def test_execute_path_catalog_author_of_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {"catalog_subtype": "author_of"}

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "get_book_author":
            return {"ok": True, "context": "", "title": None, "author": None}
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-999"], "found_count": 1}
        if tool_name == "search_chunks":
            return {
                "ok": True,
                "chunks": [{"text": f"chunk {i}", "score": 0.9} for i in range(4)],
                "found_count": 4,
            }
        return {"ok": True, "found_count": 0}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "catalog",
            signals,
            "بۆرە توپىدىن ئۆتكەن ئوغۇلنى كىم يازغان؟",
            mock_ctx,
            observations,
        ):
            pass

    tools_called = [o["tool"] for o in observations]
    assert tools_called == [
        "get_book_author",
        "search_books_by_summary",
        "search_chunks",
    ]

    search_chunks_call = next(o for o in observations if o["tool"] == "search_chunks")
    assert search_chunks_call["args"]["book_ids"] == ["book-999"]


@pytest.mark.asyncio
async def test_execute_path_catalog_books_by_fallback(mock_ctx):
    handler = DeterministicRAGHandler()
    observations = []
    signals = {"catalog_subtype": "books_by"}

    async def mock_dispatch(tool_name, tool_args, ctx):
        if tool_name == "get_books_by_author":
            return {"ok": True, "context": "", "books": []}
        if tool_name == "search_books_by_summary":
            return {"ok": True, "book_ids": ["book-111"], "found_count": 1}
        if tool_name == "search_chunks":
            return {
                "ok": True,
                "chunks": [{"text": f"chunk {i}", "score": 0.9} for i in range(4)],
                "found_count": 4,
            }
        return {"ok": True, "found_count": 0}

    with patch(
        "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
        side_effect=mock_dispatch,
    ):
        async for _ in handler.execute_path(
            "catalog",
            signals,
            "بۆرە توپىسى ھەققىدە يازغۇچى قانداق كىتابلار يازغان؟",
            mock_ctx,
            observations,
        ):
            pass

    tools_called = [o["tool"] for o in observations]
    assert tools_called == [
        "get_books_by_author",
        "search_books_by_summary",
        "search_chunks",
    ]
