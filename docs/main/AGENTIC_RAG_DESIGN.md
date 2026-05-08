# Agentic RAG Design

## Overview

Convert `StandardRAGHandler` from a fixed retrieval pipeline into an LLM-driven agent loop. The agent decides which retrieval tools to call, can retry with refined queries, and self-evaluates whether its context is sufficient before answering.

**Scope:** Only `StandardRAGHandler` changes. The nine specialized handlers (`IdentityHandler`, `FollowUpHandler`, `AuthorByTitleHandler`, etc.) are already purpose-built and do not benefit from agentic behavior.

---

## Problem with the current pipeline

`StandardRAGHandler._build_rag_context()` follows a fixed decision tree:

```
embed query
  → title match?  → use those books
  → else: summary search?  → use those books
  → else: context_book_ids?  → use those
  → else: category fallback  → use those
→ vector search chunks
→ if empty: summary fallback
→ answer
```

Failure modes this design cannot recover from:
- Summary search returns topically wrong books → chunk search finds nothing → answers from an irrelevant summary
- Query uses a pronoun that wasn't fully resolved → embedding is off → wrong chunks retrieved
- User asks a multi-part question → single retrieval scope misses half the answer
- Threshold is too strict → 0 results → no retry with relaxed threshold

---

## Design goals

1. The agent decides what to retrieve — not a hard-coded if/else tree.
2. The agent can retry: different query, different book scope.
3. The agent stops when context is sufficient, not after a fixed number of steps.
4. Latency stays within reason: cap at 4 tool calls per question; all existing caches still apply.
5. Streaming is preserved end-to-end.
6. No changes to `QueryContext`, `HandlerRegistry`, specialized handlers, or `answer_builder.py`.

---

## Architecture

### What stays the same

| Component | Status |
|-----------|--------|
| `HandlerRegistry` + all 9 specialized handlers | Unchanged |
| `QueryContext` | Unchanged (agent reads and writes same fields) |
| `answer_builder.py` (`generate_answer`, `generate_answer_stream`) | Unchanged |
| `QueryRewriter` | Unchanged, called as a tool |
| All three cache layers (embedding, chunk search, summary search) | Unchanged |
| `ChunksRepository.similarity_search()` | Unchanged |
| `BookSummariesRepository.summary_search()` | Unchanged |

### What changed

`AgentRAGHandler` (priority=998) is added to the registry **alongside** `StandardRAGHandler` (priority=999). When `agentic_rag_enabled=true` in `system_configs`, `AgentRAGHandler` runs the loop and generates the answer. When the flag is off, it immediately delegates to `StandardRAGHandler` — zero-cost fallback.

`invoke_with_tools(model_name, messages, tools)` was added to `app/langchain/models.py` to invoke Gemini with tool definitions while reusing the existing rate limiter and circuit breaker.

---

## Tool definitions

Four tools are exposed to the agent. Each maps directly to existing code with no new retrieval logic.

### `search_chunks`
```
Description: Vector-search book chunks for passages relevant to a query.
Parameters:
  query        string   — the question or sub-query to embed and search
  book_ids     string[] — restrict to these book IDs; omit for global search
Returns: list of { text, score, title, author, volume, page, book_id }
```
Maps to: `StandardRAGHandler._vector_search()` via Level-1 (embedding) + Level-2 (chunk search) caches.

### `search_books_by_summary`
```
Description: Find books whose summary embeddings are closest to a query.
             Call before search_chunks when you don't know which books to search.
Parameters:
  query        string   — the question to embed and compare against summaries
  book_ids     string[] — restrict to a candidate set (e.g. character-filtered books)
Returns: list of book_ids sorted by similarity DESC
```
Maps to: `StandardRAGHandler._summary_search()` via Level-3 (summary) cache.

### `find_books_by_title`
```
Description: Return all volume IDs for a book title mentioned in the question.
             Handles «quoted» exact match and fuzzy word-prefix match.
Parameters:
  question     string   — the full question text (title extraction is done server-side)
Returns: list of book_ids, or empty list if no title was detected
```
Maps to: `StandardRAGHandler._find_books_by_title_in_question()`.

### `rewrite_query`
```
Description: Resolve pronouns and co-references in a follow-up question using
             the chat history. Use when the question contains "ئۇ", "بۇ", "شۇ"
             or references something from a previous turn.
Parameters:
  question     string   — the raw user question
Returns: { rewritten_question: string }
```
Maps to: `QueryRewriter.rewrite()` (Level-1 cached). Side-effect: sets `ctx.enriched_question`.

> **Note:** The original design included an `answer` terminal tool. The implementation uses the simpler convention of stopping when the LLM returns a response with no tool calls, which is idiomatic for LangChain + Gemini function calling.

