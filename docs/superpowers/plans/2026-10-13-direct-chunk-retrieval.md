# Direct Chunk Retrieval (Summary-Narrowing Off) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the chat retrieval agent search book chunks across the whole library directly, without first narrowing to ~30 books by summary similarity. Ship it behind a `system_configs` flag so both modes can be compared on production data. Include optional fixes that improve semantic and keyword recall in either mode.

**Architecture:** A new `rag_summary_narrowing_enabled` system config is read once per request in `ChatOrchestrator` and stored on `QueryContext`. It selects one of two retrieval-agent system prompts (`build_agent_system_prompt(summary_narrowing=...)`) and decides whether the `search_books_by_summary` tool is exposed. `_run_search_chunks`'s context-switch fallback broadens to the whole library instead of re-discovering books via summaries. Independent fixes (Tasks 4–6) touch `ChunksRepository` and the reranker only.

**Tech Stack:** Python 3 / FastAPI backend-core, google-adk `Agent`, PostgreSQL + pgvector 0.8.x (HNSW on `halfvec(3072)`), Postgres FTS (`tsvector` 'simple'), pytest + pytest-asyncio.

## Background (why)

Findings from the 2026-10-13 retrieval review:

1. **Summary narrowing loses books that only mention a topic briefly.** `search_books_by_summary` (`summary_threshold=0.30`, `limit=30`) effectively always returns the top 30 of ~633 books, ranked by how similar the whole book's summary is to the question. A book that covers the topic on 2 pages ranks low and is never searched. Prompt step 6g sends every general content question through this path, and `_HARD_LIMITS` forbids searching the whole library first.
2. **The per-book quota then pads results with weak passages.** With 30 book IDs, `vector_search` gives each book `max(25 // 30, 3) = 3` slots (`retrieval.py:287`). That's up to 90 chunks, and weak books are guaranteed slots.
3. **It isn't the fast path either.** Scoped search uses `c.embedding` without the `halfvec` cast, so the HNSW index is not used. It runs one exact scan per book (30 in parallel). Library-wide search uses the HNSW index.
4. **Library-wide search is capped at 40 candidates.** `hnsw.ef_search` is at the pgvector default of 40, while the query asks for `inner_limit = limit * 3 = 75`. The table-of-contents, threshold and character-category filters run *after* that cap. (Task 4)
5. **The reranker drops keyword hits.** `search_keyword_phrase` hits carry `rank`, not `score`. When there are more than 50 candidates, `rerank_context` sorts by `score` and truncates, so keyword hits land last and are dropped. (Task 5)
6. **Keyword search misses inflected forms.** `phraseto_tsquery('simple', ...)` matches whole tokens only, so `ھوزۇرۇم` does not match `ھوزۇرۇمنى` or `ھوزۇرۇمدا`. (Task 6)

## Scope: required vs optional

| Task | What | Required for the experiment? |
|------|------|------|
| 1 | Config flag + `QueryContext` field + orchestrator wiring | **Required** |
| 2 | Prompt variant + tool-list filtering | **Required** |
| 3 | Context-switch fallback goes whole-library | **Required** |
| 4 | HNSW `ef_search` fix (+ iterative scan) | Strongly recommended: direct mode relies on library-wide search |
| 5 | Reranker keeps keyword hits | Optional, independent bug fix |
| 6 | Keyword prefix (suffix-tolerant) matching | Optional, independent |
| 7 | Docs + skill sync | Required if any of 1–6 ship |
| 8 | A/B evaluation on production data | **Required** to decide the default |

**Explicitly out of scope:**
- **Hybrid vector+keyword fusion (RRF) inside `search_chunks`.** It was deliberately removed in the keyword-search rework (`docs/feature/graph-rag-with-GDS/keyword-search-rework-plan.md`; see the docstring of `tests/app/services/rag_retrieval_test.py`). Revisit only after Task 8 results, with that plan's rationale re-read first.
- **Normalizing keyword queries with `normalize_uyghur`.** It maps `ې`/`ي` → `ى`, but `pages.text_search` indexes the raw, un-normalized text, so a normalized query would *miss* pages written with `ې`. A fix needs an index rebuild and is not worth it now.
- **Query/document embedding task prefixes** (would need a corpus re-embed — see memory: no bulk re-chunk).
- Deleting `search_books_by_summary` / `book_summaries` (decide after Task 8).

## Global Constraints

- No `print()` — use `log_json(logger, level, "message", key=value)`.
- No `os.environ.get()` in application code — use `settings.*` / `SystemConfigsRepository.get_value`.
- No raw SQL with user input — always SQLAlchemy bound parameters. (`SET LOCAL` values must be validated `int`s built in code, never user input.)
- Migration file first, then code that reads it.
- Prompt text edits: invoke the `/prompt-engineer` skill before editing `services/rag/agent/prompts.py`.
- Missing config row must preserve **current** behavior (`rag_summary_narrowing_enabled` default `"true"` in code); the migration seeds `"false"` to turn the experiment on.
- Run tests from repo root: `pytest packages/backend-core/tests/<path> -v` (pytest.ini at repo root, `asyncio_mode = auto`).
- Never auto-translate user-facing Uyghur text; prompt instructions stay in English with Uyghur only as quoted examples already present.

## File Structure

| File | Change |
|------|--------|
| `packages/backend-core/migrations/098_seed_rag_summary_narrowing_config.sql` | Create — seeds flag `false` |
| `packages/backend-core/migrations/098_rollback_seed_rag_summary_narrowing_config.sql` | Create |
| `packages/backend-core/app/db/seeds.py` | Modify — add seed entry next to `rag_vector_top_k` |
| `packages/backend-core/app/services/rag/context.py` | Modify — add `summary_narrowing_enabled: bool = True` |
| `packages/backend-core/app/services/rag/agent/prompts.py` | Modify — `build_agent_system_prompt(summary_narrowing: bool)` |
| `packages/backend-core/app/services/chat/retrieval_agent.py` | Modify — `summary_narrowing_enabled` param; filter tools |
| `packages/backend-core/app/services/rag/agent/tools.py` | Modify — `search_chunks` docstring; context-switch fallback |
| `packages/backend-core/app/services/chat/orchestrator.py` | Modify — read flag, set on ctx, pass to builder, log it |
| `packages/backend-core/app/db/repositories/chunks_repository.py` | Modify — ef_search (Task 4), prefix tsquery (Task 6) |
| `packages/backend-core/app/services/rag/retrieval.py` | Modify — `agent_keyword_search` passes `prefix_match=True` (Task 6) |
| `packages/backend-core/app/services/rag/agent/reranker.py` | Modify — keep keyword hits in truncation (Task 5) |
| `docs/main/CHAT_RAG_DESIGN.md`, `docs/main/SUMMARY_DESIGN.md`, `.claude/skills/prompt-engineer/SKILL.md` | Modify (Task 7) |
| Tests under `packages/backend-core/tests/app/...` | Modify/extend as listed per task |

