# Agentic RAG — Current Implementation

**Status:** Fully implemented and running in production. All three original phases are complete.

See [QUESTION_ANSWERING_DIAGRAM_V2.md](QUESTION_ANSWERING_DIAGRAM_V2.md) for the visual pipeline diagram.

---

## Overview

The RAG pipeline uses an LLM-driven agent loop (`AgentRAGHandler`, priority=998) as the sole fallback handler for all questions not caught by a fast-path handler. The agent decides which retrieval tools to call, retries with refined queries when results are thin, and stops when it has sufficient context.

The old `StandardRAGHandler` fixed decision tree has been removed from the registry. There is no feature flag — the agent is always-on.

---

## Handler registry (ordered by priority)

| Handler | Priority | Behaviour |
|---------|----------|-----------|
| `IdentityHandler` | 1 | Greetings and identity questions — direct reply, no retrieval |
| `CapabilityHandler` | 2 | "What can you do?" questions — direct reply |
| `AuthorByTitleHandler` | 20 | "Who wrote X?" — DB lookup, direct reply; falls back to agent on miss |
| `BooksByAuthorHandler` | 21 | "What did Y write?" — DB lookup, direct reply; falls back to agent on miss |
| `VolumeInfoHandler` | 22 | Volume/page count questions — DB lookup, direct reply |
| `FollowUpHandler` | 30 | Detects follow-up signals; rewrites question; delegates to agent |
| `CurrentPageHandler` | 40 | In-reader current-page questions — injects page text as context |
| `CurrentVolumeHandler` | 41 | In-reader volume-scoped questions — sets scope flag; delegates to agent |
| `AgentRAGHandler` | 998 | All other questions — runs the ReAct loop |

---

## FollowUpHandler — detection heuristics

`FollowUpHandler.can_handle()` returns `True` when the question has prior history **and** any of:

1. **Explicit follow-up phrase** — one of ~30 markers in `_FOLLOWUP_MARKERS` (e.g. "يەنە", "داۋاملاشتۇر", "بۇ كىتابنىڭ", "ئۇ ئاپتور")
2. **Referential pronoun** — any standalone word in `_REFERENTIAL_PRONOUNS` (ئۇ، بۇ، شۇ and their suffixed forms)
3. **"چۇ" topic-shift clitic** — any word in the question ends with "چۇ" (e.g. "يىگانە ئارالنىڭچۇ؟" = "What about Yegane Aral?")

When triggered, `QueryRewriter` LLM-rewrites the question into a standalone query, sets `ctx.enriched_question`, and delegates to `AgentRAGHandler`.

---

## Agent tool set (7 tools)

### Content retrieval

| Tool | Wraps | Cache | Description |
|------|-------|-------|-------------|
| `search_chunks` | `ChunksRepository.similarity_search` | L1 (embed) + L2 (results) | Vector-search passages; primary retrieval tool |
| `search_books_by_summary` | `BookSummariesRepository.summary_search` | L3 | Find which books cover a topic when book scope is unknown |
| `find_books_by_title` | `BooksRepository` title match | — | Resolve a book title mentioned in the question to book IDs |
| `rewrite_query` | `QueryRewriter.rewrite` | L0 | Resolve co-references; short-circuits if `ctx.enriched_question` already set by `FollowUpHandler` |

### Catalog & metadata

| Tool | Wraps | Description |
|------|-------|-------------|
| `get_book_author` | `BooksRepository.find_author_by_title_in_question` | Author lookup for compound queries; fast-path handler handles the simple "who wrote X?" case |
| `get_books_by_author` | `BooksRepository.find_books_by_author_in_question` | Book list for compound queries; fast-path handler handles the simple case |
| `search_catalog` | `CatalogHandler._build_catalog_context` | Library browsing and general catalog questions |

Metadata tools return a `"context"` key that `format_observations_as_context` prepends before chunk passages in the final context string.

---

## Agent loop