---

## Agent loop

```python
# loop.py — simplified pseudocode

MAX_STEPS = 4
_ENOUGH_CHUNKS = 8

async def run_agent_loop(ctx, agent_model_name) -> list[dict]:
    messages = [SystemMessage(AGENT_SYSTEM_PROMPT), HumanMessage(question)]
    observations = []

    for step in range(MAX_STEPS):
        response = await invoke_with_tools(agent_model_name, messages, AGENT_TOOLS)

        if not response.tool_calls:      # LLM signals it's done
            break

        messages.append(response)

        for tc in response.tool_calls:
            result = await dispatch_tool(tc["name"], tc["args"], ctx)
            observations.append({"tool": tc["name"], "args": tc["args"], "result": result})
            messages.append(ToolMessage(json.dumps(result), tool_call_id=tc["id"]))

        if count_chunks(observations) >= _ENOUGH_CHUNKS:
            break                         # collected enough — stop early

    return observations
```

The agent system prompt instructs the model to:
- Call `search_books_by_summary` first when it doesn't know which books to search.
- Call `search_chunks` with the `book_ids` once books are identified.
- Call `rewrite_query` only when the question contains Uyghur pronouns.
- Stop calling tools (return a no-tool-call response) when it has enough context.
- Never hallucinate book titles or page numbers.

After the loop, `format_observations_as_context()` deduplicates chunks and formats them for `generate_answer` / `generate_answer_stream`, which are called exactly as before.

---

## Typical agent traces

### Simple factual question (2 steps)
```
User: ئابدۇرەھىم ئۆتكۈر كىم؟

Step 1 → search_books_by_summary(query="ئابدۇرەھىم ئۆتكۈر")
         → returns [book_id_A, book_id_B, book_id_C]

Step 2 → search_chunks(query="ئابدۇرەھىم ئۆتكۈر", book_ids=[A, B, C])
         → returns 12 chunks with score > 0.35

[LLM returns no tool calls → loop ends]

→ generate_answer(context from step 2)
```

### Question with low chunk count (3 steps — retry)
```
User: ئۆتكۈرنىڭ شېئىرلىرى ھەققىدە نېمە بىلىسەن؟

Step 1 → search_books_by_summary(query="ئۆتكۈرنىڭ شېئىرلىرى")
         → returns [book_id_A]

Step 2 → search_chunks(query="ئۆتكۈرنىڭ شېئىرلىرى", book_ids=[A])
         → returns 3 chunks (below _ENOUGH_CHUNKS=8)

Step 3 → search_chunks(query="ئۆتكۈر شېئىر ئەدەبىيات", book_ids=[A])
         → returns 7 more chunks

[LLM returns no tool calls → loop ends]
```

### Follow-up with pronoun (3 steps)
```
User: ئۇنىڭ تۇغۇلغان يىلى قاچان؟   (pronoun "ئۇنىڭ" refers to prior context)

Step 1 → rewrite_query(question="ئۇنىڭ تۇغۇلغان يىلى قاچان؟")
         → { rewritten_question: "ئابدۇرەھىم ئۆتكۈرنىڭ تۇغۇلغان يىلى قاچان؟" }
         → ctx.enriched_question is set

Step 2 → search_chunks(query="ئابدۇرەھىم ئۆتكۈرنىڭ تۇغۇلغان يىلى قاچان؟", book_ids=[A, B, C])
         → returns 8 chunks  [_ENOUGH_CHUNKS reached → loop ends]
```

---

## Streaming

Streaming (`handle_stream`) works identically — the agent loop runs to completion (no streaming during tool calls), then `generate_answer_stream` is called on the final accumulated context. Tool calls are typically fast (all cached), so the pre-answer delay is acceptable.

---

## Caching

All three existing cache layers are preserved and hit normally:

| Cache | Key | Where it's hit |
|-------|-----|----------------|
| Level-1: query embedding | MD5(query) | `search_chunks` and `search_books_by_summary` dispatch |
| Level-2: chunk search results | MD5(embedding + book_ids) | `search_chunks` dispatch |
| Level-3: summary search results | MD5(embedding + char_tag) | `search_books_by_summary` dispatch |

The agent loop itself is not cached. Step count (1–4) is logged per request for observability.

---

## Latency budget

| Component | Typical latency |
|-----------|-----------------|
| `search_books_by_summary` (cache hit) | ~2 ms |
| `search_books_by_summary` (cache miss: embed + query) | ~300 ms |
| `search_chunks` (cache hit) | ~2 ms |
| `search_chunks` (cache miss: pgvector) | ~50 ms |
| Agent LLM decision call (Gemini Flash, tool-use only) | ~400–700 ms |
| Final answer generation (existing, unchanged) | ~1–3 s |