---

### Task 1: Config flag, `QueryContext` field, orchestrator wiring

**Files:**
- Create: `packages/backend-core/migrations/098_seed_rag_summary_narrowing_config.sql`
- Create: `packages/backend-core/migrations/098_rollback_seed_rag_summary_narrowing_config.sql`
- Modify: `packages/backend-core/app/db/seeds.py` (after the `rag_graph_top_k` entry, ~line 258)
- Modify: `packages/backend-core/app/services/rag/context.py` (after `use_deterministic_router`, ~line 93)
- Modify: `packages/backend-core/app/services/chat/orchestrator.py` (~lines 245–280 and ~line 462)
- Test: `packages/backend-core/tests/app/services/test_adk_orchestrator.py`

**Interfaces:**
- Produces: `QueryContext.summary_narrowing_enabled: bool` (default `True`); orchestrator calls `build_retrieval_agent(model=..., intent_signals=..., summary_narrowing_enabled=ctx.summary_narrowing_enabled)` (param added in Task 2; land Tasks 1+2 in one commit if executing strictly in order, or add the kwarg in Task 2 and the orchestrator pass-through there — see Task 2 Step 6).
- Produces: module helper `_parse_bool_config(value: Optional[str], default: bool) -> bool` in `orchestrator.py`.

- [ ] **Step 1: Write the migration**

`packages/backend-core/migrations/098_seed_rag_summary_narrowing_config.sql`:

```sql
-- Migration: 098_seed_rag_summary_narrowing_config.sql
-- Description: Seed rag_summary_narrowing_enabled system configuration key.
--   'false' = retrieval agent searches chunks across the whole library directly
--   (no search_books_by_summary pre-narrowing). Missing row = 'true' in code
--   (legacy behavior), so rollback restores the old pipeline.
-- Author: Kitabim.AI
-- Date: 2026-10-13

BEGIN;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'rag_summary_narrowing_enabled',
    'false',
    'When true, the chat retrieval agent first narrows content questions to ~30 books by book-summary similarity (search_books_by_summary) before chunk search. When false, it searches chunks across the whole library directly. get_book_summary for "what is this book about" questions is unaffected.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

COMMIT;
```

`packages/backend-core/migrations/098_rollback_seed_rag_summary_narrowing_config.sql`:

```sql
-- Rollback Migration: 098_rollback_seed_rag_summary_narrowing_config.sql
-- Description: Rollback migration 098 by removing rag_summary_narrowing_enabled config
-- Author: Kitabim.AI
-- Date: 2026-10-13

BEGIN;

DELETE FROM system_configs WHERE key = 'rag_summary_narrowing_enabled';

COMMIT;
```

- [ ] **Step 2: Add the seed entry** in `app/db/seeds.py`, directly after the `rag_graph_top_k` dict:

```python
        {
            "key": "rag_summary_narrowing_enabled",
            "value": "false",
            "description": "When true, the chat retrieval agent first narrows content questions to ~30 books by book-summary similarity (search_books_by_summary) before chunk search. When false, it searches chunks across the whole library directly. get_book_summary for \"what is this book about\" questions is unaffected.",
        },
```

- [ ] **Step 3: Add the `QueryContext` field** in `app/services/rag/context.py`, after `use_deterministic_router: bool = False`:

```python
    # rag_summary_narrowing_enabled system_config — False means the retrieval
    # agent searches chunks library-wide instead of pre-narrowing to books via
    # search_books_by_summary. Default True = legacy behavior when unset.
    summary_narrowing_enabled: bool = True
```

- [ ] **Step 4: Write the failing test** — append to `tests/app/services/test_adk_orchestrator.py`:

```python
from app.services.chat.orchestrator import _parse_bool_config


def test_parse_bool_config_defaults_and_values():
    assert _parse_bool_config(None, default=True) is True
    assert _parse_bool_config("", default=True) is True
    assert _parse_bool_config("false", default=True) is False
    assert _parse_bool_config(" FALSE ", default=True) is False
    assert _parse_bool_config("true", default=False) is True
    assert _parse_bool_config("garbage", default=True) is True
```

- [ ] **Step 5: Run it to verify it fails**

Run: `pytest packages/backend-core/tests/app/services/test_adk_orchestrator.py::test_parse_bool_config_defaults_and_values -v`
Expected: FAIL — `ImportError: cannot import name '_parse_bool_config'`

- [ ] **Step 6: Implement** — in `orchestrator.py`, add near the other module-level helpers (after `_extract_effective_question`):

```python
def _parse_bool_config(value: Optional[str], default: bool) -> bool:
    """Parse a 'true'/'false' system_config value; anything else → default."""
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    return default
```

Then, right after `set_current_query_context(ctx)` (~line 280):

```python
        ctx.summary_narrowing_enabled = _parse_bool_config(
            await configs_repo.get_value("rag_summary_narrowing_enabled", "true"),
            default=True,
        )
```

- [ ] **Step 7: Run tests**

Run: `pytest packages/backend-core/tests/app/services/test_adk_orchestrator.py -v`
Expected: all PASS

- [ ] **Step 8: Apply the migration locally** (standalone host Postgres):

```bash
export $(grep ^DATABASE_URL .env | xargs)
psql "$DATABASE_URL" -f packages/backend-core/migrations/098_seed_rag_summary_narrowing_config.sql
psql "$DATABASE_URL" -tc "select value from system_configs where key='rag_summary_narrowing_enabled';"
```
Expected: ` false`

- [ ] **Step 9: Commit**

```bash
git add packages/backend-core/migrations/098_*.sql packages/backend-core/app/db/seeds.py \
  packages/backend-core/app/services/rag/context.py packages/backend-core/app/services/chat/orchestrator.py \
  packages/backend-core/tests/app/services/test_adk_orchestrator.py
git commit -m "feat(rag): add rag_summary_narrowing_enabled config flag"
```

---

### Task 2: Prompt variant and tool filtering for direct mode

