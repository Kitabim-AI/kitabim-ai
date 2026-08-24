# Agent-Driven Keyword Search Tool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the ADK Retrieval Agent a new tool, `search_keyword_phrase`, so ordinary (non-quoted) questions can get an exact-match lexical assist alongside vector search — without repeating the old OR-of-every-word flood bug.

**Architecture:** `docs/feature/graph-rag-with-GDS/keyword-search-rework-plan.md` already solved keyword search for *quoted* questions: `detect_phrase_intent()` gates a deterministic, pre-agent leg (`exact_phrase.py` / `retrieval.exact_phrase_chunk_search`) that bypasses the ADK agent loop entirely and runs `ChunksRepository.keyword_search()` (Postgres `phraseto_tsquery` phrase match over `pages.text_search`, capped by `rag_keyword_top_k`, guarded by `work_mem`/`statement_timeout`). That doc explicitly ruled out "LLM-based keyword extraction for general questions" — this plan revisits that decision with a different mechanism than the one that was rejected: instead of a *separate* keyword-extraction LLM call before retrieval, expose the *existing*, already-guarded `keyword_search()` leg as a tool the Retrieval Agent (which is already an LLM reasoning over the question) can call itself, passing a short, specific phrase, whenever it judges vector search alone might miss an exact name/date/term. No new LLM call, no OR-of-words query, and the underlying DB guards (`phraseto_tsquery` phrase-adjacency + `LIMIT` + `statement_timeout`) apply exactly as they do today, so a badly-chosen phrase argument fails toward "few/no results," not a slow flood.

**Tech Stack:** Python (FastAPI/arq backend-core), Google ADK `Agent`/`ToolContext`, SQLAlchemy, Postgres full-text search (`phraseto_tsquery`, GIN index on `pages.text_search` — already exists, no migration needed), pytest + pytest-asyncio.

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)` (per `CLAUDE.md`).
- No hardcoded user-visible strings — this feature has no user-visible strings (agent-internal tool + prompt text only); skip `t()` unless a step below says otherwise.
- No raw SQL with unparameterized user input — not touched by this plan; `ChunksRepository.keyword_search()` already uses bound parameters and is reused as-is, unmodified.
- Every new/modified async DB call runs on the existing per-request `ctx.session` (`QueryContext.session`) — do not open a new session.
- Follow existing file conventions exactly: local (in-function) imports where the surrounding function already uses local imports (`vector_search`, `_run_search_chunks`); module-level imports where the surrounding module already uses module-level imports (`reranker.py`).
- This plan touches **only** `packages/backend-core/` — no new DB migration, no new frontend work, no new system-config seed (reuses the already-seeded `rag_keyword_top_k`).

---

### Task 1: `agent_keyword_search()` retrieval primitive

**Files:**
- Modify: `packages/backend-core/app/services/rag/retrieval.py:131` (insert after `exact_phrase_chunk_search`, before `async def vector_search`)
- Test: `packages/backend-core/tests/app/services/rag_retrieval_test.py`

**Interfaces:**
- Consumes: `ChunksRepository.keyword_search(phrase, book_ids, categories, limit) -> List[dict]` (existing, unmodified — `packages/backend-core/app/db/repositories/chunks_repository.py:231`); `SystemConfigsRepository.get_value(key, default) -> Optional[str]` (existing); `QueryContext.session`, `.character_categories` (existing fields).
- Produces: `agent_keyword_search(ctx: QueryContext, phrase: str, book_ids: Optional[List[str]]) -> List[dict]` — a list of dicts shaped like `keyword_search`'s return value (`book_id`, `page_number`, `page`, `text`, `title`, `volume`, `author`, `rank`). Consumed by Task 3's `_run_search_keyword_phrase`.

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/services/rag_retrieval_test.py` (near the existing `exact_phrase_chunk_search` tests):

