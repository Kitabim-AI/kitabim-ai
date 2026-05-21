# Agentic RAG — Current Implementation

See [QUESTION_ANSWERING_DIAGRAM.md](QUESTION_ANSWERING_DIAGRAM.md) for the visual pipeline diagram.

---

## Overview

The RAG pipeline uses a LangGraph graph-based agent (`AgentRAGHandler`, priority=998) as the sole handler for all questions. The agent decides which retrieval tools to call, retries with refined queries when results are thin, and stops when it has sufficient context.

Three quality nodes sit around the ReAct loop: a **decompose_query** node (splits multi-question inputs before the loop), a **planner** (heuristic intent detection), and a **grade_context** node (score-based chunk filtering before answer generation).

---

## Handler registry

| Handler | Priority | Behaviour |
|---------|----------|-----------|
| `AgentRAGHandler` | 998 | Sole handler — all questions run the LangGraph graph |

---

## Agent tool set (10 tools)

### Content retrieval

| Tool | Wraps | Cache | Description |
|------|-------|-------|-------------|
| `search_chunks` | `ChunksRepository.similarity_search` | L1 (embed) + L2 (results) | Vector-search passages; primary retrieval tool |
| `search_books_by_summary` | `BookSummariesRepository.summary_search` | L3 | Find which books cover a topic when book scope is unknown |
| `find_books_by_title` | `BooksRepository` title match | — | Resolve a book title mentioned in the question to book IDs |
| `get_book_summary` | `BookSummariesRepository.get_summaries_for_books` | — | Fetch full semantic summary text for specific books; called for plot/character/theme questions |
| `get_current_page` | `PagesRepository.find_one` | — | Raw text of the page currently open in the reader; only callable in single-book mode when `[Context]` includes `current_page` |
| `get_sister_volumes` | `BooksRepository.find_sister_volumes` | — | All volumes of the same title+author series as a given `book_id`; called when the question asks about a different volume (next/previous/numbered) of the current or previously-discussed book |
| `rewrite_query` | `QueryRewriter.rewrite` | L0 | Resolve co-references; short-circuits if `ctx.enriched_question` is already set |

### Catalog & metadata

| Tool | Wraps | Description |
|------|-------|-------------|
| `get_book_author` | `BooksRepository.find_author_by_title_in_question` | Author lookup for who-wrote-X questions |
| `get_books_by_author` | `BooksRepository.find_books_by_author_in_question` | Book list for what-did-Y-write questions |
| `search_catalog` | `CatalogHandler._build_catalog_context` | Library browsing and general catalog questions |

Metadata tools return a `"context"` key that `format_observations_as_context` prepends before chunk passages in the final context string.

---

## Agent loop (LangGraph graph)

The agent is implemented as a compiled LangGraph `StateGraph` operating on `AgentState`. All state mutations are immutable returns from node functions; LangGraph merges annotated fields (`messages` via `add_messages`, `observations` via `operator.add`).

### Graph topology

```
START → decompose_query → plan_query → agent_step
agent_step  → [execute_tool ×N  (parallel Send)]  |  build_context
execute_tool → collect_tools
collect_tools → [agent_step  |  build_context]
build_context → grade_context → generate_answer → END
```

### Conditional edge functions

| Edge source | Condition | Destinations |
|-------------|-----------|--------------|
| `agent_step` | Has tool calls → fan-out via `Send` per tool call; no tool calls → exit loop | `execute_tool` (×N, parallel) or `build_context` |
| `collect_tools` | `total_chunks >= AGENT_ENOUGH_CHUNKS` or `step_count >= AGENT_MAX_STEPS` → exit; otherwise → loop | `build_context` or `agent_step` |

### Node descriptions