**Invoke `/prompt-engineer` before editing `prompts.py`.**

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/prompts.py`
- Modify: `packages/backend-core/app/services/chat/retrieval_agent.py`
- Modify: `packages/backend-core/app/services/rag/agent/tools.py:92-107` (`search_chunks` docstring)
- Modify: `packages/backend-core/app/services/chat/orchestrator.py` (~line 462, `build_retrieval_agent(...)` call)
- Test: `packages/backend-core/tests/app/services/test_adk_orchestrator.py`

**Interfaces:**
- Consumes: `QueryContext.summary_narrowing_enabled` (Task 1).
- Produces: `build_agent_system_prompt(summary_narrowing: bool = True) -> str`; `AGENT_SYSTEM_PROMPT` stays exported and equals `build_agent_system_prompt(True)`.
- Produces: `build_retrieval_agent(model: str, intent_signals: Optional[dict] = None, summary_narrowing_enabled: bool = True) -> Agent`.

- [ ] **Step 1: Write the failing tests** — append to `tests/app/services/test_adk_orchestrator.py`:

```python
from app.services.rag.agent.prompts import (
    AGENT_SYSTEM_PROMPT,
    build_agent_system_prompt,
)


def test_legacy_prompt_unchanged_when_summary_narrowing_enabled():
    assert build_agent_system_prompt(summary_narrowing=True) == AGENT_SYSTEM_PROMPT
    assert "search_books_by_summary" in AGENT_SYSTEM_PROMPT


def test_direct_prompt_never_mentions_summary_narrowing():
    prompt = build_agent_system_prompt(summary_narrowing=False)
    assert "search_books_by_summary" not in prompt
    # Library-wide search must be the stated default, and the legacy ban removed.
    assert "whole library" in prompt
    assert "Do NOT call search_chunks with an empty book_ids list as your first action" not in prompt
    # "What is this book about" still uses get_book_summary.
    assert "get_book_summary" in prompt


def test_build_retrieval_agent_direct_mode_drops_summary_search_tool():
    agent = build_retrieval_agent(
        model="gemini-3.5-flash-lite", summary_narrowing_enabled=False
    )
    tool_names = {tool.__name__ for tool in agent.tools}
    assert "search_books_by_summary" not in tool_names
    assert {"search_chunks", "search_keyword_phrase", "get_book_summary"} <= tool_names
    assert "search_books_by_summary" not in agent.instruction


def test_build_retrieval_agent_default_keeps_summary_search_tool():
    agent = build_retrieval_agent(model="gemini-3.5-flash-lite")
    assert "search_books_by_summary" in {tool.__name__ for tool in agent.tools}
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest packages/backend-core/tests/app/services/test_adk_orchestrator.py -v -k "prompt or direct_mode or default_keeps"`
Expected: FAIL — `ImportError: cannot import name 'build_agent_system_prompt'`

- [ ] **Step 3: Implement the prompt variant** in `prompts.py`. Keep every existing `_STEP_*` constant byte-for-byte (they are the legacy prompt). Add direct-mode constants and the builder at the bottom, replacing the current `AGENT_SYSTEM_PROMPT = "\n\n".join([...])` block:

```python
# ── Direct-chunk mode (rag_summary_narrowing_enabled = false) ────────────────
# Same routing as above except: no search_books_by_summary pre-narrowing.
# Content questions that name no book/author/current book search chunks across
# the whole library directly; vector ranking picks the books.

_STEP_5_CATALOG_DIRECT = (
    "5. For catalog or metadata questions (who wrote X, what books does Y author have, "
    "what is available in the library):\n"
    '   - "who wrote [title]?" or any authorship/ownership question about a book title → call get_book_author.\n'
    "   - This includes Uyghur genitive patterns like '[title] كىمنىڭ؟' (whose is [title]?), "
    "'[title] كىمگە تەئەللۇق؟', '[title]نىڭ ئاپتورى كىم؟', or any sentence where a known book title "
    "is followed by كىمنىڭ, كىمكى, ئاپتورى, or similar ownership/authorship markers. "
    "IMPORTANT: Do NOT call find_books_by_title for these — call get_book_author directly.\n"
    '   - "what did [author] write?" → call get_books_by_author\n'
    "   - general library browsing or listing → call search_catalog\n"
    "   - If the strict catalog call above (get_book_author, get_books_by_author, or search_catalog) "
    "returns no results, call search_chunks with no book_ids (searching the whole library) using the "
    "book title/author text — do NOT stop with an empty result."
)

_STEP_6_CONTENT_DIRECT = (
    "6. For content questions (what does the book say about X, explain Y, summarize Z, which book is character W in):\n"
    "   - Note on Character identity questions: If the question asks who or what a character/person/entity is "
    "(e.g. 'X كىم؟', 'tell me about X') and step 4 did not already answer it, call search_chunks with the entity "
    "name and no book_ids (searching the whole library), then call search_keyword_phrase with the entity name. "
    "Do NOT call get_book_summary for these — book summaries rarely describe individual people.\n"
    "   a. If the question asks for the plot, themes, or main characters of a specific book → call find_books_by_title, then "
    "call get_book_summary with the resulting book IDs. Do NOT call search_chunks for these questions.\n"
    "   b. If the question explicitly names a book title and asks for specific passages or details → call find_books_by_title "
    "to get the book IDs, then call search_chunks with those book IDs for supporting passages.\n"
    "   c. If the question explicitly names an author → call get_books_by_author, extract "
    "the book IDs from the result, and call search_chunks with those book IDs.\n"
    "   d. If no title/author is explicitly named, but [Context] provides a current book_id:\n"
    "      - If the question asks for the plot, themes, summary, or main content of the current book (e.g. 'بۇ كىتاب نېمە توغرىسىدا؟', 'بۇ كىتابنىڭ ئاساسى مەزمۇنى نېمە؟', 'this book summary') → call get_book_summary with [current_book_id] directly. Skip book discovery tools entirely.\n"
    "      - If the question asks about a DIFFERENT volume of the current book (e.g. mentions 'next volume', "
    "'previous volume', a numbered volume like '2-توم', 'كەيىنكى توم', 'ئالدىنقى توم', 'ئىككىنچى توم'), "
    "call get_sister_volumes with the current book_id. Then call search_chunks with the relevant sister "
    "volume's book_id (determine which volume from the question and the series list returned).\n"
    "      - Otherwise, call search_chunks with the current book_id directly — skip book discovery entirely.\n"
    "   - Note on stale context: when [Context] lists 'Previous response books' with titles, judge for yourself "
    "whether those titles plausibly relate to this question's topic before reusing them in step e below. "
    "If they clearly do not, skip straight to step f.\n"
    "   e. If no title/author is explicitly named, [Context] provides previous response book IDs, AND no current book_id is provided in [Context]:\n"
    "      - If the question asks about a DIFFERENT volume of those books (mentions next/previous/numbered volume), "
    "call get_sister_volumes with the first context book_id to discover the full series, then call search_chunks "
    "with the relevant sister volume's book_id.\n"
    "      - Otherwise, call search_chunks with those book_ids first — they may be relevant if the topic has not changed. "
    "If fewer than 4 results are returned, the topic may have changed — proceed to step f.\n"
    "   f. In all other cases (general topics, people, events, no prior context), call search_chunks with no book_ids "
    "to search the whole library. Do NOT try to pre-select books — vector ranking across all books already surfaces "
    "the books that contain the most relevant passages.\n"
    "   g. [Only applies to search_chunks calls. If you just called get_book_summary, or if any previous search_chunks call for this topic/sub-question has already returned 25 or more results, STOP immediately — the context is already full, do NOT retry or call search_chunks again.] "
    "If search_chunks returns fewer than 4 results, retry once with a rephrased query (still with no book_ids)."
)