```python
@pytest.mark.asyncio
async def test_agent_keyword_search_passes_config_limit_and_scope():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.character_categories = ["history"]

    captured = {}

    async def fake_get_value(self, key, default=None):
        assert key == "rag_keyword_top_k"
        return "7"

    async def fake_keyword_search(self, phrase, book_ids=None, categories=None, limit=10):
        captured["phrase"] = phrase
        captured["book_ids"] = book_ids
        captured["categories"] = categories
        captured["limit"] = limit
        return [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]

    with (
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
    ):
        result = await agent_keyword_search(ctx, "Yunus Khan", ["book-1"])

    assert captured == {
        "phrase": "Yunus Khan",
        "book_ids": ["book-1"],
        "categories": ["history"],
        "limit": 7,
    }
    assert result == [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]


@pytest.mark.asyncio
async def test_agent_keyword_search_falls_back_to_default_limit_on_bad_config():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.character_categories = []

    captured = {}

    async def fake_get_value(self, key, default=None):
        return "not-a-number"

    async def fake_keyword_search(self, phrase, book_ids=None, categories=None, limit=10):
        captured["limit"] = limit
        return []

    with (
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
    ):
        await agent_keyword_search(ctx, "term", None)

    assert captured["limit"] == 10


@pytest.mark.asyncio
async def test_agent_keyword_search_empty_phrase_returns_empty_without_querying():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()

    called = False

    async def fake_keyword_search(self, *a, **kw):
        nonlocal called
        called = True
        return []

    with patch.object(ChunksRepository, "keyword_search", fake_keyword_search):
        result = await agent_keyword_search(ctx, "   ", None)

    assert result == []
    assert called is False


@pytest.mark.asyncio
async def test_agent_keyword_search_empty_book_ids_list_returns_empty_without_querying():
    """Mirrors vector_search's convention: an explicit [] (not None) means
    discovery tools found no usable books — don't fall back to a global scan."""
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()

    called = False

    async def fake_keyword_search(self, *a, **kw):
        nonlocal called
        called = True
        return []

    with patch.object(ChunksRepository, "keyword_search", fake_keyword_search):
        result = await agent_keyword_search(ctx, "term", [])

    assert result == []
    assert called is False
```

Ensure the test file's header imports include `pytest`, `MagicMock`, `AsyncMock`, `patch` (it already does, per the existing `exact_phrase_chunk_search` tests in this file).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_retrieval_test.py -k agent_keyword_search -v`
Expected: FAIL with `ImportError: cannot import name 'agent_keyword_search'`

- [ ] **Step 3: Implement `agent_keyword_search`**

In `packages/backend-core/app/services/rag/retrieval.py`, insert immediately after `exact_phrase_chunk_search` ends (after line 131, before `async def vector_search`):

```python
# Fallback default when the rag_keyword_top_k system_config row is missing —
# mirrors _EXACT_PHRASE_DEFAULT_LIMIT in chat/orchestrator.py; kept as a
# separate constant since this module has no dependency on orchestrator.py.
_AGENT_KEYWORD_SEARCH_DEFAULT_LIMIT = 10


async def agent_keyword_search(
    ctx: "QueryContext",
    phrase: str,
    book_ids: Optional[List[str]],
) -> List[dict]:
    """Keyword-leg assist for the ADK retrieval agent's search_keyword_phrase
    tool (see agent/tools.py).

    Unlike exact_phrase_chunk_search (the pre-agent quoted-phrase gate in
    phrase_intent.py, which runs standalone with no vector fusion and never
    reaches the agent loop), this is called *by* the agent alongside
    search_chunks for ordinary questions — the agent decides, per question,
    whether a specific named term is worth a lexical-match check. Reuses the
    same ChunksRepository.keyword_search leg (phraseto_tsquery phrase match,
    same work_mem/statement_timeout guards) and the same rag_keyword_top_k
    cap as the quoted-phrase gate, so a misused (e.g. too-generic) phrase
    argument still can't flood or time out — see
    docs/feature/graph-rag-with-GDS/keyword-search-rework-plan.md.
    """
    phrase = phrase.strip()
    if not phrase:
        return []
    if book_ids is not None and not book_ids:
        return []

    from app.core.providers import get_vector_store
    from app.db.repositories.system_configs_repository import SystemConfigsRepository

    configs_repo = SystemConfigsRepository(ctx.session)
    rag_keyword_top_k_str = await configs_repo.get_value(
        "rag_keyword_top_k", str(_AGENT_KEYWORD_SEARCH_DEFAULT_LIMIT)
    )
    try:
        rag_keyword_top_k = int(rag_keyword_top_k_str)
    except ValueError:
        rag_keyword_top_k = _AGENT_KEYWORD_SEARCH_DEFAULT_LIMIT

    chunks_repo = get_vector_store(ctx.session)
    return await chunks_repo.keyword_search(
        phrase=phrase,
        book_ids=book_ids,
        categories=ctx.character_categories or None,
        limit=rag_keyword_top_k,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_retrieval_test.py -k agent_keyword_search -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/rag/retrieval.py packages/backend-core/tests/app/services/rag_retrieval_test.py
git commit -m "feat: add agent_keyword_search retrieval primitive for the agent-driven keyword tool"
```

