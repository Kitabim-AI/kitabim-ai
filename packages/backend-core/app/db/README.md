# Database Layer (`app/db`)

## Overview
Defines the SQLAlchemy 2.0 ORM domain models, database engine initialization, connection pooling, async session management, initial configuration seeding, and entity repositories.

## Interface
- `[models.py:Base]` — Declarative ORM base class for all database models.
- `[models.py:Book]` — ORM model for books and pipeline milestone tracking.
- `[models.py:Page]` — ORM model for book pages, OCR text, and processing statuses.
- `[models.py:Chunk]` — ORM model for document chunks and vector embeddings (`pgvector`).
- `[models.py:User]` / `[models.py:RefreshToken]` — ORM models for user identity and token sessions.
- `[models.py:SystemConfig]` — ORM model for dynamic configuration parameters.
- `[models.py:RAGEvaluation]` — ORM model for RAG response quality metrics and token costs.
- `[models.py:BatchOCRJob]` — Batch processing job models (`BatchOCRJob`, `BatchEmbeddingJob`, `BatchHistoryExtractionJob`, `BatchLlmSpellCheckJob`).
- `[models.py:HistoryDictionary]` — Models for history dictionary (`HistoryDictionary`, `HistoryDictionaryStaging`).
- `[models.py:Conversation]` — Models for user chat histories (`Conversation`, `ConversationMessage`).
- `[session.py:init_db]` — Initializes the SQLAlchemy async engine and session factory.
- `[session.py:close_db]` — Closes the async engine and releases connection pool resources.
- `[session.py:get_session]` — Async generator yielding scoped `AsyncSession` instances.
- `[session.py:get_engine]` — Returns the active `AsyncEngine` instance.
- `[seeds.py:seed_system_configs]` — Idempotently seeds default system configurations into PostgreSQL (including OCR, RAG, embedding, spell-check, and `auth_usercheck_enabled` / `auth_blocked_email_domains` signup gate defaults).
- [Repositories](./repositories/README.md) — Subdirectory providing domain repository query classes.

## Invariants
- `[session.py:get_database_url]` — Enforces the `postgresql+asyncpg://` async driver protocol.
- `[seeds.py:seed_system_configs]` — Idempotent execution: seeds default system configuration keys without overwriting existing admin-modified values.
- `[models.py]` — Foreign keys, cascading constraints, and timestamp mixins (`created_at`, `updated_at`) are strictly declared on relational entities.

## Side Effects
- Establishes persistent async connection pools to PostgreSQL via SQLAlchemy and `asyncpg`.
- Commits initial system configuration seeds to the database on system startup.

## Verification
- Run: `pytest packages/backend-core/tests`
