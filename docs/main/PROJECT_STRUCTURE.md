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
- A **RAG chat system** (`ChatOrchestrator`) — an LLM-driven Google ADK agent loop searching pgvector passages and a Neo4j knowledge graph.
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
│   ├── models.py               # SQLAlchemy ORM models (30 tables)
│   ├── session.py               # Async engine/session factory, init/close hooks
│   ├── seeds.py                   # Default system_configs seeding
│   └── repositories/               # 17 repository modules, ~one per table, incl. graph_repository.py (Neo4j)
│                                      and conversation_repository.py (Conversation/ConversationMessage);
│                                      batch_ocr_jobs/batch_embedding_jobs/pipeline_events are queried inline
│                                      from their owning service instead of through a dedicated repository
├── llm/
│   ├── models.py                # GeminiLLM/ProtectedLLM client, CircuitBreaker wiring, RedisRateLimiter
│   └── chains.py                  # TextChain/StructuredChain .ainvoke()/.astream() wrappers
├── models/
│   ├── schemas.py                # Pydantic request/response schemas
│   └── user.py                     # UserRole enum, user Pydantic model
├── services/
│   ├── cache_service.py           # Redis caching wrapper (circuit-breaker protected)
│   ├── ocr_service.py                 # OCR image → text extraction (interactive Gemini Vision)
│   ├── batch_ocr_service.py             # Gemini Batch API OCR submission + result polling (feature-flagged)
│   ├── chunking_service.py                # Text cleaning + chunk splitting
│   ├── batch_embedding_service.py           # Gemini Batch API embedding submission + result polling (feature-flagged)
│   ├── knowledge_graph_service.py             # Entity/relation extraction orchestration
│   ├── entity_resolution_service.py             # Merge/split algorithm (scope-parameterized), used by graph_resolution_job
│   │                                                and the admin merge/split/unmerge endpoints alike
│   ├── history_extraction_service.py              # History-term extraction + fact classification/synthesis from book pages
│   ├── batch_history_extraction_service.py          # Gemini Batch API history-extraction submission + result polling (feature-flagged)
│   ├── history_fact_utils.py                          # Pure dedup/similarity helpers for extracted history facts (no I/O)
│   ├── dictionary_staging_service.py                    # Reviews history_dictionary_staging candidates, publishes approvals
│   ├── spell_check_service.py                             # Dictionary-based spell-check
│   ├── auto_correct_service.py                              # Bulk OCR auto-correction rule application
│   ├── book_milestone_service.py                              # Milestone transition helpers
│   ├── storage_service.py                                       # GCS / local filesystem storage abstraction
│   ├── pdf_service.py, docx_service.py                             # PDF/DOCX parsing helpers
│   ├── token_service.py, user_service.py, chat_limit_service.py
│   ├── rag/                                                         # Retrieval primitives + ADK tools shared by the chat pipeline (see below)
│   └── chat/                                                          # ADK-native ChatOrchestrator — the chat pipeline (see below)
├── utils/
│   ├── circuit_breaker.py     # Generic Redis-backed CircuitBreaker
│   ├── rate_limiter.py          # RedisRateLimiter
│   ├── citation_fixer.py          # Post-processes malformed inline citations
│   ├── observability.py             # log_json(), request_id contextvar
│   ├── security.py, redis_lock.py, lru_cache.py, markdown.py, text.py, errors.py
├── queue.py                    # ARQ client (enqueue_job)
└── jobs.py                       # create_or_reset_job / update_job_status helpers
```

### `services/rag/` — shared retrieval primitives
```
app/services/rag/
├── context.py                 # QueryContext dataclass — per-request state threaded through tool calls
├── answer_builder.py            # Document/format_document/build_instructions (generate_answer_stream is now dead code)
├── query_rewriter.py              # Standalone pronoun-resolution helper
├── judge.py                         # LLM-as-judge scoring (faithfulness/answer_relevance/context_precision),
│                                        used by rag_eval_job
├── retrieval.py                     # vector_search, embed_query, find_books_by_title_in_question,
│                                        exact_phrase_chunk_search (keyword-only leg)
├── phrase_intent.py                    # detect_phrase_intent() — classifies quoted/"Exact phrase" questions
│                                          (keyword-search-rework-plan.md Phase 1)
├── keywords.py                        # Keyword lists used by fallback heuristics
├── llm_resources.py                     # Builds/caches the answer-generation LLM chain per model name
├── utils.py                               # normalize_uyghur, format_chat_history, empty-response text
├── handlers/
│   └── catalog.py                          # CatalogHandler — static helper class for catalog/author lookups, used by tools.py
└── agent/
    ├── prompts.py            # AGENT_SYSTEM_PROMPT for the retrieval agent
    ├── config.py               # AGENT_MAX_STEPS, grading thresholds, context-switch score threshold
    ├── tools.py                  # 19 ADK-callable tool functions + dispatch-with-retry
    └── reranker.py               # rerank_context() — LLM reranker, called only from chat/orchestrator.py