---

### Task 2: Generalize context grading to accept a second chunk-shaped tool

`_grade_context` (context_grading.py) and `_pool_and_dedup` (reranker.py) both currently hard-filter on `obs.get("tool") == "search_chunks"`. Task 3's new tool must use a different `tool_name` (its own dispatch key — reusing `"search_chunks"` as the tag would make `_dispatch_tool_with_retry` mis-route its args into the vector-search implementation). Generalize the filter to a shared set instead of widening what "search_chunks" means.

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/config.py:12` (add constant after `MIN_CHUNKS_AFTER_GRADING`)
- Modify: `packages/backend-core/app/services/chat/context_grading.py:60-84` (`_grade_context`), `:196-207` (`_extract_used_book_ids`)
- Modify: `packages/backend-core/app/services/rag/agent/reranker.py:15-37` (`_pool_and_dedup`)
- Test: `packages/backend-core/tests/app/services/rag_service_utils_test.py`, `packages/backend-core/tests/app/services/rag_reranker_test.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `CHUNK_RESULT_TOOLS: frozenset[str]` in `app.services.rag.agent.config`, containing `{"search_chunks", "search_keyword_phrase"}`. Task 3 does not need to touch this again when it adds the tool — the name is declared here.

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/services/rag_service_utils_test.py` (near `test_grade_context_local_grading`):

```python
def test_grade_context_includes_search_keyword_phrase_observations():
    """A search_keyword_phrase-tagged observation must flow through grading
    like search_chunks — it's a second agent tool producing chunk-shaped
    results (Task 3), not a rename of search_chunks."""
    from app.services.chat.context_grading import _grade_context

    observations = [
        {
            "tool": "search_keyword_phrase",
            "result": {
                "ok": True,
                "data": {
                    "chunks": [
                        {
                            "book_id": "book_c",
                            "page": 30,
                            "text": "Exact phrase hit",
                            "rank": 0.4,
                            "title": "Book C",
                        }
                    ]
                },
            },
        }
    ]

    graded_context, before_count, after_count = _grade_context(observations)

    assert before_count == 1
    assert after_count == 1
    assert "Book C" in graded_context


def test_grade_context_ignores_unknown_tool_observations():
    from app.services.chat.context_grading import _grade_context

    observations = [
        {
            "tool": "get_book_author",
            "result": {"ok": True, "data": {"chunks": [{"book_id": "x", "page": 1, "text": "t"}]}},
        }
    ]

    graded_context, before_count, after_count = _grade_context(observations)

    assert before_count == 0
    assert after_count == 0
