"""Tests for the LLM reranker (services/rag/agent/reranker.py)"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.agent.reranker import rerank_context
from app.services.rag.agent.config import AGENT_MAX_CONTEXT_CHUNKS


def _mock_llm(response_text: str):
    llm = MagicMock()
    llm.ainvoke = AsyncMock(return_value=response_text)
    return llm


def _chunk(book_id="b1", page=1, text="chunk text", score=0.5, **kw):
    c = {"book_id": book_id, "page": page, "text": text, "score": score}
    c.update(kw)
    return c


def _search_obs(chunks: list[dict]) -> dict:
    return {"tool": "search_chunks", "result": {"ok": True, "data": {"chunks": chunks}}}


@pytest.mark.asyncio
async def test_rerank_context_happy_path_orders_by_indices():
    observations = [
        _search_obs(
            [
                _chunk(book_id="b1", page=1, text="first"),
                _chunk(book_id="b1", page=2, text="second"),
                _chunk(book_id="b1", page=3, text="third"),
            ]
        )
    ]
    llm = _mock_llm("[3, 1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "question", observations, model="gemini-test"
        )

    assert before_count == 3
    assert after_count == 2
    # Candidate 3 (third) should appear before candidate 1 (first) in the context
    assert graded_context.index("third") < graded_context.index("first")
    assert "second" not in graded_context


@pytest.mark.asyncio
async def test_rerank_context_dedupes_by_book_id_and_page():
    observations = [
        _search_obs([_chunk(book_id="b1", page=1, text="dup")]),
        _search_obs([_chunk(book_id="b1", page=1, text="dup")]),
    ]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert before_count == 2  # raw chunks counted before dedup
    assert after_count == 1  # deduped down to one candidate
    prompt_arg = llm.ainvoke.await_args.args[0]
    assert prompt_arg.count("[1]") == 1  # only one candidate was numbered


@pytest.mark.asyncio
async def test_rerank_context_no_chunks_skips_llm_call():
    observations = [{"tool": "search_chunks", "result": {"ok": False}}]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert before_count == 0
    assert after_count == 0
    assert graded_context == "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
    llm.ainvoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_rerank_context_empty_relevant_list_is_not_an_error():
    """The judge legitimately deciding nothing is relevant (empty array) must
    not be treated as a malformed response — it still falls back to the
    MIN_CHUNKS_AFTER_GRADING floor (see the dedicated floor test below) rather
    than raising, so with the only available candidate it's kept, not
    discarded into an empty "not found" context."""
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("[]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == 1
    assert graded_context != "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."


@pytest.mark.asyncio
async def test_rerank_context_zero_relevant_falls_back_to_min_chunks_floor():
    """Mirrors _grade_context's existing MIN_CHUNKS_AFTER_GRADING floor
    (llm_routed_handler.py). Production incident: the reranker judged 0 of 25
    real candidates "relevant" for a question about a person who the library
    covers only via biographical/indirect passages (not a verbatim answer),
    producing a false "not found" turn even though _grade_context's looser
    heuristic had answered the same question successfully. A strict LLM
    relevance verdict must not fully empty the context when decent-scoring
    candidates exist — let the answer-generation LLM judge usability instead
    of a single reranker call unilaterally vetoing everything."""
    from app.services.rag.agent.config import MIN_CHUNKS_AFTER_GRADING

    chunks = [
        _chunk(book_id="b1", page=i, text=f"c{i}", score=float(5 - i)) for i in range(5)
    ]
    observations = [_search_obs(chunks)]
    llm = _mock_llm("[]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == MIN_CHUNKS_AFTER_GRADING
    # Highest-scored candidates (c0/5.0, c1/4.0, c2/3.0) kept, not the tail.
    assert "c0" in graded_context
    assert "c1" in graded_context
    assert "c2" in graded_context
    assert "c4" not in graded_context


@pytest.mark.asyncio
async def test_rerank_context_trims_input_to_rerank_max_input_chunks():
    from app.services.rag.agent.config import RERANK_MAX_INPUT_CHUNKS

    many_chunks = [
        _chunk(book_id="b1", page=i, text=f"chunk-{i}", score=float(i))
        for i in range(RERANK_MAX_INPUT_CHUNKS + 10)
    ]
    observations = [_search_obs(many_chunks)]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        await rerank_context("q", observations, model="gemini-test")

    prompt_arg = llm.ainvoke.await_args.args[0]
    numbered_count = prompt_arg.count("] [BookID:")
    assert numbered_count == RERANK_MAX_INPUT_CHUNKS
    # Highest-scored chunks (highest page/text index here) must be the ones kept
    assert f"chunk-{RERANK_MAX_INPUT_CHUNKS + 9}" in prompt_arg
    assert "chunk-0" not in prompt_arg


@pytest.mark.asyncio
async def test_rerank_context_caps_final_result_at_agent_max_context_chunks():
    n = AGENT_MAX_CONTEXT_CHUNKS + 5
    chunks = [_chunk(book_id="b1", page=i, text=f"c{i}") for i in range(n)]
    observations = [_search_obs(chunks)]
    indices = list(range(1, n + 1))
    llm = _mock_llm(str(indices))
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == AGENT_MAX_CONTEXT_CHUNKS


@pytest.mark.asyncio
async def test_rerank_context_raises_on_no_json_array():
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("I cannot decide.")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        with pytest.raises(ValueError, match="no JSON array"):
            await rerank_context("q", observations, model="gemini-test")


@pytest.mark.asyncio
async def test_rerank_context_raises_on_out_of_range_index():
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("[99]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        with pytest.raises(ValueError, match="out-of-range"):
            await rerank_context("q", observations, model="gemini-test")


@pytest.mark.asyncio
async def test_rerank_context_accepts_numeric_string_indices():
    """Exact shape of a production incident: despite the JSON-only
    instruction, the model returned indices as numeric strings (e.g. "3")
    rather than JSON integers. A numeric string is unambiguous — it must be
    coerced and honored, not rejected as out-of-range."""
    observations = [
        _search_obs(
            [
                _chunk(book_id="b1", page=1, text="first"),
                _chunk(book_id="b1", page=2, text="second"),
                _chunk(book_id="b1", page=3, text="third"),
            ]
        )
    ]
    llm = _mock_llm('["3", "1"]')
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == 2
    assert graded_context.index("third") < graded_context.index("first")
    assert "second" not in graded_context


@pytest.mark.asyncio
async def test_rerank_context_raises_on_malformed_json_inside_brackets():
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("[this is not valid json]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        # json.JSONDecodeError is itself a ValueError subclass — either way,
        # this must not be silently swallowed or partially applied.
        with pytest.raises(ValueError):
            await rerank_context("q", observations, model="gemini-test")


@pytest.mark.asyncio
async def test_rerank_context_ignores_trailing_commentary_after_array():
    """Regression test for a production failure: the model appended
    explanatory text after the JSON array (violating the "JSON only"
    instruction). A greedy bracket regex used to over-capture through to the
    LAST ']' anywhere in that commentary, producing "Extra data" JSON errors
    and an unnecessary fallback to _grade_context. raw_decode must parse only
    the array and ignore everything after it, regardless of what the
    trailing text contains."""
    observations = [
        _search_obs(
            [
                _chunk(book_id="b1", page=1, text="first"),
                _chunk(book_id="b1", page=2, text="second"),
            ]
        )
    ]
    llm = _mock_llm(
        "[2]\nI chose passage 2 because it directly answers the question "
        "(see the citation format [Source] for reference)."
    )
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == 1
    assert "second" in graded_context
    assert "first" not in graded_context


@pytest.mark.asyncio
async def test_rerank_context_requests_integer_array_response_schema():
    """Regression test for a production failure: the model returned numeric
    strings (e.g. "26") instead of JSON integers in the ranked-indices array,
    which the manual isinstance(idx, int) check then rejected as
    "out-of-range" even when the numeric value was valid. Constraining the
    response schema to list[int] via controlled generation prevents the model
    from emitting string-typed elements in the first place."""
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        await rerank_context("q", observations, model="gemini-test")

    config_arg = llm.ainvoke.await_args.kwargs["config"]
    assert config_arg.response_schema == list[int]


@pytest.mark.asyncio
async def test_rerank_context_empty_array_with_trailing_bracket_in_commentary():
    """Exact shape of the production incident: an empty array (legitimately
    no relevant passages) followed by explanatory text that itself mentions
    a bracketed reference. Must parse cleanly, not raise — and (per the
    MIN_CHUNKS_AFTER_GRADING floor) falls back to the available candidate
    rather than emptying the context outright."""
    observations = [_search_obs([_chunk()])]
    llm = _mock_llm("[]\nNone of the passages are relevant. See [reference] above.")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert after_count == 1
    assert graded_context != "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
