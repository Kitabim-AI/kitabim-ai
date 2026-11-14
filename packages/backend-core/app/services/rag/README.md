# Retrieval-Augmented Generation (`app/services/rag`)

## Overview
Coordinates retrieval-augmented generation (RAG) across books and reference lexicons, encompassing vector search, intent detection, query rewriting, answer generation, evaluation judging, and table-of-contents lookups.

## Interface
- `[answer_builder.py:Document]` — Data container for retrieved text chunks with book title, author, volume, and page metadata.
- `[answer_builder.py:generate_answer]` / `[answer_builder.py:generate_answer_stream]` — Generates synchronous or streaming grounded answers from context documents.
- `[answer_builder.py:categorize_question]` — Categorizes question intent into broad domain buckets.
- `[context.py:QueryContext]` — Scoped context tracking query parameters, active book, and session boundaries.
- `[judge.py:JudgeScores]` — Dataclass storing evaluation metrics (`faithfulness`, `answer_relevance`, `context_precision`).
- `[judge.py:score_answer]` — Evaluates RAG answer quality against retrieved context and original question.
- `[phrase_intent.py:PhraseIntent]` / `[phrase_intent.py:detect_phrase_intent]` — Detects exact phrase quote lookup intent.
- `[short_work_intent.py:ShortWorkIntent]` / `[short_work_intent.py:detect_short_work_intent]` — Detects intent to locate short stories, poems, or articles within collections.
- `[toc_lookup_service.py:resolve_short_work]` — Resolves short work titles via `book_sections` (with fallback to `toc_pages`), performing intra-page `[start_block_index .. end_block_index]` slicing, author/book disambiguation, and returning `other_matches` and printed-page spans.
- `[query_rewriter.py:QueryRewriter]` — Reformulates conversational questions into standalone search queries using dialogue history.
- `[retrieval.py:vector_search]` / `[retrieval.py:exact_phrase_chunk_search]` — Vector and exact phrase search primitives over book chunks (supporting optional `section_ids` and section/printed-page metadata).
- `[retrieval.py:select_balanced_chunks]` — Selects a balanced distribution of chunks across sister volumes and chapters.
- `[llm_resources.py:LLMResources]` — Shared singleton pooling Gemini clients, embedding models, and rerankers.
- `[utils.py:normalize_uyghur]` / `[utils.py:normalize_uyghur_spelling]` — Normalization utilities for Uyghur Arabic text and diacritics.
- [Agent Subsystem](./agent/README.md) — Agentic retrieval loop, tools, and rerankers.
- [Domain Handlers](./handlers/README.md) — Specialized query handlers (catalog lookups).

## Invariants
- `[answer_builder.py:generate_answer]` — Enforces strict grounding: instructions prohibit hallucinating facts outside provided context documents.
- `[judge.py:JudgeScores]` — All automated evaluation scores (`faithfulness`, `relevance`, `precision`) are clamped to the range `[0.0, 1.0]`.
- `[utils.py:normalize_uyghur]` — Deterministically replaces variant Arabic/Uyghur character forms and strips unwanted punctuation.

## Side Effects
- Calls Google Gemini API for answer synthesis, streaming, and evaluation scoring.
- Queries PostgreSQL database tables for chunks, books, and page records.

## Verification
- Run: `pytest packages/backend-core/tests`