```

Add to `packages/backend-core/tests/app/services/rag_reranker_test.py` (near the top-level helpers, using the existing `_mock_llm` helper):

```python
@pytest.mark.asyncio
async def test_rerank_context_pools_search_keyword_phrase_observations():
    observations = [
        {
            "tool": "search_keyword_phrase",
            "result": {
                "ok": True,
                "data": {"chunks": [_chunk(book_id="b1", page=1, text="keyword hit", rank=0.3)]},
            },
        }
    ]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        graded_context, before_count, after_count = await rerank_context(
            "q", observations, model="gemini-test"
        )

    assert before_count == 1
    assert after_count == 1
    assert "keyword hit" in graded_context
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_service_utils_test.py -k search_keyword_phrase -v tests/app/services/rag_reranker_test.py -k search_keyword_phrase -v`
Expected: FAIL — the `search_keyword_phrase`-tagged observation is currently dropped (`before_count == 0`, not `1`), because `_grade_context`/`_pool_and_dedup` only match `tool == "search_chunks"`.

- [ ] **Step 3: Add the shared constant and use it in both grading paths**

In `packages/backend-core/app/services/rag/agent/config.py`, add after the `MIN_CHUNKS_AFTER_GRADING` line:

```python
# Tool names whose observations carry `{"chunks": [...]}` results and must be
# pooled/graded together — search_keyword_phrase is a second ADK tool (see
# agent/tools.py) that packages results in the same shape as search_chunks
# but is dispatched under its own tool_name (reusing "search_chunks" as the
# tag would misroute its args in _dispatch_tool_with_retry).
CHUNK_RESULT_TOOLS = frozenset({"search_chunks", "search_keyword_phrase"})
```

In `packages/backend-core/app/services/chat/context_grading.py`, update the local import inside `_grade_context` (currently `from app.services.rag.agent.config import (AGENT_MAX_CONTEXT_CHUNKS, GRADE_RELATIVE_THRESHOLD, MIN_CHUNKS_AFTER_GRADING)`):

```python
    from app.services.rag.agent.config import (
        AGENT_MAX_CONTEXT_CHUNKS,
        CHUNK_RESULT_TOOLS,
        GRADE_RELATIVE_THRESHOLD,
        MIN_CHUNKS_AFTER_GRADING,
    )
```

and change the filter line:

```python
    for obs in observations:
        if obs.get("tool") not in CHUNK_RESULT_TOOLS:
            continue
```

Then in `_extract_used_book_ids` in the same file, add the import at the top of the function and change its filter too:

```python
def _extract_used_book_ids(observations: list[dict]) -> list[str]:
    from app.services.rag.agent.config import CHUNK_RESULT_TOOLS

    # Collect book IDs from search_chunks / search_keyword_phrase results
    chunk_book_ids = set()
    for obs in observations:
        if obs.get("tool") in CHUNK_RESULT_TOOLS:
            res = obs.get("result", {})
            if res.get("ok", False):
                data = res.get("data") or res
                if isinstance(data, dict):
                    for chunk in data.get("chunks", []):
                        if chunk.get("book_id"):
                            chunk_book_ids.add(str(chunk["book_id"]))
```

In `packages/backend-core/app/services/rag/agent/reranker.py`, add `CHUNK_RESULT_TOOLS` to the existing module-level import:

```python
from app.services.rag.agent.config import (
    AGENT_MAX_CONTEXT_CHUNKS,
    CHUNK_RESULT_TOOLS,
    MIN_CHUNKS_AFTER_GRADING,
    RERANK_MAX_INPUT_CHUNKS,
)
```

and change `_pool_and_dedup`'s filter:

```python
    for obs in observations:
        if obs.get("tool") not in CHUNK_RESULT_TOOLS:
            continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_service_utils_test.py tests/app/services/rag_reranker_test.py tests/app/services/context_grading_test.py tests/app/services/rag_system_config_top_k_test.py -v`
Expected: PASS — including all pre-existing tests in these files (the change only widens the filter, `search_chunks` behavior is untouched).

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/config.py packages/backend-core/app/services/chat/context_grading.py packages/backend-core/app/services/rag/agent/reranker.py packages/backend-core/tests/app/services/rag_service_utils_test.py packages/backend-core/tests/app/services/rag_reranker_test.py
git commit -m "refactor: generalize context grading to pool a set of chunk-result tools, not just search_chunks"
```

---

