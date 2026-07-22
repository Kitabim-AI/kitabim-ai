# LLM-Routed RAG — Google ADK Implementation

This document describes the design and execution flow of `LLMRoutedRAGHandler`, one of two RAG query handlers in the system. It is powered by the **Google ADK** framework (`google.adk`) and the **google-genai** SDK.

Both RAG handlers run on Google ADK — `DeterministicRAGHandler` executes a fixed Python decision tree through an ADK `Workflow`/`Runner` (see `RAG_DETERMINISTIC_ROUTER_DESIGN.md`), while `LLMRoutedRAGHandler` (this document) lets an LLM freely decide tool call order via an ADK ReAct agent loop. ADK usage itself does not distinguish the two handlers; the distinction is LLM-driven tool selection vs. fixed Python precedence.

---

## Overview

`packages/backend-core/app/services/rag/agent/llm_routed_handler.py` implements `LLMRoutedRAGHandler`. Its `can_handle()` always returns `True`, so `HandlerRegistry` (`packages/backend-core/app/services/rag/registry.py`) uses it as the fallback whenever `DeterministicRAGHandler.can_handle()` returns `False` — i.e. whenever the `use_deterministic_router` system config is `false`. That config defaults to `false`, so `LLMRoutedRAGHandler` is the default active handler for all chat traffic unless an administrator opts a deployment into the deterministic router.

The assistant is built as a stateless Google ADK `Agent`, run via `InMemoryRunner` for each chat request. The workflow is split into:
1. **Pre-processing steps**: query decomposition (LLM-based question splitting) and lightweight intent detection for the initial `planning` UI event.
2. **Core Agent Loop**: an ADK-driven ReAct loop managing multi-step reasoning and automated tool execution, governed by `AGENT_SYSTEM_PROMPT` (`prompts.py`).
3. **Post-processing steps**: context construction, relative-score grading, and streaming answer synthesis.

---

## Agent Tool Set (19 Tools)

Registered in `adk_agent.py::build_rag_agent()`. All tool functions live in `tools.py` and dispatch through `_execute_and_record_tool`, which appends every call to `tool_context.state["observations"]`.

### Content Retrieval

| Tool | Wraps | Cache | Description |
|------|-------|-------|-------------|
| `search_chunks` | `ChunksRepository.similarity_search` (pgvector) | L1 (embed) + L2 (results) | Vector-search passages; primary retrieval tool. |
| `search_books_by_summary` | `BookSummariesRepository` summary vector search | none (see caching note below) | Find which books cover a topic when book scope is unknown. |
| `find_books_by_title` | `BooksRepository` title match | — | Resolve a book title mentioned in the question to internal book IDs. Includes a false-positive guard for lone single-word matches and a fuzzy-keyword fallback when strict matching finds nothing — see "Retrieval Refinements" in `RAG_DETERMINISTIC_ROUTER_DESIGN.md`. |
| `get_book_summary` | `BookSummariesRepository` | — | Fetch full semantic summary text for specific books (plot/character/theme queries). |
| `get_current_page` | `PagesRepository` | — | Raw text of the page currently open in the reader (callable only in single-book reader mode). |
| `get_sister_volumes` | `BooksRepository.find_sister_volumes` | — | Retrieves other volumes of the same series as a given `book_id`. |
| `rewrite_query` | `QueryRewriter` | L0 | Resolves co-references and pronouns using conversation history. |

### Catalog & Metadata

| Tool | Wraps | Description |
|------|-------|-------------|
| `get_book_author` | `BooksRepository` title→author match | Author lookup for "who wrote X?" questions. |
| `get_books_by_author` | `BooksRepository` author match | Book list for "what did Y write?" questions. |
| `search_catalog` | Catalog query helpers | Library browsing and general listing queries. |

### Dictionary & Language (8 tools)

| Tool | Description |
|------|-------------|
| `lookup_uyghur_word` | Uyghur word definition lookup. |
| `lookup_history_term` | Historical term/person/event/place lookup. |
| `translate_english_to_uyghur` | English → Uyghur translation. |
| `check_word_spelling` | Uyghur spelling validity check. |
| `lookup_uyghur_name` | Uyghur person-name lookup (meaning, or listing by starting letter). |
| `search_language_sources` | Fallback dictionary search when the source type is unclear. |
| `lookup_proverbs` | Uyghur proverb/saying lookup. |
| `lookup_synonyms` | Synonym-dictionary lookup. |

### Quran

| Tool | Description |
|------|-------------|
| `search_quran` | Surah/ayah lookup or free-text search within the Quran (a source separate from the book library). Also returns Surah metadata (total ayah count, Uyghur/Arabic/English surah names) for every surah touched by the results, prepended to the tool's context output. |

### Tool Execution Context
Each tool function retrieves the active `QueryContext` from `tool_context.state["query_context"]`. Results of tool executions are appended to `tool_context.state["observations"]` to enable downstream context aggregation and grading.

---

## Agent Execution Workflow

```
[User Question]
       │
       ▼
 ┌───────────┐
 │ Pre-Agent │ (Intent Detection & Query Decomposition)
 └─────┬─────┘
       │
       ▼
 ┌───────────┐
 │ ADK Agent │ (ReAct Reasoning Loop; InMemoryRunner)
 └─────┬─────┘
       │   ├────► Call Tools (19 available)
       │   ◄────┤ Return Observations (search results, catalog/dictionary data)
       ▼
 ┌───────────┐
 │Post-Agent │ (Extract Book IDs, Context Grading, Answer Synthesis)
 └─────┬─────┘
       │
       ▼
[Streamed Answer with Citations]
```

