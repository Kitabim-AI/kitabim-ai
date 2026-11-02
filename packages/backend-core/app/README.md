# Backend Core Application (`app`)

## Overview
Primary Python application package for shared backend functionality across the Kitabim AI monorepo. Contains background job management, worker queue lifecycles, and organizes sub-packages for core configuration, database persistence, LLM integrations, Pydantic domain models, services, decorators, and utilities.

## Interface
- `[jobs.py:create_or_reset_job]` — `create_or_reset_job(...)`: Creates a new background batch job or resets an existing one to idle state.
- `[jobs.py:update_job_status]` — `update_job_status(...)`: Updates batch job processing state, milestones, and error payloads.
- `[jobs.py:increment_attempts]` — `increment_attempts(...)`: Increments failure and retry attempt counters for background jobs.
- `[queue.py:worker_startup]` — Startup hook initializing database pools and Redis connections for ARQ worker processes.
- `[queue.py:worker_shutdown]` — Teardown hook gracefully terminating active tasks and closing connection pools.
- `[queue.py:heartbeat_loop]` — Periodic async loop writing worker health check heartbeats to Redis.
- [Core Configuration](./core/README.md) — System settings, pipeline order, cache keys, character personas, and prompts.
- [Database Layer](./db/README.md) — SQLAlchemy models, session factory, migrations, and repositories.
- [Decorators](./decorators/README.md) — Shared function caching decorators.
- [LLM Integration](./llm/README.md) — Gemini client wrappers, circuit breakers, chains, and cost tracking.
- [Domain Models](./models/README.md) — Pydantic DTOs, request/response schemas, and user models.
- [Services](./services/README.md) — Business logic services (OCR, chunking, embeddings, spell check, chat, RAG).
- [Utilities](./utils/README.md) — Concurrency controls, rate limiters, distributed locks, and text utilities.

## Invariants
- `[jobs.py:create_or_reset_job]` — Idempotently restarts batch operations without duplicating pending jobs.
- `[queue.py:worker_startup]` — Halts startup and refuses to process queues if database connection or Redis ping fails.

## Side Effects
- Updates job tracking tables in PostgreSQL via SQLAlchemy.
- Writes worker heartbeat keys and health metrics to Redis.

## Verification
- Run: `pytest packages/backend-core/tests`