### Task 3: `search_keyword_phrase` ADK tool

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/tools.py:19-24` (import), after `search_chunks` wrapper (~line 106), after `_run_search_chunks` (~line 646), and in `_dispatch_tool_with_retry` (~line 456)
- Modify: `packages/backend-core/app/services/chat/retrieval_agent.py:9-51` (import + `ALL_TOOLS`)
- Test: `packages/backend-core/tests/app/services/rag_agent_tools_test.py`

**Interfaces:**
- Consumes: `agent_keyword_search(ctx, phrase, book_ids) -> List[dict]` (Task 1); `_extract_book_ids(args) -> Optional[List[str]]` (existing, `tools.py:529`); `_execute_and_record_tool(tool_context, tool_name, tool_args) -> dict` (existing).
- Produces: ADK tool `search_keyword_phrase(phrase, book_ids=None, tool_context=None) -> dict`, registered in `ALL_TOOLS`; dispatch result shape `{"ok": True, "chunks": [...], "found_count": N}` (identical shape to `search_chunks`'s dispatch result, per `_dispatch_tool_with_retry:454-456`).

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/services/rag_agent_tools_test.py` (near `test_search_chunks_falls_back_to_current_book_in_reader_mode`):

```python
@pytest.mark.asyncio
async def test_run_search_keyword_phrase_scopes_to_current_book_in_reader_mode():
    from app.services.rag.agent.tools import _run_search_keyword_phrase

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book_id = "book-789"

    searched_book_ids = None

    async def fake_agent_keyword_search(ctx, phrase, book_ids):
        nonlocal searched_book_ids
        searched_book_ids = book_ids
        return [{"book_id": "book-789", "page_number": 3, "text": "hit", "rank": 0.5}]

    with patch(
        "app.services.rag.agent.tools.agent_keyword_search", fake_agent_keyword_search
    ):
        result = await _run_search_keyword_phrase({"phrase": "Yunus Khan"}, ctx)

    assert searched_book_ids == ["book-789"]
    assert len(result) == 1


@pytest.mark.asyncio
async def test_run_search_keyword_phrase_respects_explicit_book_ids():
    from app.services.rag.agent.tools import _run_search_keyword_phrase

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = True
    ctx.book_id = None

    searched_book_ids = "unset"

    async def fake_agent_keyword_search(ctx, phrase, book_ids):
        nonlocal searched_book_ids
        searched_book_ids = book_ids
        return []

    with patch(
        "app.services.rag.agent.tools.agent_keyword_search", fake_agent_keyword_search
    ):
        await _run_search_keyword_phrase(
            {"phrase": "term", "book_ids": ["book-1", "book-2"]}, ctx
        )

    assert searched_book_ids == ["book-1", "book-2"]


@pytest.mark.asyncio
async def test_dispatch_tool_search_keyword_phrase_returns_expected_shape():
    from app.services.rag.agent.tools import _dispatch_tool_with_retry

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = True
    ctx.book_id = None

    async def fake_agent_keyword_search(ctx, phrase, book_ids):
        return [{"book_id": "b1", "page_number": 1, "text": "hit", "rank": 0.9}]

    with patch(
        "app.services.rag.agent.tools.agent_keyword_search", fake_agent_keyword_search
    ):
        result = await _dispatch_tool_with_retry(
            "search_keyword_phrase", {"phrase": "term"}, ctx
        )

    assert result["ok"] is True
    assert result["found_count"] == 1
    assert result["chunks"][0]["text"] == "hit"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_agent_tools_test.py -k search_keyword_phrase -v`
Expected: FAIL with `ImportError: cannot import name '_run_search_keyword_phrase'`

- [ ] **Step 3: Implement the tool**

In `packages/backend-core/app/services/rag/agent/tools.py`, update the existing import block (lines 19-24):

```python
from app.services.rag.retrieval import (
    agent_keyword_search,
    embed_query,
    find_books_by_title_in_question,
    graph_entity_lookup,
    vector_search,
)
```

Add the public tool wrapper immediately after `search_chunks` (after line 106, before `search_books_by_summary`):

```python
async def search_keyword_phrase(
    phrase: str,
    book_ids: Optional[List[str]] = None,
    tool_context: ToolContext = None,
) -> dict:
    """Exact contiguous-phrase lexical search — a supplement to search_chunks, not a replacement.

    Call this IN ADDITION TO search_chunks (never instead of it) when the question names a
    specific, distinguishing term that vector similarity can blur or miss: a proper noun, an
    exact date, a rare technical/historical term, or a short quoted phrase. Pass a SHORT phrase
    (2-6 words) — the single most distinguishing term or phrase from the question, not the full
    question and not a common/generic word (e.g. not "king" or "book" alone). Do NOT call this
    for open-ended or broad questions with no single distinguishing term.

    Args:
        phrase: A short (2-6 word), specific phrase to match verbatim (word order and adjacency
                matter — this is not a bag-of-words search).
        book_ids: Optional list of book IDs to restrict the search scope, matching whatever
                  scope search_chunks used for this question.
    """
    args = {"phrase": phrase, "book_ids": book_ids}
    return await _execute_and_record_tool(tool_context, "search_keyword_phrase", args)
```