### 1. Pre-Processing Pipeline
- **Intent Detection**: A fast heuristic (`_detect_intent`) classifies the question as `current_page` (if a page-query pattern matches while in-reader) or `content_search` — used only for the `planning` UI event, not to constrain the agent's own tool choice.
- **Query Decomposition**: If the question contains more than one `?`/`؟`, or matches a comparison-pattern regex (multiple entities being compared), an LLM call (`_llm_split`) splits it into up to 4 self-contained sub-questions, appended to the prompt as a `[Sub-questions]` block.
- **Context Injection**: `_build_human_message` prepends a `[Context]` block to the user message containing current book metadata, current page, prior-turn book IDs, category filters, and whether chat history is available.

### 2. Google ADK Agent Execution
- Instantiates a stateless Google ADK `Agent` with `AGENT_SYSTEM_PROMPT` and the 19 registered tools, `temperature=0.0`.
- Executes the query using `InMemoryRunner.run_async()`.
- Captures and yields `tool_call` and `agent_thinking` events directly from the runner's async event stream to drive real-time UI animation.
- Gathers tool output data into an inline list of observations (read from the event stream itself, not from `session.state`, since `InMemoryRunner` does not reliably persist state across the run).

### 3. Post-Processing Pipeline
- **Deduplication & book-ID extraction**: `_extract_used_book_ids` pulls book IDs out of `search_chunks` and `get_book_summary` observations.
- **Context Grading** (`_grade_context`): for each `search_chunks` call, finds its highest similarity score and keeps chunks scoring at or above `top_score × GRADE_RELATIVE_THRESHOLD` (0.85), falling back to at least `MIN_CHUNKS_AFTER_GRADING` (3) chunks if the filter is too aggressive. Chunks are deduplicated by `(book_id, page)` across all search calls, globally re-sorted by score, and capped at `AGENT_MAX_CONTEXT_CHUNKS` (25).
- **Answer Synthesis**: streams the final answer via `generate_answer_stream` using the graded context. If the query was split into sub-questions, the synthesis prompt directs the model to address each one.
- **Telemetry**: records tool list, step count, chunk counts, and score ranges to the `rag_evaluations` table via `_populate_ctx_from_observations`.

---

## Streaming Events (SSE)

Events flow from the handler to the `/api/chat/stream` endpoint, translating ADK runner events and post-processing steps into frontend-compatible events.

| Event `type` | Payload | Triggered When |
|---|---|---|
| `planning` | `{"type": "planning", "intent": str}` | Pre-processing begins; intent is identified |
| `decompose` | `{"type": "decompose", "count": int}` | Multiple questions are detected and split |
| `agent_thinking` | `{"type": "agent_thinking", "text": str}` | Agent is reasoning |
| `tool_call` | `{"type": "tool_call", "tool": str}` | Agent decides to invoke a tool |
| `tool_result` | `{"type": "tool_result", "tool": str, "found": int}` | Tool execution completes; returns records found |
| `grading` | `{"type": "grading", "before": int, "after": int}` | Chunks are filtered by score before synthesis |
| `answer_start` | `{"type": "answer_start"}` | Answer synthesis begins |
| `chunk` | `{"type": "chunk", "text": str}` | A single token of the streaming answer is yielded |
| `answer_end` | `{"type": "answer_end"}` | Answer stream terminates |
| `done` | `{"done": true, "contextBookIds": [...]}` | Completes the connection, returning used book IDs |

---

## Caching (3 Active Levels)

All caching leverages Redis to avoid redundant LLM and database queries:

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool | Deduplicate pronoun and follow-up query rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embedding call in query | Reuse query embeddings across multiple tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Cache pgvector similarity search results |

`KEY_RAG_SUMMARY_SEARCH` (an "L3" cache key) is defined in `cache_config.py` but currently unused — `BookSummariesRepository.summary_search()` (backing `search_books_by_summary`) does not read or write it, so summary searches are not cached.

---

## Model Configuration

`ctx.agent_model` is resolved per-request in `rag_service.py::_build_context()` from the `gemini_agent_loop_model` system config, falling back to `gemini_chat_model` if unset (it is unset by default, so the agent loop currently runs on the same model as chat answer generation — `gemini-3.1-flash-lite` by default). Both are DB-driven via `SystemConfigsRepository`, hot-reloadable without a deploy.

The `agent_max_steps` (default 6) and `agent_enough_chunks` (default 8) system configs are also read into `QueryContext` per request, but are currently **not consumed** anywhere in the ReAct loop or its tools — they are dead config as of this writing. The actual step limit is a hardcoded instruction baked into `AGENT_SYSTEM_PROMPT` (`prompts.py`'s `_HARD_LIMITS`): "at most 6 tool calls total (10 with `[Sub-questions]`)" — a soft, LLM-followed limit, not a Python-enforced one.

---

## Typical Agent Trace (Global Query Example)

```
User: ئابدۇرەھىم ئۆتكۈر كىم؟
--------------------------------------------------------------------------------
1. Pre-Processing:
   - Intent detected: content_search
   - Question marks: 1 (no decomposition needed)
   - Injects previous conversation book IDs if present

2. ADK Agent Loop:
   - Step 1: Calls search_books_by_summary(query="ئابدۇرەھىم ئۆتكۈر") -> returns [book_id_A, book_id_B]
   - Step 2: Calls search_chunks(query="ئابدۇرەھىم ئۆتكۈر", book_ids=[A, B]) -> returns 10 passages
   - Loop terminates (observations collected)

3. Post-Processing:
   - Deduplicates 10 passages
   - Grades chunks: 10 retrieved -> 7 pass relative threshold
   - Synthesizes answer using the 7 graded chunks
   - Streams answer with citations, writes metadata log
```
