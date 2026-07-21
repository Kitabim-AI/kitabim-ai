# Kitabim.AI — Project Structure

## Table of Contents

1. [Overview](#overview)
2. [Repository Layout](#repository-layout)
3. [`packages/backend-core`](#packagesbackend-core)
4. [`services/backend`](#servicesbackend)
5. [`services/worker`](#servicesworker)
6. [`apps/frontend`](#appsfrontend)
7. [Technology Stack](#technology-stack)
8. [Data Flow](#data-flow)
9. [Deployment](#deployment)
10. [Key Files Reference](#key-files-reference)

---

## Overview

**Kitabim.AI** is a monorepo digital library and conversational query engine for Uyghur literature. It has four moving parts:

- An **OCR ingestion pipeline** (worker) that extracts text page-by-page from PDFs using Gemini Vision.
- A **curation workspace** (frontend + backend) for spell-checking, dictionary lookups, and editorial review.
- A **RAG chat system** with two interchangeable handlers — a fixed-path deterministic router and an LLM-driven Google ADK agent loop — both searching pgvector passages and a Neo4j knowledge graph.
- **User identity**: JWT auth with four OAuth providers and role-based access control.

---

## Repository Layout

```
kitabim-ai/
├── apps/
│   └── frontend/            # React 19 + Vite + TypeScript SPA
├── packages/
│   ├── backend-core/        # Shared Python: models, repos, LLM clients, services
│   └── shared/               # Generated OpenAPI TypeScript types (npm workspace)
├── services/
│   ├── backend/              # FastAPI HTTP API
│   └── worker/                 # ARQ background scanners + jobs
├── deploy/
│   ├── local/                 # Local Docker Compose rebuild scripts
│   └── gcp/                    # Production Docker Compose + deploy scripts
├── scripts/                    # Operational / diagnostic scripts
├── data/                        # Local uploads/covers volume (bind-mounted into containers)
├── docs/                         # Architecture & design docs
├── docker-compose.yml             # Local dev entry point
├── Dockerfile.backend              # Backend API image
└── Dockerfile.worker                # Worker image
```

PostgreSQL is **not** part of `docker-compose.yml` — it runs standalone on the host, and containers reach it at `host.docker.internal:5432`.

---

## `packages/backend-core`

Shared Python package imported by both `services/backend` and `services/worker` (added to `PYTHONPATH` in both Dockerfiles).

```
packages/backend-core/app/
├── core/
│   ├── config.py              # Settings dataclass (env-backed); no model names live here
│   ├── cache_config.py        # Redis TTLs and key templates
│   ├── characters.py          # Chat persona definitions
│   ├── i18n.py                # t() translation lookup
│   ├── pipeline.py            # Pipeline step / milestone constants shared by worker + backend
│   ├── prompts.py             # Base prompt templates
│   └── providers.py           # LLM/storage provider protocols
├── db/
│   ├── models.py               # SQLAlchemy ORM models (21 tables)
│   ├── session.py               # Async engine/session factory, init/close hooks
│   ├── seeds.py                   # Default system_configs seeding
│   └── repositories/               # One repository per table, incl. graph_repository.py (Neo4j)
├── llm/
│   ├── models.py                # GeminiLLM/ProtectedLLM client, CircuitBreaker wiring, RedisRateLimiter
│   └── chains.py                  # TextChain/StructuredChain .ainvoke()/.astream() wrappers
├── models/
│   ├── schemas.py                # Pydantic request/response schemas
│   └── user.py                     # UserRole enum, user Pydantic model
├── services/
│   ├── cache_service.py           # Redis caching wrapper (circuit-breaker protected)
│   ├── rag_service.py               # RAGService facade — builds QueryContext, dispatches via registry
│   ├── ocr_service.py                 # OCR image → text extraction
│   ├── chunking_service.py              # Text cleaning + chunk splitting
│   ├── knowledge_graph_service.py         # Entity/relation extraction orchestration
│   ├── spell_check_service.py               # Dictionary-based spell-check
│   ├── auto_correct_service.py                # Bulk OCR auto-correction rule application
│   ├── book_milestone_service.py               # Milestone transition helpers
│   ├── storage_service.py                        # GCS / local filesystem storage abstraction
│   ├── pdf_service.py, docx_service.py              # PDF/DOCX parsing helpers
│   ├── token_service.py, user_service.py, chat_limit_service.py
│   └── rag/                                          # RAG sub-package (see below)
├── utils/
│   ├── circuit_breaker.py     # Generic Redis-backed CircuitBreaker
│   ├── rate_limiter.py          # RedisRateLimiter
│   ├── citation_fixer.py          # Post-processes malformed inline citations
│   ├── observability.py             # log_json(), request_id contextvar
│   ├── security.py, redis_lock.py, lru_cache.py, markdown.py, text.py, errors.py
├── queue.py                    # ARQ client (enqueue_job)
└── jobs.py                       # create_or_reset_job / update_job_status helpers
```

### `services/rag/` — RAG sub-package
```
app/services/rag/
├── registry.py            # HandlerRegistry — tries handlers in order, first can_handle()==True wins
├── base_handler.py          # QueryHandler interface (handle / handle_stream / can_handle)
├── context.py                 # QueryContext dataclass — per-request state threaded through both handlers
├── answer_builder.py            # Shared instruction-building + generate_answer(_stream)()
├── query_rewriter.py              # Standalone pronoun-resolution helper
├── retrieval.py                     # vector_search, embed_query, find_books_by_title_in_question
├── keywords.py                        # Keyword lists used by fallback heuristics
├── llm_resources.py                     # Builds/caches the answer-generation LLM chain per model name
├── utils.py                               # normalize_uyghur, format_chat_history, empty-response text
├── handlers/
│   └── catalog.py                          # CatalogHandler — helper class for catalog/author lookups, used by tools.py (not itself registered in HandlerRegistry)
└── agent/
    ├── prompts.py            # AGENT_SYSTEM_PROMPT for the LLM-routed ReAct loop
    ├── config.py               # AGENT_MAX_STEPS, grading thresholds, context-switch score threshold
    ├── tools.py                  # 19 ADK-callable tool functions + dispatch-with-retry
    ├── adk_agent.py                 # build_rag_agent() — constructs the ADK Agent + tool list
    ├── deterministic_handler.py       # DeterministicRAGHandler — signal extraction, intent classification, 9 fixed paths
    ├── graph_router.py                  # google.adk.workflow.Workflow graph selecting one of the 9 paths
    └── llm_routed_handler.py              # LLMRoutedRAGHandler — decomposition, context injection, InMemoryRunner ReAct loop
```

`HandlerRegistry` (`registry.py`) is built with `DeterministicRAGHandler` first and `LLMRoutedRAGHandler` last as the always-matching fallback. Which one actually runs a given request is controlled by the `use_deterministic_router` system config — `false` by default, so `LLMRoutedRAGHandler` is the handler that answers most chat traffic today.

---

## `services/backend`

```
services/backend/
├── main.py                  # FastAPI app factory, router registration, CORS, rate limiting, /health
├── api/endpoints/            # One router module per resource (21 files): books, chat, auth, users,
│                                 system_configs, stats, contact, spell_check, auto_correct_rules,
│                                 dictionary, words, synonyms, history_dictionary, names_dictionary,
│                                 english_uyghur, share, cache, questions, proverbs, quran, ai
├── auth/
│   ├── dependencies.py         # get_current_user, require_role() dependency factory
│   ├── jwt_handler.py            # JWT issue/verify, refresh-token rotation
│   └── providers/                  # google_provider.py, facebook_provider.py, twitter_provider.py,
│                                       instagram_provider.py, base_provider.py
├── locales/                      # i18n translation files (t() lookups)
├── requirements.txt                # Backend + worker shared Python deps
└── requirements.postgres.txt         # Postgres/pgvector-specific deps
```

The worker adds `services/worker/requirements.worker.txt` on top of these two files for its own image.

---

## `services/worker`

```
services/worker/
├── worker.py                # ARQ WorkerSettings entrypoint (arq worker.WorkerSettings)
├── manual_scan.py             # CLI to trigger a scanner pass on demand
├── jobs/                        # Per-unit-of-work executors (7)
│   ├── ocr_job.py                  # Renders a page, calls Gemini Vision, writes text
│   ├── chunking_job.py               # Cleans text, writes chunk rows
│   ├── embedding_job.py                # Vectorizes chunks
│   ├── spell_check_job.py                # Flags likely OCR errors per page
│   ├── auto_correct_job.py                 # Applies bulk auto-correction rules
│   ├── summary_job.py                        # Generates + embeds a book summary
│   └── knowledge_graph_job.py                  # Extracts entities/relations, writes to Neo4j
└── scanners/                             # Periodic pollers + the event-driven dispatcher (12)
    ├── ocr_scanner.py                        # Leases idle pages, enqueues ocr_job
    ├── chunking_scanner.py                     # Leases OCR'd pages, enqueues chunking_job
    ├── embedding_scanner.py                      # Leases chunked pages, enqueues embedding_job
    ├── spell_check_scanner.py                      # Leases indexed pages, enqueues spell_check_job
    ├── auto_correct_scanner.py                       # Enqueues auto_correct_job
    ├── summary_scanner.py                              # Leases ready books, enqueues summary_job
    ├── graph_scanner.py                                  # Leases ready books, enqueues knowledge_graph_job (implemented but NOT wired into WorkerSettings.cron_jobs — see WORKER_DESIGN.md)
    ├── event_dispatcher.py                                 # Reacts to pipeline_events for immediate next-step triggering
    ├── gcs_discovery_scanner.py                              # Discovers books uploaded directly to GCS
    ├── pipeline_driver.py                                      # Coordinates scanner scheduling
    ├── stale_watchdog_scanner.py                                 # Recovers pages stuck mid-processing
    └── maintenance_scanner.py                                      # Cleans up processed pipeline_events
```

Each scanner uses a fresh `async with async_session_factory()` per page/batch it processes — no session is held or shared across pages within a run.

---

## `apps/frontend`

```
apps/frontend/src/
├── components/       # admin/ auth/ chat/ common/ graph/ layout/ library/ pages/ reader/ share/ spell-check/ ui/
├── hooks/               # useAuth, useBooks, useBookActions, useChat, usePendingCorrections, useSpellCheck, useUyghurInput (7)
├── services/              # authService, contactService, geminiService, pdfService, persistenceService, userService (6)
├── context/                 # React context providers
├── constants/                  # Static config
├── i18n/, locales/               # Frontend translations
├── utils/                          # Shared client-side helpers
└── tests/                            # Vitest specs mirroring components/hooks/context/services
```

PDF rendering uses `pdf.js` loaded from a CDN `<script>` tag at runtime (`pdfService.ts`), not an npm dependency — there is no `pdfjs-dist` entry in `package.json`.

---

## Technology Stack

### Frontend
- **Framework**: React 19.2
- **Build**: Vite 6.2, TypeScript 5.8
- **Styling**: Tailwind CSS 3.4
- **Testing**: Vitest 4 + Testing Library
- **Graph visualization**: `react-force-graph-2d`
- **PDF rendering**: pdf.js v3.11 via CDN (not bundled)
- **Dev server port**: 3000 (Vite); production served on port 80 behind Nginx

### Backend & Worker
- **Runtime**: Python 3.13
- **Framework**: FastAPI + Uvicorn
- **ORM / DB driver**: SQLAlchemy 2.0 (async) + asyncpg, Alembic migrations
- **Database**: PostgreSQL 17 + pgvector (`Vector(3072)` embeddings)
- **Graph DB**: Neo4j 5.26 (Bolt protocol, Cypher queries)
- **Queue / cache**: Redis 7 + ARQ
- **AI stack**: `google-adk` (`google-adk[gcp]==2.5.0` — agent tool orchestration for both RAG handlers) and `google-genai` (direct generation, embeddings, structured extraction)
- **Other notable deps**: `pymupdf` (PDF parsing/rendering), `python-jose` (JWT), `slowapi` (rate limiting), `neo4j` (driver), `flashrank`, `tenacity` (retry), `python-docx`

### Infrastructure
- **Local dev**: `docker-compose.yml` runs Redis, backend, worker, frontend, and Neo4j as containers; PostgreSQL runs standalone on the host.
- **Production (GCP)**: `deploy/gcp/docker-compose.yml` runs the same services plus an Nginx reverse proxy for TLS termination, behind a single VM. It also defines an `ocr-service` container — present in the compose file and referenced by the worker's `depends_on`/`OCR_SERVICE_URL` env var, but not called anywhere in the current `packages/backend-core` or `services/worker` code (OCR goes through Gemini Vision, not this service); treat it as unverified/likely-legacy infra rather than an active part of the OCR path.

---

## Data Flow

1. **Upload** → backend saves the PDF to GCS, creates `books`/`pages` rows with `pending` milestones.
2. **OCR → Chunking → Embedding → Spell-check** run as an event-driven pipeline: each worker scanner leases `idle` pages, the matching job processes them, and the event dispatcher enqueues the next step immediately when a milestone succeeds (see `SYSTEM_DESIGN.md` §6A for the full sequence).
3. **Book ready** → summary and (if enabled) knowledge-graph extraction run concurrently.
4. **Chat** → `RAGService.answer_question(_stream)` builds a `QueryContext` (resolves character/persona, loads model names from `system_configs`, loads the book if any) and dispatches it through `HandlerRegistry` to whichever handler's `can_handle()` matches, then records telemetry to `rag_evaluations`.

---

## Deployment

- **Local rebuild**: `./deploy/local/rebuild-and-restart.sh [backend|worker|frontend|all]`
- **Local URLs**: Frontend `http://localhost:30080`, Backend `http://localhost:30800`, Neo4j Browser `http://localhost:37474` (Bolt on `37687`)
- **Production deploy**: `./deploy/gcp/scripts/deploy.sh [tag]` — builds and pushes `kitabim-backend`, `kitabim-worker`, `kitabim-frontend` images, then runs `deploy/gcp/docker-compose.yml` on the target VM.

---

## Key Files Reference

| File | Purpose |
|------|---------|
| `packages/backend-core/app/core/config.py` | Env-backed `Settings` dataclass. Deliberately holds no AI model names — those live only in `system_configs`. |
| `packages/backend-core/app/db/models.py` | All 21 SQLAlchemy ORM table definitions. |
| `packages/backend-core/app/db/seeds.py` | Default `system_configs` rows, including default model names and router toggles. |
| `packages/backend-core/app/llm/models.py` | `ProtectedLLM`/`GeminiEmbeddings` clients wrapping `google-genai`, with per-call-type `CircuitBreaker`s and `RedisRateLimiter`. |
| `packages/backend-core/app/services/rag_service.py` | Facade that resolves model names + config from `system_configs`, builds `QueryContext`, and dispatches to `HandlerRegistry`. |
| `packages/backend-core/app/services/rag/registry.py` | `HandlerRegistry` — ordered `can_handle()` dispatch between `DeterministicRAGHandler` and `LLMRoutedRAGHandler`. |
| `packages/backend-core/app/services/rag/agent/deterministic_handler.py` | `DeterministicRAGHandler` — signal extraction, intent classification, and the 9 fixed retrieval paths. |
| `packages/backend-core/app/services/rag/agent/graph_router.py` | `google.adk.workflow.Workflow` graph that selects and runs one of the 9 paths above. |
| `packages/backend-core/app/services/rag/agent/llm_routed_handler.py` | `LLMRoutedRAGHandler` — decomposition, context injection, and the ADK `InMemoryRunner` ReAct loop. |
| `packages/backend-core/app/services/rag/agent/tools.py` | The 19 ADK-callable tool functions shared by both RAG handlers. |
| `services/backend/main.py` | FastAPI app factory — router registration, CORS, rate limiting, `/health`. |
| `services/worker/worker.py` | ARQ `WorkerSettings` entrypoint wiring scanners and jobs into the worker process. |