_STEP_8_MULTI_QUESTION_DIRECT = (
    "8. If the question contains a [Sub-questions] section listing multiple numbered questions, "
    "you MUST retrieve evidence for ALL of them before finishing. "
    "Use separate tool calls for each sub-question if their topics differ. "
    "Do not stop after finding evidence for only the first sub-question. "
    "IMPORTANT: When a sub-question names a different book than one already retrieved, "
    "call find_books_by_title fresh for that sub-question; when it names no book, "
    "call search_chunks with no book_ids for it — do NOT reuse book IDs that appeared in a "
    "previous tool result from this same turn."
)

_HARD_LIMITS_DIRECT = (
    "Hard limits: at most 6 tool calls total (for turns with [Sub-questions], the limit is raised to 10 tool calls total). Do not repeat the same query or phrase twice — this includes retrying a search, phrase, or dictionary term under an alternate spelling; treat the first result (including a zero-result miss) as final.\n"
    "Searching the whole library (search_chunks with no book_ids) is the default for content questions that "
    "name no book, no author, and have no current book_id or relevant previous response books.\n"
    "CRITICAL: Do NOT call search_chunks again for the same topic or sub-question if a previous search_chunks call for that topic already returned 25 or more results — "
    "the context is already full and a rephrased or broadened retry adds no value.\n"
    "When done retrieving, respond with no tool calls to signal completion."
)