| Node | What it does |
|------|-------------|
| `decompose_query` | Heuristic question-mark count first (zero LLM cost when ≤ 1 `?`/`؟`). For inputs with multiple question marks, a cheap LLM call splits the text into up to 4 self-contained sub-questions and rewrites the `HumanMessage` in-place so `agent_step` retrieves for all of them. Sets `sub_questions`. Emits `decompose` SSE event (only when actually split). |
| `plan_query` | Heuristic intent detection (no LLM) — classifies the question as `current_page`, `catalog`, or `content_search`; detects pronoun/clitic co-references that need rewriting. Emits `planning` SSE event. |
| `agent_step` | One ReAct LLM call with all 10 tools bound. Increments `llm_calls` and `step_count`. Emits `agent_thinking` SSE event. |
| `execute_tool` | Runs a single tool call (invoked in parallel via `Send` for each tool the agent requested). Appends one observation and one `ToolMessage`. Emits `tool_call` then `tool_result` SSE events. |
| `collect_tools` | Fan-in aggregator after parallel tool executions. Recomputes `total_chunks` from merged observations. No SSE. |
| `build_context` | Calls `format_observations_as_context`; deduplicates chunks by `(book_id, page)`, sorts by score DESC, caps at `AGENT_MAX_CONTEXT_CHUNKS`. Sets `retrieved_context` and `used_book_ids`. No SSE. |
| `grade_context` | Relative-score threshold filter — keeps chunks within `GRADE_RELATIVE_THRESHOLD` of the top score; falls back to `MIN_CHUNKS_AFTER_GRADING` if too few survive. Prepends metadata context blocks unchanged. Sets `graded_context`. Emits `grading` SSE event. |
| `generate_answer` | Streams answer tokens via `generate_answer_stream`. When `sub_questions` has more than one item, formats the question as a numbered list before generation. Sets `final_answer`. Emits `answer_start`, `chunk` (×N), `answer_end` SSE events. |

### Context injection — `_build_human_message`

Before the first LLM call, the initial `HumanMessage` is enriched with a `[Context]` block:

- **Single-book mode** (`is_global=False`): injects current book title, author, volume, and `book_id`. Agent calls `search_chunks` directly with that `book_id`, skipping `find_books_by_title` entirely. Exception: if the question asks about a different volume, the agent calls `get_sister_volumes` first to discover the correct sister volume ID.
- **Global mode** (`is_global=True`): injects `context_book_ids` (up to 10, frontend-tracked from prior turns) and `character_categories`. Agent tries `search_chunks` with those IDs before falling back to `search_books_by_summary`.
- When nothing useful is available, returns the bare question — no overhead.

---

## Agent system prompt strategy

```
1. Rewrite first (if pronouns or "چۇ" particle and history exists) → rewrite_query
2. Metadata questions:
   - "who wrote X?" → get_book_author
   - "what did Y write?" → get_books_by_author
   - library browsing → search_catalog
3. Content questions:
   a-0. [Context] has current_page and user asks about content of the current page →
        get_current_page immediately (do NOT call search_chunks)
   a. Question asks for plot/themes/main characters of a specific book →
        find_books_by_title → get_book_summary (do NOT call search_chunks)
   b. Question explicitly names a title and asks for passages/details →
        find_books_by_title → search_chunks with resulting IDs
   c. Question explicitly names an author →
        get_books_by_author → search_chunks with resulting IDs
   d. No title/author named, but [Context] has a current book_id →
        - Sister volume question (next/prev/numbered volume) →
          get_sister_volumes(current book_id) → search_chunks with the right volume's ID
        - Otherwise → search_chunks directly with that book_id
   e. No title/author named, but [Context] has previous response book IDs →
        - Sister volume question →
          get_sister_volumes(context_book_ids[0]) → search_chunks with the right volume's ID
        - Otherwise → search_chunks with those IDs first
   f. All other cases (general topics, character lookups) →
        search_books_by_summary → search_chunks with returned IDs
   g. < 4 results? → retry with rephrased query or search_chunks with empty
        book_ids (entire library) — only after prior discovery steps failed
4. Stop when 6–12 passages collected (or catalog/author result for metadata)
Hard limits: 4 tool calls total. Never call search_chunks with empty book_ids
unless find_books_by_title / get_books_by_author / search_books_by_summary
have already returned no results.
```

---

## Streaming events (SSE)

Events flow from graph nodes → `rag_service.answer_question_stream` → `chat.py` `/stream` endpoint → frontend.

### Event reference

