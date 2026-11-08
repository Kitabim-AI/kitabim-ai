# RAG Retrieval Agent (`app/services/rag/agent`)

## Overview
Implements the multi-tool agentic retrieval engine, configuring tool definitions, system prompts, retrieval constraints, and context reranking for semantic document exploration.

## Interface
- `[config.py:AGENT_MAX_STEPS]` — Maximum tool execution iterations permitted per agentic run.
- `[config.py:AGENT_ENOUGH_CHUNKS]` / `[config.py:AGENT_MAX_CONTEXT_CHUNKS]` — Thresholds bounding chunk collection size.
- `[prompts.py:build_agent_system_prompt]` — Generates the system prompt guiding the retrieval agent's decision logic and tool usage.
- `[reranker.py:rerank_context]` — `rerank_context(...)`: Pools, deduplicates, and reorders candidate context chunks based on relevance scores.
- `[reranker.py:is_better_duplicate]` — Compares duplicate chunks to retain the highest-quality candidate.
- `[tools.py:search_chunks]` — Semantic vector search tool over document text chunks.
- `[tools.py:search_keyword_phrase]` — Keyword and exact phrase search tool.
- `[tools.py:search_books_by_summary]` — Searches book summaries for thematic relevance.
- `[tools.py:find_books_by_title]` / `[tools.py:get_books_by_author]` — Catalog search tools by title and author.
- `[tools.py:get_sister_volumes]` — Retrieves multi-volume series relations for a book.
- `[tools.py:get_current_page]` — Retrieves active page text for context in reading mode.
- `[tools.py:lookup_uyghur_word]` / `[tools.py:lookup_history_term]` — Uyghur lexicon and historical encyclopedia lookup tools.
- `[tools.py:search_quran]` — Quranic verse and translation search tool.
- `[tools.py:lookup_proverbs]` / `[tools.py:lookup_synonyms]` — Folk wisdom and synonym lookup tools.

## Invariants
- `[config.py:AGENT_MAX_STEPS]` — Prevents unbounded agent reasoning cycles by hard-capping maximum tool calls.
- `[tools.py:_clamp_reader_scope]` — Enforces book scope boundaries when querying within single-book reader mode.
- `[reranker.py:rerank_context]` — Deduplicates overlapping chunks across the same book and page offsets.

## Side Effects
- Reads chunks, books, pages, dictionaries, and Quran records from PostgreSQL.
- Calls Gemini embeddings API for semantic query representation.

## Verification
- Run: `pytest packages/backend-core/tests`