Worst case (4 steps, all cache misses): ~4 × 700 ms (agent) + ~4 × 350 ms (retrieval) = ~4.2 s before answer generation begins. Cache-warm requests (typical after the first user message) add ~1.5–2 s vs the current fixed pipeline.

Use `gemini_agent_model` in `system_configs` to point at a lighter model (e.g. `gemini-2.0-flash`) for agent decision calls. Falls back to `gemini_chat_model` if unset.

---

## Files

### New (Phase 1 — complete)

```
packages/backend-core/app/services/rag/agent/
  __init__.py          # package marker
  prompts.py           # AGENT_SYSTEM_PROMPT constant
  tools.py             # @tool schemas + dispatch_tool() routing to real implementations
  loop.py              # run_agent_loop(): ReAct loop, MAX_STEPS=4, _ENOUGH_CHUNKS=8
  context_builder.py   # format_observations_as_context(): dedup + format for answer LLM
  handler.py           # AgentRAGHandler (priority=998, feature-flagged)
```

### Modified (Phase 1 — complete)

| File | Change |
|------|--------|
| `app/langchain/models.py` | Added `invoke_with_tools(model_name, messages, tools)` + fixed pre-existing missing `Optional` import |
| `app/services/rag/registry.py` | Added `AgentRAGHandler()` at priority=998 alongside `StandardRAGHandler()` at priority=999 |

### system_configs keys added

| Key | Default | Purpose |
|-----|---------|---------|
| `agentic_rag_enabled` | `"false"` | Feature flag — set to `"true"` to activate |
| `gemini_agent_model` | `"gemini-2.0-flash"` | Model for agent tool-calling decisions |

---

## QueryContext fields written by the agent

No new fields were added to `QueryContext`. The agent writes to the same fields as `StandardRAGHandler`:

| Field | Written by |
|-------|-----------|
| `ctx.query_vector` | `search_chunks` / `search_books_by_summary` dispatch (Level-1 cache) |
| `ctx.enriched_question` | `rewrite_query` dispatch |
| `ctx.used_book_ids` | accumulated from `search_chunks` results in `handler.py` |
| `ctx.retrieved_count` | total chunks across all `search_chunks` calls |
| `ctx.scores` | scores from all retrieved chunks |

---

## Implementation phases

### Phase 1 — Complete ✅
- `services/rag/agent/` package with all 6 files
- `AgentRAGHandler` registered at priority=998 (falls back to `StandardRAGHandler` when flag is off)
- `invoke_with_tools()` added to `langchain/models.py`
- SQL seed for `agentic_rag_enabled` and `gemini_agent_model` system_config keys

### Phase 2 — Evaluation + shadow mode
- Enable `agentic_rag_enabled=true` in local dev
- Compare agent traces vs StandardRAGHandler: step count, tools called, chunk counts, scores
- Write `rag_evaluations` records for both paths
- Tune agent system prompt based on observed failure patterns
- Tune `MAX_STEPS` and `_ENOUGH_CHUNKS` constants

### Phase 3 — Promote and clean up
- Enable `agentic_rag_enabled=true` in production via system config (no deploy required)
- Update `FollowUpHandler` to delegate to `AgentRAGHandler` instead of `StandardRAGHandler`
- Remove `StandardRAGHandler` from the registry after a one-week soak period
- Drop `gemini_categorization_model` and `category_chain` (no longer needed)

---

## Evaluation metrics (future — add to `rag_evaluations`)

| Metric | How to compute |
|--------|---------------|
| `agent_steps` | number of LLM calls in the loop |
| `tools_called` | JSON array of tool names in order |
| `retry_count` | number of times `search_chunks` was called |
| `final_chunk_count` | total unique chunks passed to answer generation |
| `min_score` / `max_score` | score range across all retrieved chunks |

These extend the existing `rag_evaluations` table (new nullable columns via migration in Phase 2).

---

## Risks and mitigations

| Risk | Mitigation |
|------|-----------|
| Agent calls tools in a loop without making progress | `MAX_STEPS=4` hard cap; `_ENOUGH_CHUNKS=8` early-exit |
| Agent hallucinates a book title in `find_books_by_title` | Tool always looks up titles from DB — any unmatched title returns empty list |
| Gemini Flash makes poor tool-selection decisions | Falls back to `gemini_chat_model` if `gemini_agent_model` is unset |
| Streaming delay increases noticeably | Measure in Phase 2; if >2 s added latency, restrict agent to global mode only |
| `rewrite_query` called unnecessarily | Agent prompt: call only when question contains explicit Uyghur pronouns |
| `FollowUpHandler` bypasses agent (hardcodes `StandardRAGHandler`) | Acceptable in Phase 1; fixed in Phase 3 cleanup |