| Node | Event `type` | Payload | When |
|------|-------------|---------|------|
| `decompose_query` | `decompose` | `{"type": "decompose", "count": int}` | Only when the input is actually split (> 1 sub-question detected) |
| `plan_query` | `planning` | `{"type": "planning", "intent": str}` | Once, before the ReAct loop starts |
| `agent_step` | `agent_thinking` | `{"type": "agent_thinking", "step": int}` | Once per ReAct loop iteration |
| `execute_tool` | `tool_call` | `{"type": "tool_call", "tool": str, "args": dict}` | Once per tool call, before execution |
| `execute_tool` | `tool_result` | `{"type": "tool_result", "tool": str, "found": int}` | Once per tool call, after execution |
| `grade_context` | `grading` | `{"type": "grading", "before": int, "after": int}` | Once, after chunk filtering |
| `generate_answer` | `answer_start` | `{"type": "answer_start"}` | Once, before the first token |
| `generate_answer` | `chunk` | `{"type": "chunk", "text": str}` | Once per streamed token |
| `generate_answer` | `answer_end` | `{"type": "answer_end"}` | Once, after the last token |
| `chat.py` (endpoint) | `correction` | `{"correction": str}` | Only if citation fixer modifies the accumulated answer |
| `chat.py` (endpoint) | `done` | `{"done": true, "usage": {...}, "contextBookIds": [...]}` | After all events, signals completion |

### Endpoint translation

`chat.py` translates graph events before forwarding to the client:
- `{"type": "chunk", "text": t}` → `{"chunk": t}` (frontend-compatible format)
- `answer_start` resets the accumulator so `fix_malformed_citations` only sees the final pass
- All other dict events pass through as-is

### Frontend rendering behaviour

`useChat.ts` maintains `agentSteps: AgentStep[]` driven by the event stream. Step types: `'decomposing' | 'planning' | 'thinking' | 'tool' | 'grading'`. Behaviour:
- `decompose` event appends a `decomposing` step (immediately `done`) with `count`.
- `planning` appends a `planning` step (immediately `done`).
- `tool_result` marks the most-recent active `tool` step as `done` with its `found` count.
- `agent_thinking` replaces or appends a `thinking` step rather than stacking duplicates.
- `answer_start` resets `streamingMessage` and the accumulator — no critique retry path.

`ChatInterface.tsx` renders a single unified bubble when `isChatting` is true:

1. **Streaming content present** — renders `streamingMessage`; bouncing dots or a spinner shows progress.
2. **No streaming content, steps present** — renders `<AgentThinkingSteps steps={agentSteps} />` at full width (`w-full`).
3. **Neither** — renders the `TypingCarousel` (animated Uyghur phrases) as a placeholder before the first real event arrives.

`AgentThinkingSteps.tsx` is always `w-full` and renders each step in a compact row (icon + label + optional sublabel). Active steps show at full opacity; completed steps dim to 50%.

---

## Caching (4 levels)

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool via `QueryRewriter` | Deduplicate follow-up rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call per query | Reuse embeddings across all tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Reuse pgvector search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Reuse book-selection results |

> Redis checkpointing for `AgentState` is deferred and not currently implemented.

---

## Typical agent traces

### Single-book question (1 step — context injection eliminates discovery)
```
User: بابۇرنامىدە ئاغرا شەھىرى توغرىسىدا نېمە دېيىلگەن؟
[Context] Current book: "بابۇرنامە" (book_id: abc123)

decompose_query → single question (no-op)
plan_query → intent=content_search
agent_step → search_chunks(query="بابۇرنامىدە ئاغرا شەھىرى", book_ids=["abc123"])
collect_tools → total_chunks=10 [≥ AGENT_ENOUGH_CHUNKS → build_context]
build_context → grade_context → generate_answer
→ END
```

### Global question — topic unknown (2 steps)
```
User: ئابدۇرەھىم ئۆتكۈر كىم؟

decompose_query → single question (no-op)
plan_query → intent=content_search
agent_step → search_books_by_summary(query="ئابدۇرەھىم ئۆتكۈر")
           → search_chunks(query="ئابدۇرەھىم ئۆتكۈر", book_ids=[A, B, C])
collect_tools → total_chunks=12 [≥ AGENT_ENOUGH_CHUNKS → build_context]
build_context → grade_context → generate_answer
→ END
```