```python
# loop.py — simplified pseudocode

MAX_STEPS = 4
_ENOUGH_CHUNKS = 8   # early-exit threshold (not a cap — see MAX_CONTEXT_CHUNKS below)

async def run_agent_loop(ctx, agent_model_name) -> list[dict]:
    question = ctx.enriched_question or ctx.question
    messages = [
        SystemMessage(AGENT_SYSTEM_PROMPT),
        HumanMessage(_build_human_message(ctx, question)),  # injects [Context] block
    ]
    observations = []

    for step in range(MAX_STEPS):
        response = await invoke_with_tools(agent_model_name, messages, AGENT_TOOLS)

        if not response.tool_calls:   # LLM signals it has enough context
            break

        messages.append(response)
        results = await asyncio.gather(*[dispatch_tool(tc, ctx) for tc in response.tool_calls])

        for tc, result in zip(response.tool_calls, results):
            observations.append({"tool": tc["name"], "args": tc["args"], "result": result})
            messages.append(ToolMessage(json.dumps(result), tool_call_id=tc["id"]))

        if count_chunks(observations) >= _ENOUGH_CHUNKS:
            break   # collected enough — stop early

    return observations
```

### Context injection — `_build_human_message`

Before the first LLM call, the agent's HumanMessage is enriched with a `[Context]` block:

- **Single-book mode** (`is_global=False`): injects current book title, author, volume, and `book_id`. Agent calls `search_chunks` directly with that `book_id`, skipping `find_books_by_title` entirely.
- **Global mode** (`is_global=True`): injects `context_book_ids` (up to 10, frontend-tracked from prior turns) and `character_categories`. Agent tries `search_chunks` with those IDs before falling back to `search_books_by_summary`.
- When nothing useful is available, returns the bare question — no overhead.

### Context builder — `format_observations_as_context`

After the loop:
1. Collect `"context"` strings from any metadata tool result (catalog, author — in call order).
2. Collect all chunks from `search_chunks` results; deduplicate by `(book_id, page)`; sort by score DESC; cap at `MAX_CONTEXT_CHUNKS = 15`.
3. Return: metadata context prepended before chunk passages.

---

## Agent system prompt strategy

```
1. Rewrite first (if pronouns or "چۇ" particle and history exists) → rewrite_query
2. Metadata questions:
   - "who wrote X?" → get_book_author
   - "what did Y write?" → get_books_by_author
   - library browsing → search_catalog
3. Content questions:
   a. [Context] has book_id? → search_chunks directly (skip book discovery)
   b. [Context] has context book IDs? → search_chunks with those first
   c. No context IDs: question names a title? → find_books_by_title
      else → search_books_by_summary → search_chunks
   d. < 4 chunks? → retry once with rephrased query or broader scope
4. Stop when 6–12 passages collected (or catalog/author result for metadata)
Hard limit: 4 tool calls total.
```

---

## Caching (4 levels)

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `QueryRewriter` (via `FollowUpHandler` or `rewrite_query` tool) | Deduplicate follow-up rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embed call per query | Reuse embeddings across all tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Reuse pgvector search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Reuse book-selection results |

---

## Typical agent traces

### Single-book question (1 step — context injection eliminates discovery)
```
User: بابۇرنامىدە ئاغرا شەھىرى توغرىسىدا نېمە دېيىلگەن؟
[Context] Current book: "بابۇرنامە" (book_id: abc123)

Step 1 → search_chunks(query="بابۇرنامىدە ئاغرا شەھىرى", book_ids=["abc123"])
         → returns 10 chunks  [_ENOUGH_CHUNKS reached → loop ends]

→ generate_answer(10 chunks)
```

### Global question — topic unknown (2 steps)
```
User: ئابدۇرەھىم ئۆتكۈر كىم؟

Step 1 → search_books_by_summary(query="ئابدۇرەھىم ئۆتكۈر")
         → [book_id_A, book_id_B, book_id_C]

Step 2 → search_chunks(query="ئابدۇرەھىم ئۆتكۈر", book_ids=[A, B, C])
         → 12 chunks  [loop ends]

→ generate_answer(12 chunks)
```

