# Agentic RAG — Google ADK Implementation

This document describes the design and execution flow of the agentic Retrieval-Augmented Generation (RAG) assistant, powered by the **Google ADK** framework and the **google-genai** SDK.

---

## Overview

The query assistant uses an agentic RAG loop (`AgentRAGHandler`, priority=998) as the fallback handler for all content questions when the deterministic router is disabled. The assistant is built using a stateless Google ADK `Agent` run via `InMemoryRunner` for each chat request. 

Instead of embedding the entire pipeline inside a complex state graph, the workflow is split into:
1. **Pre-processing steps**: Intent detection and query decomposition (LLM-based question splitting).
2. **Core Agent Loop**: Google ADK-driven ReAct loop managing multi-step reasoning and automated tool execution.
3. **Post-processing steps**: Context construction, relative score grading, and streaming answer synthesis.

---

## Handler Registry

| Handler | Priority | Behavior |
|---------|----------|-----------|
| `AgentRAGHandler` | 998 | Fallback handler — runs if `use_deterministic_router` is set to False |

---

## Agent Tool Set (16 Tools)

### Content Retrieval

| Tool | Wraps | Cache | Description |
|------|-------|-------|-------------|
| `search_chunks` | `ChunksRepository.similarity_search` | L1 (embed) + L2 (results) | Vector-search passages; primary retrieval tool. |
| `search_books_by_summary` | `BookSummariesRepository.summary_search` | L3 | Find which books cover a topic when book scope is unknown. |
| `find_books_by_title` | `BooksRepository` title match | — | Resolve a book title mentioned in the question to internal book IDs. |
| `get_book_summary` | `BookSummariesRepository.get_summaries_for_books` | — | Fetch full semantic summary text for specific books (used for plot/character/theme queries). |
| `get_current_page` | `PagesRepository.find_one` | — | Raw text of the page currently open in the reader (callable only in single-book reader mode). |
| `get_sister_volumes` | `BooksRepository.find_sister_volumes` | — | Retrieves other volumes of the same series as a given `book_id`. |
| `rewrite_query` | `QueryRewriter.rewrite` | L0 | Resolves co-references and pronouns using conversation history. |
| `query_knowledge_graph` | `GraphRepository.query_subgraph` | — | GraphRAG tool: queries Neo4j to retrieve a 1-hop subgraph of entities and their relationships. |

### Catalog & Metadata

| Tool | Wraps | Description |
|------|-------|-------------|
| `get_book_author` | `BooksRepository.find_author_by_title_in_question` | Author lookup for "who wrote X?" questions. |
| `get_books_by_author` | `BooksRepository.find_books_by_author_in_question` | Book list for "what did Y write?" questions. |
| `search_catalog` | `CatalogHandler._build_catalog_context` | Library browsing and general listing queries. |

### Dictionary & Translation

| Tool | Wraps | Description |
|------|-------|-------------|
| `lookup_uyghur_word` | `DictionaryRepository.lookup_uyghur_definition` | Lookup definitions for Uyghur words. |
| `lookup_history_term` | `DictionaryRepository.lookup_history_term` | Lookup definition for a historical term, person, event, or concept. |
| `translate_english_to_uyghur` | `DictionaryRepository.translate_english_to_uyghur` | Translate English word/phrase to Uyghur. |
| `check_word_spelling` | `DictionaryRepository.check_word_spelling` | Validate word spelling and suggest corrections. |
| `search_language_sources` | `DictionaryRepository.search_language_sources` | Fallback search across all language/dictionary sources. |

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
        │   ├────► Call Tools (16 available)
        │   ◄────┤ Return Observations (search results, subgraphs, dictionary context)
        ▼
  ┌───────────┐
  │Post-Agent │ (Extract Book IDs, Context Grading, Answer Synthesis)
  └─────┬─────┘
        │
        ▼
[Streamed Answer with Citations]
```

### 1. Pre-Processing Pipeline
- **Intent Detection**: Classifies the question scope (current page, library catalog, or general content search) using fast heuristic patterns.
- **Query Decomposition**: Checks if the query compares multiple entities or contains multiple question marks. If so, it uses a cheap Gemini Flash model call to split the query into up to 4 self-contained sub-questions and appends them to the prompt.
- **Context Injection**: Pre-injects a `[Context]` block into the user message containing current book metadata, open pages, conversation history, and category filters.

### 2. Google ADK Agent Execution
- Instantiates a stateless Google ADK `Agent` with `AGENT_SYSTEM_PROMPT` and the 16 registered tools.
- Executes the query using `InMemoryRunner.run_async()`.
- Captures and yields `tool_call` and `agent_thinking` events directly from the runner's async event stream to provide real-time UI animation triggers.
- Gathers tool output data into an inline list of observations.

### 3. Post-Processing Pipeline
- **Deduplication**: Extracts passages from `search_chunks` and `get_book_summary` observations, deduplicating them by `(book_id, page)`.
- **Context Grading**: Evaluates the retrieved passages using a relative-score threshold:
  - Finds the highest similarity score.
  - Filters out chunks scoring below `highest_score * GRADE_RELATIVE_THRESHOLD` (default 85%).
  - Falls back to `MIN_CHUNKS_AFTER_GRADING` if too few survive.
  - Caps the final context at `AGENT_MAX_CONTEXT_CHUNKS` (default 10).
- **Answer Synthesis**: Streams the final answer utilizing the graded context. If the query was split into sub-questions, the synthesis prompt directs the model to format answers for each sub-question.
- **Telemetry**: Records details (tool list, steps, chunk count, score ranges, and user feedback markers) to the `rag_evaluations` table.

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

## Caching (4 Levels)

All caching leverages Redis to avoid redundant LLM and database queries:

| Level | Key | Populated By | Purpose |
|-------|-----|-------------|---------|
| **L0** | `KEY_RAG_REWRITE` | `rewrite_query` tool | Deduplicate pronoun and follow-up query rewrites |
| **L1** | `KEY_RAG_EMBEDDING` | First embedding call in query | Reuse query embeddings across multiple tools |
| **L2** | `KEY_RAG_SEARCH_SINGLE/MULTI` | `search_chunks` tool | Cache pgvector similarity search results |
| **L3** | `KEY_RAG_SUMMARY_SEARCH` | `search_books_by_summary` tool | Cache summary search results for topic discovery |

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

---

## Latency Budget

- **Intent & Preprocessing**: ~1–5 ms (heuristic-based).
- **Query Decomposition (LLM)**: ~400–700 ms (only for compound/multi-question queries).
- **Cache Hits (L0-L3)**: ~2 ms per lookup.
- **Cache Miss (Embedding + Search)**: ~350 ms.
- **Agent Reasoning Step (Gemini Flash)**: ~400–700 ms per step.
- **Context Grading**: ~5 ms (heuristic-based).
- **Answer Generation (Streaming)**: ~1–3 seconds (first token at ~300ms).

Best-case RAG query latency sits at **~2.5 seconds** (including streaming start), while worst-case multi-step executions run **~6–8 seconds**.