### "چۇ" follow-up — resolved by rewrite_query tool (2 steps)
```
Prior turn: user asked about "بابۇرنامە"
User: يىگانە ئارالنىڭچۇ؟

[Context] Current book: "بابۇرنامە" (book_id: abc123)

decompose_query → single question (no-op)
plan_query → intent=content_search (detects "چۇ" clitic co-reference)
agent_step → rewrite_query()
           → ctx.enriched_question = "يىگانە ئارال ھەققىدە بابۇرنامىدە نېمە دېيىلگەن؟"
           → search_chunks(query="يىگانە ئارال", book_ids=["abc123"])
collect_tools → total_chunks=8 [≥ AGENT_ENOUGH_CHUNKS → build_context]
build_context → grade_context → generate_answer
→ END
```

### Sister volume question (2 steps — reader mode)
```
User is reading "بابۇرنامە" Volume 1 (book_id: abc123)
User: كەيىنكى تومدا نېمە بولىدۇ؟

[Context] Current book: "بابۇرنامە" by Babur, volume 1 (book_id: abc123)

decompose_query → single question (no-op)
plan_query → intent=content_search
agent_step → get_sister_volumes(book_id="abc123")
           → search_chunks(query="كەيىنكى تومدا نېمە بولىدۇ", book_ids=["def456"])
collect_tools → total_chunks=9 [≥ AGENT_ENOUGH_CHUNKS → build_context]
build_context → grade_context → generate_answer
→ END
```

### Retry on thin results (3 steps)
```
User: ئۆتكۈرنىڭ شېئىرلىرى ھەققىدە نېمە بىلىسەن؟

decompose_query → single question (no-op)
plan_query → intent=content_search
agent_step (step 1) → search_books_by_summary(query="ئۆتكۈر شېئىر") → [book_id_A]
agent_step (step 2) → search_chunks(query="ئۆتكۈرنىڭ شېئىرلىرى", book_ids=[A]) → 3 chunks
agent_step (step 3) → search_chunks(query="ئۆتكۈر شېئىر ئەدەبىيات", book_ids=[A]) → 7 chunks
                    → no tool calls [→ build_context]
build_context → grade_context → generate_answer
→ END
```

### Multi-question input (decompose path)
```
User: بابۇرنامە نەدە يېزىلغان؟ ئاندىن ئۇ قايسى تىلدا يېزىلغان؟

decompose_query → LLM split → 2 sub-questions
                → HumanMessage updated with [Sub-questions] block
plan_query → intent=content_search
agent_step → search_chunks(query="بابۇرنامە يېزىلغان جاي", book_ids=["abc123"]) + ...
collect_tools → total_chunks ≥ AGENT_ENOUGH_CHUNKS → build_context
build_context → grade_context → generate_answer (numbered sub-questions as input)
→ END
```

---

## Latency budget

| Component | Typical latency |
|-----------|-----------------|
| `decompose_query` (heuristic, ≤ 1 `?`) | ~1 ms |
| `decompose_query` (LLM split, > 1 `?`) | ~400–700 ms |
| `plan_query` (heuristic, no LLM) | ~1 ms |
| Context injection (`_build_human_message`) | <1 ms |
| `rewrite_query` (L0 cache hit) | ~2 ms |
| `search_books_by_summary` (L3 cache hit) | ~2 ms |
| `search_books_by_summary` (cache miss: embed + query) | ~300 ms |
| `search_chunks` (L2 cache hit) | ~2 ms |
| `search_chunks` (cache miss: embed + pgvector) | ~50 ms |
| Agent LLM decision call (Gemini Flash, tool-use) | ~400–700 ms |
| `grade_context` (heuristic, no LLM) | ~5 ms |
| Final answer generation (streaming) | ~1–3 s |

Best case (single-book, context injected, L2 hit, single question): decompose (~1 ms) + planner (~1 ms) + 1 agent call (~500 ms) + grade (~5 ms) + answer (~2 s) ≈ **2.5 s**.  
Worst case (multi-question decompose + 4 steps, all cache misses): decompose (~600 ms) + ~4 × 700 ms + ~4 × 350 ms + grade + answer ≈ 7–10 s.

---

## Files

