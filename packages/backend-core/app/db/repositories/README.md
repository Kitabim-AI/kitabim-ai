# Database Repositories (`app/db/repositories`)

## Overview
Provides async SQLAlchemy data access repositories encapsulating database queries, mutations, filtering, pagination, and caching for all domain entities in Kitabim AI.

## Interface
- `[base_repository.py:BaseRepository]` — Generic base repository providing CRUD primitives (`get_by_id`, `get_all`, `create`, `update`, `delete`, `count`).
- `[books_repository.py:BooksRepository]` — Manages book metadata, processing milestones, catalog searching, and entity query matching.
- `[pages_repository.py:PagesRepository]` — Manages page records, OCR text storage, milestone status transitions, and TOC offsets.
- `[chunks_repository.py:ChunksRepository]` — Handles text chunk storage, pgvector similarity lookups, and keyword searches.
- `[book_summaries_repository.py:BookSummariesRepository]` — Persists and queries book summaries, character profiles, and thematic outlines.
- `[users_repository.py:UsersRepository]` — Manages user profiles, OAuth identity bindings, role updates, and user listing.
- `[refresh_tokens_repository.py:RefreshTokensRepository]` — Stores, validates, and revokes hashed JWT refresh tokens.
- `[system_configs_repository.py:SystemConfigsRepository]` — Manages dynamic system configurations with Redis caching.
- `[user_chat_usage_repository.py:UserChatUsageRepository]` — Tracks and increments daily chat query quotas per user or IP address.
- `[rag_evaluations_repository.py:RAGEvaluationsRepository]` — Stores RAG evaluation metrics, LLM token costs, feedback, and homepage showcases.
- `[auto_correct_rules_repository.py:AutoCorrectRulesRepository]` — Manages Uyghur auto-correction mappings with cached frequent rules.
- `[dictionary_repository.py:DictionaryRepository]` — Manages lexicon words, history dictionary entries, names, English-Uyghur terms, and Quran verses.
- `[synonyms_repository.py:SynonymsRepository]` — Queries Uyghur synonym word pairs.
- `[proverbs_repository.py:ProverbsRepository]` — Queries Uyghur proverbs and proverb search indices.
- `[contact_submissions_repository.py:ContactSubmissionsRepository]` — Handles public contact messages and admin review statuses.
- `[conversation_repository.py:ConversationRepository]` — Manages chat conversation threads and message histories with soft deletion.
- `[reading_progress_repository.py:ReadingProgressRepository]` — Tracks user reading percentage and last active page per book.
- `[bookmarks_repository.py:BookmarksRepository]` — Manages user bookmarked pages and notes.
- `[graph_repository.py:GraphRepository]` — Queries knowledge graph entities and connections.
- `[graph_resolution_repository.py:GraphResolutionQueueRepository]` — Manages entity deduplication queue items.
- `[graph_resolution_repository.py:GraphResolutionReviewsRepository]` — Stores manual and automated entity resolution reviews.
- `[graph_resolution_repository.py:GraphMergeLogRepository]` — Logs entity merge and unmerge audit histories.

## Invariants
- `[base_repository.py:BaseRepository]` — Requires an active `AsyncSession` for all queries and operations.
- `[conversation_repository.py:ConversationRepository]` — Automatically filters out soft-deleted conversations (`is_deleted == False`) on retrieval.
- `[dictionary_repository.py:_sql_normalize_uyghur]` — Normalizes Uyghur Arabic orthographic variants (e.g. kaf/gaf, yeh variations) for uniform lookup.

## Side Effects
- Executes read and write SQL statements against PostgreSQL database tables.
- Invalidates and populates Redis cache keys for cached entity repositories (e.g., system configs and auto-correct rules).

## Verification
- Run: `pytest packages/backend-core/tests`