def build_agent_system_prompt(summary_narrowing: bool = True) -> str:
    """Retrieval-agent system prompt.

    summary_narrowing=True is the legacy prompt (search_books_by_summary
    pre-narrows content questions to ~30 books). False routes unscoped
    content questions straight to library-wide search_chunks — see
    rag_summary_narrowing_enabled.
    """
    if summary_narrowing:
        parts = [
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
    else:
        parts = [
            _ROLE,
            _STEP_1_COREFERENCE,
            _STEP_2_CURRENT_PAGE,
            _STEP_3_QURAN,
            _STEP_4_DICTIONARY,
            _STEP_5_CATALOG_DIRECT,
            _STEP_6_CONTENT_DIRECT,
            _STEP_6B_KEYWORD_PHRASE,
            _STEP_7_STOP,
            _STEP_8_MULTI_QUESTION_DIRECT,
            _HARD_LIMITS_DIRECT,
        ]
    return "\n\n".join(parts)


AGENT_SYSTEM_PROMPT = build_agent_system_prompt(summary_narrowing=True)
```

Note: `_STEP_6B_KEYWORD_PHRASE` is shared and contains `'summarize Y'` (not `search_books_by_summary`) — the "not in prompt" test asserts only the tool name, so it passes.

- [ ] **Step 4: Implement tool filtering** in `retrieval_agent.py`. Change the import and the builder:

```python
from app.services.rag.agent.prompts import build_agent_system_prompt
```

```python
def build_retrieval_agent(
    model: str,
    intent_signals: Optional[dict] = None,
    summary_narrowing_enabled: bool = True,
) -> Agent:
    """Build the Retrieval Agent focused exclusively on tool execution and context gathering.

    summary_narrowing_enabled=False (rag_summary_narrowing_enabled) drops the
    search_books_by_summary tool and uses the direct-chunk prompt variant.
    """
    instructions = build_agent_system_prompt(summary_narrowing=summary_narrowing_enabled)
```

…keep the existing `intent_signals` hint block unchanged, then:

```python
    tools = (
        ALL_TOOLS
        if summary_narrowing_enabled
        else [t for t in ALL_TOOLS if t is not search_books_by_summary]
    )

    agent = Agent(
        model=model,
        name="KitabimRetrievalAgent",
        description="Retrieves evidence from books, Quran, catalog, and dictionaries.",
        instruction=instructions,
        tools=tools,
    )
    return agent
```

- [ ] **Step 5: Neutralize the `search_chunks` docstring** (ADK sends it to the LLM as the tool description; the current "Always try to restrict scope first" contradicts direct mode). In `tools.py`, replace the `book_ids` arg doc:

```python
    """Vector-search book chunks for passages relevant to a query.

    Args:
        query: The search query to embed and match against book passages.
        book_ids: Optional list of book IDs to restrict the search scope.
                  Follow the system instructions for when to pass book_ids and
                  when to omit them to search the whole library.
    """
```

- [ ] **Step 6: Wire the orchestrator** — at the `build_retrieval_agent(` call (~line 462):

```python
                retrieval_agent = build_retrieval_agent(
                    model=agent_model,
                    intent_signals=signals,
                    summary_narrowing_enabled=ctx.summary_narrowing_enabled,
                )
```

and add a log line just before it:

```python
                log_json(
                    logger,
                    logging.INFO,
                    "Retrieval agent mode",
                    summary_narrowing=ctx.summary_narrowing_enabled,
                )
```

- [ ] **Step 7: Run tests**

Run: `pytest packages/backend-core/tests/app/services/test_adk_orchestrator.py packages/backend-core/tests/app/services/rag_agent_tools_test.py -v`
Expected: all PASS

- [ ] **Step 8: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/prompts.py \
  packages/backend-core/app/services/chat/retrieval_agent.py \
  packages/backend-core/app/services/rag/agent/tools.py \
  packages/backend-core/app/services/chat/orchestrator.py \
  packages/backend-core/tests/app/services/test_adk_orchestrator.py
git commit -m "feat(rag): direct-chunk retrieval prompt variant behind summary-narrowing flag"
```

---

### Task 3: Context-switch fallback searches the whole library in direct mode

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/tools.py:578-640` (`_run_search_chunks`)
- Test: `packages/backend-core/tests/app/services/rag_agent_tools_test.py`

**Interfaces:**
- Consumes: `QueryContext.summary_narrowing_enabled` (Task 1).

- [ ] **Step 1: Write the failing tests** — append to `rag_agent_tools_test.py`:

```python
from app.services.rag.agent import tools as agent_tools


def _ctx_for_context_switch(summary_narrowing_enabled: bool):
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = True
    ctx.book_id = None
    ctx.context_book_ids = ["old-book"]
    ctx.summary_narrowing_enabled = summary_narrowing_enabled
    return ctx


@pytest.mark.asyncio
async def test_context_switch_direct_mode_broadens_to_whole_library():
    ctx = _ctx_for_context_switch(summary_narrowing_enabled=False)
    calls = []

    async def fake_vector_search(ctx_, book_ids, query_vector=None):
        calls.append(book_ids)
        if book_ids == ["old-book"]:
            return [{"book_id": "old-book", "page_number": 1, "chunk_index": 0, "score": 0.30}]
        return [{"book_id": "new-book", "page_number": 9, "chunk_index": 0, "score": 0.80}]

    summary_mock = AsyncMock(return_value=["should-not-be-used"])
    with (
        patch.object(agent_tools, "embed_query", AsyncMock(return_value=[0.1])),
        patch.object(agent_tools, "vector_search", fake_vector_search),
        patch.object(agent_tools, "graph_entity_lookup", AsyncMock(return_value=[])),
        patch.object(agent_tools, "_run_search_books_by_summary", summary_mock),
    ):
        results = await agent_tools._run_search_chunks(
            {"query": "q", "book_ids": ["old-book"]}, ctx
        )

    summary_mock.assert_not_awaited()
    assert calls == [["old-book"], None]
    assert {r["book_id"] for r in results} == {"old-book", "new-book"}


@pytest.mark.asyncio
async def test_context_switch_legacy_mode_still_uses_summary_rediscovery():
    ctx = _ctx_for_context_switch(summary_narrowing_enabled=True)
    calls = []

    async def fake_vector_search(ctx_, book_ids, query_vector=None):
        calls.append(book_ids)
        return [{"book_id": "old-book", "page_number": 1, "chunk_index": 0, "score": 0.30}]

    summary_mock = AsyncMock(return_value=["summary-book"])
    with (
        patch.object(agent_tools, "embed_query", AsyncMock(return_value=[0.1])),
        patch.object(agent_tools, "vector_search", fake_vector_search),
        patch.object(agent_tools, "graph_entity_lookup", AsyncMock(return_value=[])),
        patch.object(agent_tools, "_run_search_books_by_summary", summary_mock),
    ):
        await agent_tools._run_search_chunks({"query": "q", "book_ids": ["old-book"]}, ctx)

    summary_mock.assert_awaited_once()
    assert calls == [["old-book"], ["summary-book"]]
```

Before writing these, confirm `embed_query`, `vector_search`, and `graph_entity_lookup` are imported at module level in `tools.py` (`grep -n "^from app.services.rag.retrieval import" -A8 packages/backend-core/app/services/rag/agent/tools.py`). If any is imported inside the function instead, patch it at `app.services.rag.retrieval.<name>`.

Also, the graph lookup reads `rag_graph_top_k` via `SystemConfigsRepository(ctx.session).get_value` — with `ctx.session = AsyncMock()` it returns an `AsyncMock` coroutine result; if that breaks, add `patch.object(SystemConfigsRepository, "get_value", AsyncMock(return_value="10"))`.

- [ ] **Step 2: Run to verify failure**

Run: `pytest packages/backend-core/tests/app/services/rag_agent_tools_test.py -v -k context_switch`
Expected: `test_context_switch_direct_mode_broadens_to_whole_library` FAILS (summary mock awaited); legacy test PASSES.

- [ ] **Step 3: Implement** — in `_run_search_chunks`, replace the body of the `if top_score < CONTEXT_SWITCH_SCORE_THRESHOLD:` block's rediscovery step:

```python
        if top_score < CONTEXT_SWITCH_SCORE_THRESHOLD:
            direct_mode = not getattr(ctx, "summary_narrowing_enabled", True)
            log_json(
                logger,
                logging.INFO,
                "Context switch detected — broadening search",
                top_score=round(top_score, 3),
                threshold=CONTEXT_SWITCH_SCORE_THRESHOLD,
                via="whole_library" if direct_mode else "summaries",
            )
            if direct_mode:
                new_book_ids = None
                broader = await vector_search(ctx, None, query_vector=query_vector)
            else:
                new_book_ids = await _run_search_books_by_summary({"query": query}, ctx)
                broader = (
                    await vector_search(ctx, new_book_ids, query_vector=query_vector)
                    if new_book_ids
                    else []
                )
            if broader:
                existing_keys = {
                    (r.get("book_id"), r.get("page_number"), r.get("chunk_index"))
                    for r in results
                }
                new_chunks = [
                    c
                    for c in broader
                    if (
                        c.get("book_id"),
                        c.get("page_number"),
                        c.get("chunk_index"),
                    )
                    not in existing_keys
                ]
                results = results + new_chunks
                if new_book_ids:
                    book_ids = list(dict.fromkeys((book_ids or []) + new_book_ids))
                log_json(
                    logger,
                    logging.INFO,
                    "Context-switch re-search succeeded",
                    new_books=len(new_book_ids) if new_book_ids else 0,
                    added_chunks=len(new_chunks),
                )
```

(`getattr` default keeps any `MagicMock`-free callers that build a bare `QueryContext` on legacy behavior; real `QueryContext` always has the field after Task 1.)

- [ ] **Step 4: Run tests**

Run: `pytest packages/backend-core/tests/app/services/rag_agent_tools_test.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/tools.py packages/backend-core/tests/app/services/rag_agent_tools_test.py
git commit -m "feat(rag): context-switch fallback searches whole library in direct mode"
```

---

### Task 4: Raise the HNSW candidate cap for library-wide search

**Files:**
- Modify: `packages/backend-core/app/db/repositories/chunks_repository.py:82-229` (`similarity_search`, unscoped branch)
- Test: `packages/backend-core/tests/app/db/chunks_repository_test.py`

**Interfaces:** none new. `similarity_search` signature unchanged.

**Why:** pgvector's HNSW scan returns at most `hnsw.ef_search` rows (default 40). The unscoped query asks for `inner_limit = limit*3 = 75`, then filters TOC pages, the similarity threshold and character categories *after* the index scan, so far fewer than `limit` good rows can survive. Raise the over-fetch to `limit*8` and set `ef_search` to match, scoped to the transaction with `SET LOCAL`.

- [ ] **Step 1: Check the production pgvector version** (needed for Step 5):

```sql
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```
Record the result in the PR description. Local is `0.8.3`.

- [ ] **Step 2: Write the failing test** — append to `chunks_repository_test.py`:

```python
@pytest.mark.asyncio
async def test_similarity_search_unscoped_raises_hnsw_ef_search():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.similarity_search([0.1] * 3072, limit=25)

    statements = [str(c.args[0]) for c in session.execute.await_args_list]
    assert any("SET LOCAL hnsw.ef_search = 200" in s for s in statements)
    final_params = session.execute.await_args_list[-1].args[1]
    assert final_params["inner_limit"] == 200


@pytest.mark.asyncio
async def test_similarity_search_scoped_does_not_touch_ef_search():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.similarity_search([0.1] * 3072, book_ids=["b1"], limit=25)

    statements = [str(c.args[0]) for c in session.execute.await_args_list]
    assert not any("ef_search" in s for s in statements)
```

- [ ] **Step 3: Run to verify failure**

Run: `pytest packages/backend-core/tests/app/db/chunks_repository_test.py -v -k ef_search`
Expected: the unscoped test FAILS (no SET LOCAL; `inner_limit == 75`).

- [ ] **Step 4: Implement.** Add module constants under the keyword-search constants:

```python
# HNSW returns at most hnsw.ef_search rows (pgvector default 40). The unscoped
# similarity search filters TOC pages, the score threshold and character
# categories *after* the index scan, so over-fetch generously and raise
# ef_search to match. pgvector caps ef_search at 1000.
_VECTOR_OVERFETCH_FACTOR = 8
_HNSW_EF_SEARCH_MAX = 1000
```

In `similarity_search`, replace `inner_limit = limit * 3` with:

```python
        # Over-fetch to compensate for TOC/threshold/category rows filtered out
        # in the outer query (see _VECTOR_OVERFETCH_FACTOR).
        inner_limit = min(int(limit) * _VECTOR_OVERFETCH_FACTOR, _HNSW_EF_SEARCH_MAX)
```

and in the `else:` (unscoped) branch, just before `result = await self.session.execute(query, params)` — guard so it only runs for the unscoped branch:

```python
        if book_ids is None:
            # Int-validated, never user input — SET does not accept bind params.
            await self.session.execute(
                text(f"SET LOCAL hnsw.ef_search = {int(inner_limit)}")
            )
```

- [ ] **Step 5 (only if prod pgvector ≥ 0.8.0): iterative scan for category-filtered search.** In the same `if book_ids is None:` block, add:

```python
            if categories:
                # pgvector ≥0.8: keep scanning the graph until enough rows pass
                # the post-filter instead of stopping at ef_search.
                await self.session.execute(
                    text("SET LOCAL hnsw.iterative_scan = relaxed_order")
                )
```

Add a test asserting the statement is issued when `categories=["history"]` and not otherwise. **If prod is < 0.8, skip this step** — an unknown GUC would abort the transaction.

- [ ] **Step 6: Run tests**

Run: `pytest packages/backend-core/tests/app/db/chunks_repository_test.py -v`
Expected: all PASS

- [ ] **Step 7: Check latency locally with EXPLAIN** (local data has few embeddings, so this checks the plan shape, not recall):

```bash
export $(grep ^DATABASE_URL .env | xargs)
psql "$DATABASE_URL" <<'SQL'
BEGIN;
SET LOCAL hnsw.ef_search = 200;
EXPLAIN ANALYZE
SELECT c.book_id FROM chunks c WHERE c.embedding IS NOT NULL
ORDER BY c.embedding::halfvec(3072) <=> (SELECT embedding::halfvec(3072) FROM chunks WHERE embedding IS NOT NULL LIMIT 1)
LIMIT 200;
ROLLBACK;
SQL
```
Expected: plan uses `Index Scan using idx_chunks_embedding`.

- [ ] **Step 8: Commit**

```bash
git add packages/backend-core/app/db/repositories/chunks_repository.py packages/backend-core/tests/app/db/chunks_repository_test.py
git commit -m "fix(rag): raise HNSW ef_search so library-wide vector search isn't capped at 40"
```

---

### Task 5 (optional): Reranker keeps keyword hits when truncating candidates

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/reranker.py:113-123`
- Test: `packages/backend-core/tests/app/services/rag_reranker_test.py`

- [ ] **Step 1: Write the failing test** — append to `rag_reranker_test.py`:

```python
from app.services.rag.agent.config import RERANK_MAX_INPUT_CHUNKS


@pytest.mark.asyncio
async def test_rerank_truncation_keeps_keyword_hits():
    vector_chunks = [
        _chunk(book_id="b1", page=i, text=f"vec-{i}", score=0.9 - i * 0.001)
        for i in range(RERANK_MAX_INPUT_CHUNKS + 5)
    ]
    keyword_hit = {"book_id": "b2", "page": 7, "text": "KEYWORD-HIT", "rank": 0.06}
    observations = [
        _search_obs(vector_chunks),
        {"tool": "search_keyword_phrase", "result": {"ok": True, "data": {"chunks": [keyword_hit]}}},
    ]
    llm = _mock_llm("[1]")
    with patch("app.services.rag.agent.reranker.build_text_llm", return_value=llm):
        await rerank_context("q", observations, model="gemini-test")

    prompt = llm.ainvoke.await_args.args[0]
    assert "KEYWORD-HIT" in prompt
    assert prompt.count("[Source:") + prompt.count("[BookID:") <= RERANK_MAX_INPUT_CHUNKS
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest packages/backend-core/tests/app/services/rag_reranker_test.py::test_rerank_truncation_keeps_keyword_hits -v`
Expected: FAIL — `"KEYWORD-HIT" not in prompt`

- [ ] **Step 3: Implement** — replace the truncation block in `rerank_context`:

```python
    candidates = docs
    if len(candidates) > RERANK_MAX_INPUT_CHUNKS:
        # Keyword hits carry `rank`, not a cosine `score`, so a score sort would
        # always push them below every vector hit and cut them. Reserve their
        # slots first, fill the rest with the best-scoring vector hits, and keep
        # the original pool order for the reranker prompt.
        keyword_docs = [d for d in candidates if d.metadata.get("rank") is not None]
        keyword_docs = keyword_docs[:RERANK_MAX_INPUT_CHUNKS]
        other_docs = sorted(
            (d for d in candidates if d.metadata.get("rank") is None),
            key=lambda d: (
                d.metadata.get("rrf_score", 0.0),
                d.metadata.get("score", 0.0),
            ),
            reverse=True,
        )[: RERANK_MAX_INPUT_CHUNKS - len(keyword_docs)]
        keep = {id(d) for d in keyword_docs} | {id(d) for d in other_docs}
        candidates = [d for d in candidates if id(d) in keep]
```

- [ ] **Step 4: Run tests**

Run: `pytest packages/backend-core/tests/app/services/rag_reranker_test.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/services/rag/agent/reranker.py packages/backend-core/tests/app/services/rag_reranker_test.py
git commit -m "fix(rag): reranker truncation no longer drops keyword-phrase hits"
```

---

### Task 6 (optional): Suffix-tolerant keyword matching for the agent's keyword tool

**Files:**
- Modify: `packages/backend-core/app/db/repositories/chunks_repository.py` (`keyword_search` + new helper)
- Modify: `packages/backend-core/app/services/rag/retrieval.py:184-189` (`agent_keyword_search`)
- Test: `packages/backend-core/tests/app/db/chunks_repository_test.py`, `packages/backend-core/tests/app/services/rag_retrieval_test.py`

**Interfaces:**
- Produces: `build_prefix_tsquery(phrase: str) -> str` (module function in `chunks_repository.py`).
- Produces: `ChunksRepository.keyword_search(..., prefix_match: bool = False)`. Only `agent_keyword_search` passes `True`. The quoted exact-phrase gate (`exact_phrase_chunk_search`) and the home Content search keep strict matching.

- [ ] **Step 1: Write failing tests** — append to `chunks_repository_test.py`:

```python
from app.db.repositories.chunks_repository import build_prefix_tsquery


def test_build_prefix_tsquery_adds_prefix_to_long_tokens_only():
    assert build_prefix_tsquery("ھوزۇرۇم مۇقام") == "ھوزۇرۇم:* <-> مۇقام:*"
    assert build_prefix_tsquery("ئۇ ئەلى") == "ئۇ <-> ئەلى:*"


def test_build_prefix_tsquery_strips_tsquery_operators_and_punctuation():
    assert build_prefix_tsquery("«بابۇر» & (شاھ)") == "بابۇر:* <-> شاھ"
    assert build_prefix_tsquery("  !!  ") == ""


@pytest.mark.asyncio
async def test_keyword_search_prefix_match_uses_to_tsquery():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("ھوزۇرۇم", prefix_match=True)

    sql = str(session.execute.await_args_list[-1].args[0])
    params = session.execute.await_args_list[-1].args[1]
    assert "to_tsquery('simple', :phrase)" in sql
    assert "phraseto_tsquery" not in sql
    assert params["phrase"] == "ھوزۇرۇم:*"


@pytest.mark.asyncio
async def test_keyword_search_prefix_match_empty_query_returns_empty():
    session = AsyncMock()
    repo = ChunksRepository(session)
    assert await repo.keyword_search("!!", prefix_match=True) == []
    session.execute.assert_not_called()
```

Note: `"شاھ"` is 3 characters, so it stays exact; `MIN_PREFIX_LEN` is 4.

In `rag_retrieval_test.py`, update `test_agent_keyword_search_passes_config_limit_and_scope`: add `prefix_match=False` to `fake_keyword_search`'s signature, record `captured["prefix_match"] = prefix_match`, and add `"prefix_match": True` to the expected `captured` dict. Do the same signature update in any other `fake_keyword_search` in that file used by `agent_keyword_search` tests.

- [ ] **Step 2: Run to verify failure**

Run: `pytest packages/backend-core/tests/app/db/chunks_repository_test.py packages/backend-core/tests/app/services/rag_retrieval_test.py -v -k "prefix or agent_keyword"`
Expected: FAIL — `ImportError: cannot import name 'build_prefix_tsquery'`

- [ ] **Step 3: Implement the helper** in `chunks_repository.py` (add `import re` at top):

```python
# Uyghur is agglutinative: "ھوزۇرۇم" appears as "ھوزۇرۇمنى", "ھوزۇرۇمدا", ...
# A prefix tsquery (word:*) per token keeps phrase adjacency (<->) while
# tolerating suffixes. Tokens shorter than this stay exact so a 2-3 letter
# particle can't expand to a huge GIN posting list.
_PREFIX_MIN_TOKEN_LEN = 4
_TSQUERY_STRIP = re.compile(r"[&|!():*<>'\\\"«»،؟.,;:\-\[\]{}]")


def build_prefix_tsquery(phrase: str) -> str:
    """Build a to_tsquery('simple', ...) string: tokens joined by <->, each
    token ≥4 chars suffixed with :*. Returns "" when nothing usable remains.
    The result is still passed as a bound parameter."""
    cleaned = _TSQUERY_STRIP.sub(" ", phrase or "")
    tokens = [t for t in cleaned.split() if t]
    return " <-> ".join(
        f"{t}:*" if len(t) >= _PREFIX_MIN_TOKEN_LEN else t for t in tokens
    )
```

- [ ] **Step 4: Use it in `keyword_search`.** Add `prefix_match: bool = False` to the signature. At the top of the method body:

```python
        if prefix_match:
            phrase = build_prefix_tsquery(phrase)
            if not phrase:
                return []
            tsquery_expr = "to_tsquery('simple', :phrase)"
        else:
            tsquery_expr = "phraseto_tsquery('simple', :phrase)"
```

Then in **both** SQL branches, replace every literal `phraseto_tsquery('simple', :phrase)` (two per branch: in `ts_rank(...)` and in the `@@` predicate) with `{tsquery_expr}` (the SQL strings are already f-strings). Update the docstring's first paragraph to mention `prefix_match`.

- [ ] **Step 5: Pass it from the agent tool** — in `retrieval.py` `agent_keyword_search`:

```python
    return await chunks_repo.keyword_search(
        phrase=phrase,
        book_ids=book_ids,
        categories=ctx.character_categories or None,
        limit=rag_keyword_top_k,
        prefix_match=True,
    )
```

- [ ] **Step 6: Run tests**

Run: `pytest packages/backend-core/tests/app/db/chunks_repository_test.py packages/backend-core/tests/app/services/rag_retrieval_test.py -v`
Expected: all PASS

- [ ] **Step 7: Check the query against local pages** (pages have text locally even without embeddings):

```bash
export $(grep ^DATABASE_URL .env | xargs)
psql "$DATABASE_URL" -c "SELECT count(*) FROM pages WHERE text_search @@ phraseto_tsquery('simple','ھوزۇرۇم');" \
                     -c "SELECT count(*) FROM pages WHERE text_search @@ to_tsquery('simple','ھوزۇرۇم:*');" \
                     -c "EXPLAIN ANALYZE SELECT 1 FROM pages WHERE text_search @@ to_tsquery('simple','ھوزۇرۇم:*') LIMIT 10;"
```
Expected: the prefix count ≥ the exact count; plan uses `idx_pages_text_search`; runtime well under the 5 s statement timeout.

- [ ] **Step 8: Commit**

```bash
git add packages/backend-core/app/db/repositories/chunks_repository.py packages/backend-core/app/services/rag/retrieval.py \
  packages/backend-core/tests/app/db/chunks_repository_test.py packages/backend-core/tests/app/services/rag_retrieval_test.py
git commit -m "feat(rag): suffix-tolerant prefix matching for agent keyword search"
```

---

### Task 7: Docs and skill sync

**Files:**
- Modify: `docs/main/CHAT_RAG_DESIGN.md`
- Modify: `docs/main/SUMMARY_DESIGN.md`
- Modify: `.claude/skills/prompt-engineer/SKILL.md`

- [ ] **Step 1: Find every reference**

Run: `grep -n "search_books_by_summary\|summary_threshold\|ef_search\|phraseto_tsquery\|RERANK_MAX_INPUT" docs/main/CHAT_RAG_DESIGN.md docs/main/SUMMARY_DESIGN.md .claude/skills/prompt-engineer/SKILL.md`

- [ ] **Step 2: Update `CHAT_RAG_DESIGN.md`.** Where the retrieval agent's book-discovery step is described, add this subsection (adjust heading level to match the surrounding section), and fix any mermaid node that shows summary search as an unconditional step to show it as conditional on the flag:

```markdown
#### Summary narrowing vs direct chunk search (`rag_summary_narrowing_enabled`)

| Value | Behavior |
|-------|----------|
| `true` (also the default when the row is missing) | Legacy: content questions that name no book/author/current book first call `search_books_by_summary` (top ~30 books by summary similarity), then `search_chunks` scoped to those books. |
| `false` (seeded by migration 098) | `search_books_by_summary` is not exposed to the retrieval agent. Unscoped content questions call `search_chunks` with no `book_ids` (library-wide HNSW search). The context-switch fallback in `_run_search_chunks` re-searches the whole library instead of rediscovering books via summaries. Character-identity questions use chunk + keyword search instead of `get_book_summary`. |

`get_book_summary` for "what is this book about" questions is unaffected by the flag. The prompt variants live in `build_agent_system_prompt()` in `services/rag/agent/prompts.py`.
```

If Tasks 4–6 shipped, also document: library-wide vector search over-fetches `limit × 8` with `SET LOCAL hnsw.ef_search` to match (and `hnsw.iterative_scan = relaxed_order` for category filters, if Step 5 shipped); the reranker reserves slots for keyword hits before truncating to 50; and `search_keyword_phrase` uses per-token prefix matching (`to_tsquery('simple', 'a:* <-> b:*')`, tokens ≥4 chars) while the quoted exact-phrase gate stays strict.

- [ ] **Step 3: Update `SUMMARY_DESIGN.md`** — where it says summaries are used for retrieval narrowing, add: "Retrieval narrowing via `search_books_by_summary` only runs when `rag_summary_narrowing_enabled = true`; see CHAT_RAG_DESIGN.md."

- [ ] **Step 4: Update `.claude/skills/prompt-engineer/SKILL.md`** — wherever it describes the retrieval agent prompt, note that it is now built by `build_agent_system_prompt(summary_narrowing: bool)` with two variants, and that edits to shared steps (1–4, 6b, 7) affect both.

- [ ] **Step 5: Commit**

```bash
git add docs/main/CHAT_RAG_DESIGN.md docs/main/SUMMARY_DESIGN.md .claude/skills/prompt-engineer/SKILL.md
git commit -m "docs(rag): document summary-narrowing flag and retrieval recall fixes"
```

---

### Task 8: A/B evaluation on production data

Local data can't evaluate this: only 63 of 526,168 local chunks have embeddings, and `tests/adk_eval` / `tests/deterministic_eval` are empty. Run on production (or a prod snapshot) after the branch is deployed with migration 098 applied.

- [ ] **Step 1: Build a question set (20–30 questions)** with the expected book and page(s) written down *before* running. Cover:
  - topics mentioned on only a few pages of a book whose summary is about something else (the case summary narrowing loses);
  - people/characters ("X كىم؟") not in the history dictionary;
  - cross-book topics (one event covered in several books);
  - a named book + specific detail (should behave the same in both modes);
  - rare proper nouns that appear inflected (exercises Task 6);
  - character personas with category filters (exercises Task 4 Step 5).

- [ ] **Step 2: Run each question in both modes** by toggling the flag between runs (no redeploy needed):

```sql
UPDATE system_configs SET value = 'true',  updated_at = NOW() WHERE key = 'rag_summary_narrowing_enabled';
-- run all questions
UPDATE system_configs SET value = 'false', updated_at = NOW() WHERE key = 'rag_summary_narrowing_enabled';
-- run all questions again
```

The RAG query cache (`cache_ttl_rag_query`, 1 h) keys on embedding + book scope, so mode A results can't leak into mode B. Still, use a fresh conversation per question to avoid co-reference carry-over.

- [ ] **Step 3: Record per question:** whether the expected page was cited; `rag_evaluations.latency_ms`, `retrieved_count`, `tools_called`, `faithfulness_score`; and the `"Retrieval agent mode"` and `"Agent tool search_chunks"` log lines (book_count, results).

- [ ] **Step 4: Decide.** Keep `false` as the default if expected-page hit rate is equal or better and p50 latency is within your tolerance. Write the result to `docs/poc/direct-chunk-retrieval/REPORT.md`. If `false` wins clearly, a follow-up PR can delete the legacy prompt branch and the `search_books_by_summary` tool. Keep the `book_summaries` table: `get_book_summary` still uses it.

---

## Self-review notes

- Spec coverage: summary-narrowing removal behind a flag (Tasks 1–3), semantic search improvement (Task 4), keyword search improvements (Tasks 5–6), and a way to judge the result (Task 8). RRF, query normalization and embedding task prefixes are explicitly out of scope, with reasons.
- Types are consistent: `summary_narrowing_enabled` (ctx field and builder kwarg), `summary_narrowing` (prompt builder kwarg), `prefix_match` (repo kwarg), `build_prefix_tsquery` (helper).
- Known residual: `get_books_by_author` for a prolific author still triggers the per-book quota (`retrieval.py:287`), producing more than 25 chunks. Task 5 keeps keyword hits safe when that happens; capping the quota is left for after Task 8.
