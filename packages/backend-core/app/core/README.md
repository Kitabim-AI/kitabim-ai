# Core Configuration & Utilities (`app/core`)

## Overview
Houses system-wide configuration, environment settings, pipeline lifecycle definitions, cache keys and TTLs, internationalization, character personas, system prompts, and abstract service protocols.

## Interface
- `[config.py:Settings]` — `class Settings(BaseSettings)`: Application configuration loaded from environment variables (PostgreSQL, Redis, GCS, Gemini, JWT auth).
- `[config.py:settings]` — Global singleton instance of `Settings`.
- `[cache_config.py:TTL_BOOKS]` — Time-to-live constants for caching (`TTL_BOOKS`, `TTL_SYSTEM_CONFIG`, `TTL_CATEGORIES`, `TTL_RAG_QUERY`, `TTL_USER_PROFILE`, `TTL_STATS`, `TTL_SUMMARY_SEARCH`, `TTL_OCR_FREQUENT_CORRECTIONS`).
- `[cache_config.py:KEY_BOOK]` — Redis cache key prefix constants (`KEY_BOOK`, `KEY_BOOKS_LIST`, `KEY_CATEGORY`, `KEY_USER`, `KEY_RAG_EMBEDDING`, `KEY_RAG_SEARCH_SINGLE`, `KEY_RAG_SEARCH_MULTI`, `KEY_RAG_SUMMARY_SEARCH`, `KEY_RAG_WORD_BOOK_COUNT`, `KEY_RAG_BOOKS_WITH_TEXT`, `KEY_PROVERB`, `KEY_STATS`, `KEY_CONFIG`, `KEY_CHAT_USAGE`, `KEY_RAG_REWRITE`, `KEY_OCR_FREQUENT_CORRECTIONS`, `KEY_GRAPH_ALIAS_LOOKUP`).
- `[pipeline.py:PIPELINE_STEP_OCR]` — Pipeline step constants (`PIPELINE_STEP_OCR`, `PIPELINE_STEP_CHUNKING`, `PIPELINE_STEP_EMBEDDING`, `PIPELINE_STEP_SPELL_CHECK`, `PIPELINE_STEP_SUMMARY`).
- `[pipeline.py:PIPELINE_ORDER]` — Ordered tuple defining book ingestion pipeline execution order.
- `[pipeline.py:PAGE_MILESTONE_IDLE]` — Page-level milestone status constants (`PAGE_MILESTONE_IDLE`, `PAGE_MILESTONE_IN_PROGRESS`, `PAGE_MILESTONE_SUCCEEDED`, `PAGE_MILESTONE_FAILED`, `PAGE_MILESTONE_ERROR`).
- `[pipeline.py:BOOK_MILESTONE_IDLE]` — Book-level milestone status constants (`BOOK_MILESTONE_IDLE`, `BOOK_MILESTONE_IN_PROGRESS`, `BOOK_MILESTONE_COMPLETE`, `BOOK_MILESTONE_PARTIAL_FAILURE`, `BOOK_MILESTONE_FAILED`).
- `[characters.py:Character]` — `class Character`: Historical Uyghur scholar persona definition.
- `[characters.py:DEFAULT_CHARACTER_ID]` — Default character identifier string (`"al_farabi"`).
- `[i18n.py:I18n]` — `class I18n`: Translation and locale manager.
- `[i18n.py:t]` — `t(key: str, **kwargs) -> str`: Fetches localized string for active locale.
- `[i18n.py:get_current_lang]` / `[i18n.py:set_current_lang]` — Context-variable accessors for active language.
- `[prompts.py:OCR_PROMPT]` — Prompt for Gemini OCR text extraction.
- `[prompts.py:BOOK_SUMMARY_PROMPT]` — Prompt for generating structured book summaries.
- `[prompts.py:RAG_PROMPT_TEMPLATE]` — Grounded Q&A prompt template for RAG answer generation.
- `[prompts.py:LLM_SPELL_CHECK_PROMPT]` — Prompt for contextual Uyghur spell checking.
- `[protocols.py:EmbeddingProvider]` — Protocol for document and query vector embedding generators.
- `[protocols.py:LLMProvider]` — Protocol for language model completion and generation providers.
- `[protocols.py:VectorStore]` — Protocol for vector similarity search engines.
- `[providers.py:get_embedding_provider]` — Factory returning configured `EmbeddingProvider`.
- `[providers.py:get_llm_provider]` — Factory returning configured `LLMProvider`.
- `[providers.py:get_vector_store]` — Factory returning configured `VectorStore`.

## Invariants
- `[config.py:Settings]` — Strictly parses environment variables; validates database URLs, API keys, and CORS origins on startup.
- `[pipeline.py:PIPELINE_ORDER]` — Enforces linear pipeline progression: OCR -> Chunking -> Embedding -> Spell Check -> Summary.
- `[i18n.py:I18n]` — Falls back to the default language (`ug`) when translation keys are missing in the requested locale.
- `[prompts.py]` — LLM system prompts are authored strictly in English while requiring modern Uyghur Arabic script for user-facing outputs.

## Side Effects
- `[config.py:Settings]` — Reads environment variables and local `.env` configuration file on initial import.
- `[i18n.py:set_current_lang]` — Mutates Python `contextvars.ContextVar` state for the current async task context.

## Verification
- Run: `pytest packages/backend-core/tests`