```
packages/backend-core/app/services/rag/agent/
  __init__.py          # package marker
  config.py            # AGENT_MAX_STEPS, AGENT_ENOUGH_CHUNKS, AGENT_MAX_CONTEXT_CHUNKS,
                       # GRADE_RELATIVE_THRESHOLD, MIN_CHUNKS_AFTER_GRADING,
                       # CONTEXT_SWITCH_SCORE_THRESHOLD
  prompts.py           # AGENT_SYSTEM_PROMPT — retrieval strategy instructions
  tools.py             # @tool schemas + dispatch_tool() — 10 tools
  state.py             # AgentState TypedDict (includes sub_questions)
  graph.py             # LangGraph StateGraph — wires all nodes and conditional edges
  handler.py           # AgentRAGHandler — priority=998
  nodes/
    __init__.py
    decompose.py       # decompose_query node — heuristic + LLM multi-question split
    planner.py         # plan_query node — heuristic intent detection
    agent_step.py      # agent_step node — one ReAct LLM call
    execute_tool.py    # execute_tool node — single tool executor (parallel via Send)
    collect_tools.py   # collect_tools node — fan-in aggregator
    build_context.py   # build_context node — wraps format_observations_as_context
    grade_context.py   # grade_context node — relative-score chunk filter
    generate_answer.py # generate_answer node — streams answer tokens; formats sub_questions if > 1

packages/backend-core/app/services/rag/
  answer_builder.py    # generate_answer_stream(), format_observations_as_context(),
                       # format_document()
  retrieval.py         # Shared IO primitives: embed_query, vector_search,
                       # find_books_by_title_in_question
```

Supporting files:
- `app/services/rag/query_rewriter.py` — LLM rewrite with L0 caching
- `app/langchain/models.py` — `invoke_with_tools()` and `generate_text()` using shared rate limiter + circuit breaker

Frontend:
- `apps/frontend/src/hooks/useChat.ts` — `agentSteps` state; `handleAgentEvent` dispatcher; step types: `decomposing | planning | thinking | tool | grading`
- `apps/frontend/src/components/chat/ChatInterface.tsx` — unified streaming bubble
- `apps/frontend/src/components/chat/AgentThinkingSteps.tsx` — step list renderer, always `w-full`

---

## QueryContext fields written by the agent

| Field | Written by |
|-------|-----------|
| `ctx.query_vector` | `search_chunks` / `search_books_by_summary` (L1 cache side-effect) |
| `ctx.enriched_question` | `rewrite_query` tool |
| `ctx.used_book_ids` | `graph.populate_ctx_from_state` — from `AgentState.used_book_ids` |
| `ctx.retrieved_count` | total chunks across all `search_chunks` calls |
| `ctx.scores` | scores from all retrieved chunks |
| `ctx.agent_steps` | LLM call count (`AgentState.llm_calls`) |
| `ctx.agent_tools_called` | ordered list of tool names from observations |
| `ctx.agent_retry_count` | number of `search_chunks` invocations |
| `ctx.agent_final_chunk_count` | unique chunks after grading (counted from `graded_context`) |

---

## LLM calls in a full pipeline run

| Call | Model | Purpose |
|------|-------|---------|
| `decompose_query` | Gemini Flash (cheap) — only when > 1 `?`/`؟` | Split multi-question input into sub-questions; zero-cost for single questions |
| `plan_query` | — (no LLM) | Heuristic intent detection; zero-cost |
| Agent ReAct loop (1–N) | Gemini Flash (tool-use) | Tool selection per step |
| `grade_context` | — (no LLM) | Score-based chunk filtering; heuristic |
| `generate_answer` | Gemini Pro / configured model | Streaming answer generation |

---

## RAG evaluation metrics

Every chat response writes a `rag_evaluations` row when `rag_eval_enabled=true`. Agent-path rows include:

| Column | Value |
|--------|-------|
| `agent_steps` | LLM calls in the loop (1–4) |
| `tools_called` | JSON array of tool names in order |
| `retry_count` | number of `search_chunks` invocations |
| `final_chunk_count` | unique chunks passed to answer generation |
| `min_score` / `max_score` | score range across retrieved chunks |

---

## Morphological matching

Entity matching in `BooksRepository` and `utils.py` handles Uyghur agglutinative suffixes:
- Word-prefix matching: `"بابۇرنامە"` matches `"بابۇرنامىنىڭ"` in a question.
- ە→ى alternation: genitive/dative case suffixes replace the final ە (U+06D5) with ى (U+06CC). Both forms are tried for every entity word.

This affects `get_book_author`, `get_books_by_author`, `find_books_by_title`, and `search_catalog`.