### "چۇ" follow-up — pre-rewritten by FollowUpHandler (2 steps)
```
Prior turn: user asked about "بابۇرنامە"
User: يىگانە ئارالنىڭچۇ؟

FollowUpHandler detects "چۇ" clitic → QueryRewriter rewrites →
ctx.enriched_question = "يىگانە ئارال ھەققىدە بابۇرنامىدە نېمە دېيىلگەن؟"

Agent receives [Context] + enriched question

Step 1 → search_chunks(query="يىگانە ئارال", book_ids=["abc123"])
         → 8 chunks  [_ENOUGH_CHUNKS → loop ends]

→ generate_answer(8 chunks)
```

### Retry on thin results (3 steps)
```
User: ئۆتكۈرنىڭ شېئىرلىرى ھەققىدە نېمە بىلىسەن؟

Step 1 → search_books_by_summary(query="ئۆتكۈر شېئىر") → [book_id_A]

Step 2 → search_chunks(query="ئۆتكۈرنىڭ شېئىرلىرى", book_ids=[A])
         → 3 chunks (below _ENOUGH_CHUNKS)

Step 3 → search_chunks(query="ئۆتكۈر شېئىر ئەدەبىيات", book_ids=[A])
         → 7 chunks

[LLM returns no tool calls → loop ends]
```

---

## Latency budget

| Component | Typical latency |
|-----------|-----------------|
| Context injection (`_build_human_message`) | <1 ms |
| `rewrite_query` (L0 cache hit) | ~2 ms |
| `search_books_by_summary` (L3 cache hit) | ~2 ms |
| `search_books_by_summary` (cache miss: embed + query) | ~300 ms |
| `search_chunks` (L2 cache hit) | ~2 ms |
| `search_chunks` (cache miss: embed + pgvector) | ~50 ms |
| Agent LLM decision call (Gemini Flash, tool-use only) | ~400–700 ms |
| Final answer generation | ~1–3 s |

Best case (single-book, context injected, L2 hit): 1 agent call (~500 ms) + answer (~2 s) ≈ **2.5 s**.  
Worst case (4 steps, all cache misses): ~4 × 700 ms + ~4 × 350 ms = ~4.2 s before answer generation.

---

## Files

```
packages/backend-core/app/services/rag/agent/
  __init__.py          # package marker
  prompts.py           # AGENT_SYSTEM_PROMPT — retrieval strategy instructions
  tools.py             # @tool schemas + dispatch_tool() — 7 tools
  loop.py              # run_agent_loop(), _build_human_message(), MAX_STEPS=4, _ENOUGH_CHUNKS=8
  context_builder.py   # format_observations_as_context(), MAX_CONTEXT_CHUNKS=15
  handler.py           # AgentRAGHandler — priority=998
```

Supporting files:
- `app/services/rag/handlers/follow_up.py` — heuristic detection + pre-rewrite before agent
- `app/services/rag/query_rewriter.py` — LLM rewrite with L0 caching
- `app/langchain/models.py` — `invoke_with_tools()` using shared rate limiter + circuit breaker

---

## QueryContext fields written by the agent

| Field | Written by |
|-------|-----------|
| `ctx.query_vector` | `search_chunks` / `search_books_by_summary` (L1 cache side-effect) |
| `ctx.enriched_question` | `FollowUpHandler` (pre-agent) or `rewrite_query` tool |
| `ctx.used_book_ids` | accumulated from `search_chunks` results in `handler.py` |
| `ctx.retrieved_count` | total chunks across all `search_chunks` calls |
| `ctx.scores` | scores from all retrieved chunks |
| `ctx.agent_steps` | LLM call count from `run_agent_loop` |
| `ctx.agent_tools_called` | ordered list of tool names from observations |
| `ctx.agent_retry_count` | number of `search_chunks` invocations |
| `ctx.agent_final_chunk_count` | unique chunks after dedup in context builder |

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

This affects `get_book_author`, `get_books_by_author`, `find_books_by_title`, `search_catalog`, and `VolumeInfoHandler`.