```

### `services/chat/` — the chat pipeline
```
app/services/chat/
├── context.py            # ChatRequestDTO (adds conversation_id), ToolDependencies
├── context_grading.py      # _build_human_message / _grade_context / _extract_used_book_ids
├── query_signals.py          # analyze_query_signals() — single-shot structured signal-extraction LLM call
├── history.py                   # Formats ConversationMessage rows into LLM-readable history text
├── answer_prompts.py              # build_answer_instructions() — citation/grammar prompt for the answer agent
├── answer_agent.py                   # build_answer_agent() — tools-less ADK Agent for answer synthesis
├── retrieval_agent.py                   # ALL_TOOLS + build_retrieval_agent() — the one retrieval agent, all 19 tools
├── exact_phrase.py                         # run_exact_phrase_retrieval() + page-hit formatting for the keyword-only leg
│                                              (Phase 1 of keyword-search-rework-plan.md), driven by rag/phrase_intent.py
└── orchestrator.py                         # ChatOrchestrator — the pipeline itself, see below
```

`ChatOrchestrator` is the only chat pipeline — both `POST /api/chat/` (via its non-streaming `answer()` wrapper) and `POST /api/chat/stream` (via `stream_response()`) build one unconditionally. It runs a two-agent pipeline (retrieval agent → grading → answer agent) on an ADK `Runner`, persists every turn to `conversations`/`conversation_messages` via `ConversationRepository`, and is what backs the frontend's conversation-history sidebar. It uses the `rag/agent/` tool implementations and system prompt directly, but has its own copy of the answer-synthesis citation prompt (`answer_prompts.py`) rather than sharing `rag/answer_builder.py` (whose own `generate_answer_stream()` is now unused dead code, left over from a deleted legacy pipeline — see `docs/superpowers/plans/2026-08-12-adk-chat-consolidation.md`). Before any of that, `detect_phrase_intent()` (`rag/phrase_intent.py`) checks the question for a quoted phrase or the explicit "Exact phrase" UI flag; if it matches, the turn is answered by `chat/exact_phrase.py`'s keyword-only leg instead (no vector/graph fusion), with page-finding phrasing ("find pages with...") rendered as raw page hits rather than an LLM-synthesized answer.

---

## `services/backend`

```
services/backend/
├── main.py                  # FastAPI app factory, router registration, CORS, rate limiting, /health
├── api/endpoints/            # One router module per resource (23 files): books, chat, auth, users,
│                                 system_configs, stats, contact, spell_check, auto_correct_rules,
│                                 dictionary, words, synonyms, history_dictionary, names_dictionary,
│                                 english_uyghur, share, cache, questions, proverbs, quran, ai,
│                                 admin_history_dictionary (admin-only history-extraction/staging-review
│                                 actions), graph_admin (admin-only entity split/unmerge/review-queue actions)
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
├── jobs/                        # Per-unit-of-work executors (10)
│   ├── ocr_job.py                  # Renders a page, calls Gemini Vision (or submits a batch_ocr_job if gemini_batch_ocr_enabled)
│   ├── chunking_job.py               # Cleans text, writes chunk rows
│   ├── embedding_job.py                # Vectorizes chunks (synchronous path; batch path is submitted inline by embedding_scanner)
│   ├── spell_check_job.py                # Flags likely OCR errors per page
│   ├── auto_correct_job.py                 # Applies bulk auto-correction rules
│   ├── summary_job.py                        # Generates + embeds a book summary
│   ├── knowledge_graph_job.py                  # Extracts entities/relations, writes to Neo4j
│   ├── graph_resolution_job.py                   # Resolves/merges duplicate graph entities against Neo4j fuzzy-match candidates
│   ├── history_extraction_job.py                   # Extracts + stages history-dictionary terms/facts for a book (or submits a
│   │                                                   batch_history_extraction_job if gemini_batch_history_extraction_enabled);
│   │                                                   admin-triggered, not on a cron schedule
│   └── rag_eval_job.py                             # Post-turn async judge scoring for rag_evaluations (enqueued by ChatOrchestrator, not a scanner)
└── scanners/                             # Periodic pollers + the event-driven dispatcher (16)
    ├── ocr_scanner.py                        # Leases idle pages, enqueues ocr_job
    ├── batch_ocr_poller_scanner.py              # Polls in-flight batch_ocr_jobs, ingests results when Gemini finishes
    ├── chunking_scanner.py                        # Leases OCR'd pages, enqueues chunking_job
    ├── embedding_scanner.py                         # Leases chunked pages; dispatches embedding_job, or submits a batch_embedding_job inline if gemini_batch_embedding_enabled
    ├── batch_embedding_poller_scanner.py               # Polls in-flight batch_embedding_jobs, writes vectors back when Gemini finishes
    ├── spell_check_scanner.py                            # Leases indexed pages, enqueues spell_check_job
    ├── auto_correct_scanner.py                             # Enqueues auto_correct_job
    ├── summary_scanner.py                                    # Leases ready books, enqueues summary_job
    ├── graph_scanner.py                                        # Leases ready books, enqueues knowledge_graph_job (implemented but NOT wired into WorkerSettings.cron_jobs — see WORKER_DESIGN.md)
    ├── graph_resolution_scanner.py                               # Claims graph_resolution_queue rows, dispatches one graph_resolution_job per scope
    ├── batch_history_poller_scanner.py                             # Polls in-flight batch_history_extraction_jobs, stages results when Gemini finishes
    ├── event_dispatcher.py                                       # Reacts to pipeline_events for immediate next-step triggering
    ├── gcs_discovery_scanner.py                                    # Discovers books uploaded directly to GCS
    ├── pipeline_driver.py                                            # Coordinates scanner scheduling
    ├── stale_watchdog_scanner.py                                       # Recovers pages stuck mid-processing
    └── maintenance_scanner.py                                            # Cleans up processed pipeline_events