Add the dispatch branch in `_dispatch_tool_with_retry`, immediately after the existing `search_chunks` branch (after line 456):

```python
    if tool_name == "search_keyword_phrase":
        chunks = await _run_search_keyword_phrase(tool_args, ctx)
        return {"ok": True, "chunks": chunks, "found_count": len(chunks)}
```

Add the implementation immediately after `_run_search_chunks` ends (after line 646, before `_run_search_books_by_summary`):

```python
async def _run_search_keyword_phrase(args: dict, ctx: QueryContext) -> List[dict]:
    phrase = args.get("phrase") or ""
    book_ids = _extract_book_ids(args)
    if book_ids is None and not ctx.is_global and ctx.book_id:
        book_ids = [ctx.book_id]

    results = await agent_keyword_search(ctx, phrase, book_ids)

    log_json(
        logger,
        logging.INFO,
        "Agent tool search_keyword_phrase",
        phrase=phrase[:60],
        book_count=len(book_ids) if book_ids is not None else 0,
        results=len(results),
    )
    return results
```

In `packages/backend-core/app/services/chat/retrieval_agent.py`, add `search_keyword_phrase` to the import block (after `search_chunks`) and to `ALL_TOOLS` (after `search_chunks`):

```python
from app.services.rag.agent.tools import (
    search_chunks,
    search_keyword_phrase,
    search_books_by_summary,
    ...
)

ALL_TOOLS = [
    search_chunks,
    search_keyword_phrase,
    search_books_by_summary,
    ...
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd packages/backend-core && python -m pytest tests/app/services/rag_agent_tools_test.py -v`
Expected: PASS (all tests in the file, including the 3 new ones and every pre-existing test — confirms the new import/dispatch branch didn't break existing tool dispatch)

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/tools.py packages/backend-core/app/services/chat/retrieval_agent.py packages/backend-core/tests/app/services/rag_agent_tools_test.py
git commit -m "feat: register search_keyword_phrase as an ADK retrieval agent tool"
```

---

### Task 4: System-prompt guidance for when to call the new tool

Tool docstrings alone tell the LLM *what* the tool does; this codebase's established pattern (`AGENT_SYSTEM_PROMPT`) additionally tells it *when*, as part of the numbered retrieval strategy the agent follows. Without this, the agent may under- or over-call the new tool inconsistently.

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/prompts.py`
- Test: none (prompt text has no unit-testable behavior; verified via Task 5's dispatch-shape test and manual chat verification in the Verification section)

**Interfaces:**
- Consumes: nothing new.
- Produces: `AGENT_SYSTEM_PROMPT` (existing export) now includes the new step; no signature change.

- [ ] **Step 1: Add the new step constant**

In `packages/backend-core/app/services/rag/agent/prompts.py`, add a new constant after `_STEP_6_CONTENT` (before `_STEP_7_STOP`):

```python
_STEP_6B_KEYWORD_PHRASE = (
    "6b. Exact-term lexical assist: after (or alongside) a search_chunks call made in step 6 for "
    "a content question, also call search_keyword_phrase if the question names a specific, "
    "distinguishing term that vector similarity might miss or blur — a proper noun, an exact "
    "date, a rare technical/historical term, or a short quoted phrase. Pass a SHORT phrase "
    "(2-6 words), not the full question, using the same book_ids scope as the search_chunks call. "
    "Do NOT call search_keyword_phrase for broad or open-ended questions with no single "
    "distinguishing term, and do NOT call it as a substitute for search_chunks — always call "
    "search_chunks first."
)
```

- [ ] **Step 2: Wire it into `AGENT_SYSTEM_PROMPT` and extend the hard limits**

Update the `AGENT_SYSTEM_PROMPT` join list:

```python
AGENT_SYSTEM_PROMPT = "\n\n".join(
    [
        _ROLE,
        _STEP_1_COREFERENCE,
        _STEP_2_CURRENT_PAGE,
        _STEP_3_QURAN,
        _STEP_4_DICTIONARY,
        _STEP_5_CATALOG,
        _STEP_6_CONTENT,
        _STEP_6B_KEYWORD_PHRASE,
        _STEP_7_STOP,
        _STEP_8_MULTI_QUESTION,
        _HARD_LIMITS,
    ]
)
```

Append one line to `_HARD_LIMITS` (after the existing `search_chunks` CRITICAL lines, before the `"When done retrieving..."` line):

```python
    "CRITICAL: search_keyword_phrase's phrase argument must be a short 2-6 word term, never the "
    "full question and never a single generic/common word.\n"
```

- [ ] **Step 3: Verify the prompt still imports and builds**

Run: `cd packages/backend-core && python -c "from app.services.rag.agent.prompts import AGENT_SYSTEM_PROMPT; assert 'search_keyword_phrase' in AGENT_SYSTEM_PROMPT; print('ok')"`
Expected: prints `ok`

- [ ] **Step 4: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/prompts.py
git commit -m "docs: add retrieval-agent guidance for when to call search_keyword_phrase"
```

---

## Verification (manual, before merging)

Automated tests cover wiring and grading; they cannot verify the LLM actually calls the new tool sensibly. Before merging:

1. Rebuild the backend: `./deploy/local/rebuild-and-restart.sh backend`
2. In the chat UI (http://localhost:30080), ask a handful of **non-quoted** content questions that name a specific, distinguishing term likely to be sparse in embedding space (an exact date, an obscure historical figure's full name, a rare technical term) and confirm via backend logs (`log_json` output for `"Agent tool search_keyword_phrase"`) that the agent calls the new tool with a short, sensible phrase — not the full question, not a generic word.
3. Ask a handful of broad/open-ended questions ("what is this book about", "tell me about the Silk Road") and confirm the agent does **not** call `search_keyword_phrase` for them (per the docstring/prompt guidance) — i.e. it isn't over-firing.
4. Confirm a `search_keyword_phrase` call with a rare-but-real term returns results that get folded into the answer (spot-check the streamed answer mentions the specific fact only the keyword hit would have surfaced, not just what vector search alone found).
5. Confirm quoted-phrase questions (`"exact text"`) still route through the **existing** deterministic `phrase_intent.py` gate unchanged — this plan does not touch that path, but the shared `keyword_search()`/`rag_keyword_top_k` reuse means it's worth a quick regression check.

If step 2/3 shows the agent mis-firing in either direction, tighten `_STEP_6B_KEYWORD_PHRASE`'s wording (this is a prompt-tuning iteration, not a code change) before merging.

## Self-Review Notes

- **Spec coverage:** the discussed goal — "detect a salient keyword from a general question, run keyword search alongside vector search, without repeating the OR-of-all-words flood" — is covered by Task 3's docstring/dispatch (agent decides the phrase) and Task 1's reuse of the already-guarded `phraseto_tsquery`/`work_mem`/`statement_timeout` leg (no flood risk, since it's still a contiguous-phrase match, not OR-of-words).
- **No feature flag added deliberately:** mirrors the resolved-decision precedent already in `keyword-search-rework-plan.md` ("no replacement kill-switch flag was added, per the plan's default"). The failure mode of a misused `phrase` argument here is "empty/few results" (phrase-adjacency match), not the old flood bug, so the existing DB-level guards are the safety net, not an app-level toggle. If production telemetry later shows the agent overusing or misusing the tool, a `rag_agent_keyword_search_enabled` config (checked in `_run_search_keyword_phrase`, short-circuiting to `[]`) is a small, isolated follow-up — intentionally deferred rather than speculatively built now.
- **No migration:** `pages.text_search` (GIN-indexed) and `ChunksRepository.keyword_search()` already exist and are reused unmodified — this plan is purely an application-layer addition (a second consumer of an existing, already-hardened leg).
