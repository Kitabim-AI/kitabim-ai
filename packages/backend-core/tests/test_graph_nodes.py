"""Unit tests for pure-Python graph node functions — no LLM, no DB required."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_ctx(**kw):
    ctx = MagicMock()
    ctx.current_page = kw.get("current_page", None)
    ctx.is_global = kw.get("is_global", False)
    ctx.book = kw.get("book", None)
    ctx.use_knowledge_graph_in_chat = kw.get("use_knowledge_graph_in_chat", False)
    ctx.history = kw.get("history", [])
    ctx.context_book_ids = kw.get("context_book_ids", [])
    ctx.character_categories = kw.get("character_categories", [])
    ctx.book_id = kw.get("book_id", "abc")
    return ctx


# ---------------------------------------------------------------------------
# detect_intent
# ---------------------------------------------------------------------------


class TestDetectIntent:
    def test_default_is_content_search(self):
        from app.services.rag.agent.graph_nodes import detect_intent

        ctx = _make_ctx()
        assert detect_intent("what is the main theme", ctx) == "content_search"

    def test_current_page_when_page_set_and_keyword_match(self):
        from app.services.rag.agent.graph_nodes import detect_intent

        ctx = _make_ctx(current_page=5)
        # Uyghur pattern for "what is on this page"
        assert detect_intent("بۇ بەتتە نېمە بار", ctx) == "current_page"

    def test_no_current_page_never_returns_current_page(self):
        from app.services.rag.agent.graph_nodes import detect_intent

        ctx = _make_ctx(current_page=None)
        assert detect_intent("بۇ بەتتە نېمە بار", ctx) == "content_search"

    def test_content_search_even_with_page_but_no_keyword(self):
        from app.services.rag.agent.graph_nodes import detect_intent

        ctx = _make_ctx(current_page=5)
        assert detect_intent("what is the author of this book", ctx) == "content_search"


# ---------------------------------------------------------------------------
# decompose_question
# ---------------------------------------------------------------------------


class TestDecomposeQuestion:
    def test_single_question_unchanged(self):
        from app.services.rag.agent.graph_nodes import decompose_question

        subs, was_split = decompose_question("what is this book about")
        assert subs == ["what is this book about"]
        assert was_split is False

    def test_two_question_marks_triggers_split_flag(self):
        from app.services.rag.agent.graph_nodes import decompose_question

        _, was_split = decompose_question("كىم يازغان؟ قاچان يازغان؟")
        assert was_split is True

    def test_comparison_keyword_triggers_split_flag(self):
        from app.services.rag.agent.graph_nodes import decompose_question

        _, was_split = decompose_question("what is similar between the two books")
        assert was_split is True

    def test_uyghur_comparison_keyword_triggers_split_flag(self):
        from app.services.rag.agent.graph_nodes import decompose_question

        _, was_split = decompose_question("ئوخشاشلىقى نېمە")
        assert was_split is True

    def test_compound_question_same_entity_single_mark(self):
        from app.services.rag.agent.graph_nodes import decompose_question

        # One question mark, no comparison — should NOT flag
        subs, was_split = decompose_question("what did the author write?")
        assert was_split is False
        assert len(subs) == 1


# ---------------------------------------------------------------------------
# grade_context
# ---------------------------------------------------------------------------


class TestGradeContext:
    def test_empty_returns_no_docs_string(self):
        from app.services.rag.agent.graph_nodes import grade_context

        text, before, after = grade_context([])
        assert "NO RELEVANT DOCUMENTS" in text
        assert before == 0
        assert after == 0

    def test_failed_observations_are_ignored(self):
        from app.services.rag.agent.graph_nodes import grade_context

        obs = [{"tool": "search_chunks", "result": {"ok": False, "error": "db down"}}]
        text, before, after = grade_context(obs)
        assert "NO RELEVANT DOCUMENTS" in text
        assert before == 0

    def test_deduplicates_same_book_page(self):
        from app.services.rag.agent.graph_nodes import grade_context

        obs = [
            {
                "tool": "search_chunks",
                "result": {
                    "ok": True,
                    "data": {
                        "chunks": [
                            {
                                "text": "A",
                                "title": "T",
                                "book_id": "1",
                                "page": 1,
                                "score": 0.9,
                            },
                            {
                                "text": "B dup",
                                "title": "T",
                                "book_id": "1",
                                "page": 1,
                                "score": 0.8,
                            },
                        ]
                    },
                },
            }
        ]
        _, before, after = grade_context(obs)
        assert before == 2
        assert after == 1  # second chunk is a dup by (book_id, page)

    def test_non_search_chunks_obs_adds_metadata(self):
        from app.services.rag.agent.graph_nodes import grade_context

        obs = [
            {
                "tool": "get_book_author",
                "result": {
                    "ok": True,
                    "data": {"context": "Author is John Doe"},
                },
            }
        ]
        text, before, after = grade_context(obs)
        assert "Author is John Doe" in text
        assert before == 0  # no chunks
        assert after == 0


# ---------------------------------------------------------------------------
# is_graph_enabled
# ---------------------------------------------------------------------------


class TestIsGraphEnabled:
    def test_disabled_when_kg_feature_off(self):
        from app.services.rag.agent.graph_nodes import is_graph_enabled

        ctx = _make_ctx(use_knowledge_graph_in_chat=False)
        assert is_graph_enabled(ctx) is False

    def test_enabled_global_with_kg_on(self):
        from app.services.rag.agent.graph_nodes import is_graph_enabled

        ctx = _make_ctx(use_knowledge_graph_in_chat=True, is_global=True)
        assert is_graph_enabled(ctx) is True

    def test_single_book_requires_complete_milestone(self):
        from app.services.rag.agent.graph_nodes import is_graph_enabled

        book = MagicMock()
        book.graph_milestone = "pending"
        ctx = _make_ctx(use_knowledge_graph_in_chat=True, is_global=False, book=book)
        assert is_graph_enabled(ctx) is False
        book.graph_milestone = "complete"
        assert is_graph_enabled(ctx) is True

    def test_global_no_book_with_kg_on(self):
        from app.services.rag.agent.graph_nodes import is_graph_enabled

        ctx = _make_ctx(use_knowledge_graph_in_chat=True, is_global=True)
        assert is_graph_enabled(ctx) is True


# ---------------------------------------------------------------------------
# extract_used_book_ids
# ---------------------------------------------------------------------------


class TestExtractUsedBookIds:
    def test_empty_observations_returns_empty_list(self):
        from app.services.rag.agent.graph_nodes import extract_used_book_ids

        assert extract_used_book_ids([]) == []

    def test_extracts_from_search_chunks(self):
        from app.services.rag.agent.graph_nodes import extract_used_book_ids

        obs = [
            {
                "tool": "search_chunks",
                "result": {
                    "ok": True,
                    "data": {
                        "chunks": [
                            {"book_id": "42"},
                            {"book_id": "43"},
                            {"book_id": "42"},  # dup
                        ]
                    },
                },
            }
        ]
        ids = extract_used_book_ids(obs)
        assert set(ids) == {"42", "43"}

    def test_ignores_failed_results(self):
        from app.services.rag.agent.graph_nodes import extract_used_book_ids

        obs = [
            {
                "tool": "search_chunks",
                "result": {"ok": False, "error": "db down"},
            }
        ]
        assert extract_used_book_ids(obs) == []


# ---------------------------------------------------------------------------
# populate_ctx_from_observations
# ---------------------------------------------------------------------------


class TestPopulateCtxFromObservations:
    def test_populates_eval_fields(self):
        from app.services.rag.agent.graph_nodes import populate_ctx_from_observations

        ctx = _make_ctx()
        ctx.retrieved_count = 0
        ctx.scores = []
        ctx.agent_steps = None
        ctx.agent_tools_called = []
        ctx.agent_retry_count = None
        ctx.agent_final_chunk_count = None
        ctx.graded_context = None

        obs = [
            {
                "tool": "search_chunks",
                "result": {
                    "ok": True,
                    "data": {
                        "chunks": [
                            {"text": "A", "book_id": "1", "page": 1, "score": 0.9}
                        ]
                    },
                },
            }
        ]
        populate_ctx_from_observations(ctx, obs, "[BookID: 1]...", llm_calls=1)
        assert ctx.retrieved_count == 1
        assert ctx.scores == [0.9]
        assert ctx.agent_steps == 1
        assert ctx.agent_retry_count == 1
        assert ctx.agent_final_chunk_count == 1
        assert ctx.graded_context == "[BookID: 1]..."