```

15 of these 16 scanners are wired into `WorkerSettings.cron_jobs` — `graph_scanner.py` is the one exception (see [WORKER_DESIGN.md](WORKER_DESIGN.md)). Each scanner uses a fresh `async with async_session_factory()` per page/batch it processes — no session is held or shared across pages within a run. `ocr_job`, `chunking_job`, `embedding_job`, and `spell_check_job` additionally take a Redis `MultiPageLock` (namespaced per stage via a `prefix` argument) around their claimed page IDs as a second line of defense against double-processing.

---

## `apps/frontend`

```
apps/frontend/src/
├── components/       # admin/ auth/ chat/ common/ graph/ layout/ library/ pages/ reader/ share/ spell-check/ ui/
│                        chat/: AgentThinkingSteps, ChatInterface, ReferenceModal
│                        library/: SearchTabBar + searchTabsConfig.ts drive the home search box's fixed, paginated
│                                   tab bar (Ask/Books/Content/Dictionary/Quran/Names/History/Proverbs/Spell-check/
│                                   Synonyms/English-Uyghur); per-tab result rendering lives in HomeSearchTabResults,
│                                   LookupResultsList (dictionary/names/history/synonyms/en-ug), QuranResultsList,
│                                   and SpellCheckResult
│                        share/: ShareModal (whole-book share), ShareChatModal (single Q&A share — implemented,
│                                 backed by a working `/api/share/qa` endpoint, but not currently rendered from
│                                 any component; there is no "share this answer" entry point in the chat UI today)
├── hooks/               # useAuth, useBookActions, useBooks, useChat, useContentSearch, useLookupSearch,
│                            usePendingCorrections, useScrollStabilizer, useScrollToPage, useSpellCheck,
│                            useSpellingCheck, useUyghurInput (12)
│                            useScrollStabilizer: keeps the visible reader page stationary while
│                            off-screen-above placeholders resolve to real content during ordinary
│                            scrolling; useScrollToPage handles the equivalent for the initial
│                            jump-to-page settle window
├── services/              # authService, contactService, geminiService, pdfService, persistenceService,
│                             searchTabsService, userService (7)
│                             geminiService.ts is legacy-named — despite the name, it calls the Kitabim backend
│                             (/api/chat/*, /api/ai/ocr/), never Gemini directly; it owns chatWithBookStream()
│                             (the SSE transport) and the conversation CRUD calls (getUserConversations,
│                             getConversationMessages, deleteConversation, createConversation)
│                             searchTabsService.ts is the client for the non-"Ask" home search tabs — thin wrappers
│                             over the existing dictionary/names/history/proverbs/synonyms/english-uyghur/quran
│                             search endpoints plus the new `/api/books/content-search` and
│                             `/api/dictionary/check-spelling` endpoints
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
- **AI stack**: `google-adk` (`google-adk[gcp]==2.5.0` — agent tool orchestration for `ChatOrchestrator`'s retrieval + answer agents) and `google-genai` (direct generation, embeddings, structured extraction)
- **Other notable deps**: `pymupdf` (PDF parsing/rendering), `python-jose` (JWT), `slowapi` (rate limiting), `neo4j` (driver), `flashrank`, `tenacity` (retry), `python-docx`

### Infrastructure
- **Local dev**: `docker-compose.yml` runs Redis, backend, worker, frontend, and Neo4j as containers; PostgreSQL runs standalone on the host.
- **Production (GCP)**: `deploy/gcp/docker-compose.yml` runs backend, worker, frontend, Redis, Neo4j, plus an Nginx reverse proxy for TLS termination behind a single Compute Engine VM.

---

## Data Flow

1. **Upload** → backend saves the PDF to GCS, creates `books`/`pages` rows with `pending` milestones.
2. **OCR → Chunking → Embedding → Spell-check** run as an event-driven pipeline: each worker scanner leases `idle` pages, the matching job processes them, and the event dispatcher enqueues the next step immediately when a milestone succeeds (see `SYSTEM_DESIGN.md` §6A for the full sequence).
3. **Book ready** → summary and (if enabled) knowledge-graph extraction run concurrently.
4. **Chat** → both the streaming and non-streaming endpoints build a `ChatOrchestrator` unconditionally: a retrieval agent → grading → answer agent pipeline that persists conversation history and records telemetry to `rag_evaluations`.

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
| `packages/backend-core/app/db/models.py` | All 30 SQLAlchemy ORM table definitions. |
| `packages/backend-core/app/db/repositories/conversation_repository.py` | `ConversationRepository` — CRUD + soft-delete for `conversations`/`conversation_messages`, used only by `ChatOrchestrator`. |
| `packages/backend-core/app/services/chat/orchestrator.py` | `ChatOrchestrator` — the only chat pipeline; `stream_response()` for `POST /api/chat/stream`, `answer()` for `POST /api/chat/`. |
| `packages/backend-core/app/services/batch_ocr_service.py` / `batch_embedding_service.py` / `batch_history_extraction_service.py` | Gemini Batch API submission + polling for OCR, embeddings, and history-dictionary extraction, feature-flagged off by default. |
| `packages/backend-core/app/db/seeds.py` | Default `system_configs` rows, including default model names and pipeline-tuning toggles. |
| `packages/backend-core/app/llm/models.py` | `ProtectedLLM`/`GeminiEmbeddings` clients wrapping `google-genai`, with per-call-type `CircuitBreaker`s and `RedisRateLimiter`. |
| `packages/backend-core/app/services/rag/agent/tools.py` | The 19 ADK-callable tool functions used by the retrieval agent. |
| `services/backend/main.py` | FastAPI app factory — router registration, CORS, rate limiting, `/health`. |
| `services/worker/worker.py` | ARQ `WorkerSettings` entrypoint wiring scanners and jobs into the worker process. |
