# Kitabim.AI

> **The definitive intelligent knowledge base for Uyghur literature, history, and culture.**

**Kitabim.AI** is an end-to-end digital library, OCR ingestion engine, and agentic RAG query assistant dedicated to digitizing, indexing, and preserving the complete written corpus of publications in the Uyghur language. It turns physical books into a living, queryable knowledge network accessible through natural-language conversation, interactive dictionary lookup, and graph-based entity exploration.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
- [Architecture \& High-Level Design](#architecture--high-level-design)
  - [System Architecture](#system-architecture)
  - [Book Processing \& Ingestion Pipeline](#book-processing--ingestion-pipeline)
  - [Agentic RAG Question Answering Pipeline](#agentic-rag-question-answering-pipeline)
  - [Knowledge Graph \& Entity Resolution](#knowledge-graph--entity-resolution)
  - [Interactive Archify Diagrams](#interactive-archify-diagrams)
- [Monorepo Project Structure](#monorepo-project-structure)
- [Technology Stack](#technology-stack)
- [Getting Started (Local Development)](#getting-started-local-development)
  - [Prerequisites](#prerequisites)
  - [Environment Setup](#environment-setup)
  - [Running with Docker Compose](#running-with-docker-compose)
  - [Local Service Endpoints](#local-service-endpoints)
  - [Rebuilding Services](#rebuilding-services)
- [Production Deployment \& Data Safety](#production-deployment--data-safety)
- [Documentation Index](#documentation-index)

---

## Overview

Uyghur literature and historical publications exist overwhelmingly in physical form. Millions of Uyghur speakers worldwide face severe challenges discovering, searching, and analyzing the written heritage of their civilization. Keyword searching fails on scanned PDFs because Uyghur is agglutinative, OCR output often has spelling anomalies, and complex thematic or historical questions span multiple books and volumes.

**Kitabim.AI solves this by pairing OCR digitization with an Agentic RAG architecture powered by Google ADK and Google Gemini.** Rather than relying on simple vector search, Kitabim.AI employs language-model agents that reason over query intent, decompose composite questions, call specialized retrieval and dictionary tools, perform graph entity lookups, and synthesize answers with precise inline citations to source books, volumes, and page numbers.

---

## Key Features

### 📄 Ingestion & Digitization Pipeline
- **Gemini Vision OCR**: Page-by-page text extraction from uploaded PDFs with automated text normalization for Uyghur script. Supports interactive API execution as well as asynchronous **Gemini Batch API** modes (`ocr_batch_enabled` / `embed_batch_enabled`).
- **Milestone State Machine**: Resumable, multi-stage processing pipeline (`OCR → Chunking → Embedding → Spell-Check → Summary → Graph Extraction`).
- **Event-Driven Outbox**: Low-latency reactive trigger system (`pipeline_events` outbox + Event Dispatcher) ensuring swift stage handoffs without waiting for cron intervals.
- **Smart Chunking & Embeddings**: Overlapping window chunking stored with `pgvector` similarity indexes using Gemini Embedding v2.

### 🤖 Agentic RAG & Natural Language QA
- **`ChatOrchestrator`** (the only chat pipeline): Persistent conversation history, query-signal analysis, ADK Retrieval Agent (19 tools), context reranking / context grading, and ADK Answer Agent with streaming SSE output.
- **Hybrid Retrieval**: `pgvector` semantic search fused with PostgreSQL full-text keyword search via Reciprocal Rank Fusion (`rag_hybrid_search_enabled`), followed by an LLM-based reranking pass (`rag_reranker_enabled`) before context grading.
- **19 Specialized ADK Tools**: Includes passage search, summary search, title/author matching, catalog lookup, current reader page text, sister volume discovery, Uyghur dictionary lookups, scripture (Quran) vector search, and post-vector knowledge graph entity lookup.
- **Fine-Grained Citations**: Answers cite `ref:book_id:page_number` inline immediately after the relevant sentence (with multi-page and Quran surah:ayah variants), not just at the book level.
- **Automated RAG Evaluation**: Post-turn async scoring (`rag_eval_job`) evaluating answer faithfulness, relevance, context precision, and context recall per turn.

### 🕸️ Knowledge Graph & Entity Resolution (GraphRAG)
- **Neo4j Semantic Network**: Automatically extracts Person, Location, Organization, Work, and Event entities and relationships from book content.
- **Scheduled Entity Resolution**: Background worker pipeline (`graph_resolution_scanner` → `graph_resolution_job`) resolving duplicate entities using hard-match parent boosting, gray-zone review management (`graph_resolution_reviews`), and automated review resolution upon entity merges.

### 📖 Editorial Workspace & Quality Layer
- **Uyghur Spell-Checking**: Per-page spell audit against an extensive Uyghur dictionary with custom auto-correct rules.
- **Human-in-the-Loop OCR Correction**: Dedicated spell-check review workspace (`SpellCheckPanel` / `SpellCheckView`) where editors accept, edit, skip, or dictionary-add flagged OCR words per page, with confidence badges and full state tracking (`page_spell_issues`).
- **Bulk OCR Auto-Correction**: Scheduled daily job (`auto_correct_scanner`) applying auto-correction rules across processed pages.
- **Interactive Reader & Curation UI**: Modern React 19 SPA with PDF viewer, in-reader query assistant, spellcheck review workspace, and admin analytics panel.

### 📚 AI-Driven History Dictionary Extraction
- **Gemini-Powered Fact Extraction**: Extracts structured Uyghur history-dictionary entries from book content (interactive and Gemini Batch API modes, `batch_history_poller_scanner` / `history_extraction_job`).
- **Admin Review & Staging Workflow**: Extracted entries land in a staging queue for admin approval/conflict-resolution before merging into the live `history_dictionary` table (`admin_history_dictionary_router`, `history_dictionary_router`).

### 🔐 User Management & Access Control
- **OAuth2 & JWT Authentication**: Support for Google, Facebook, Twitter/X, and Instagram login with secure `httpOnly` cookies.
- **Role Hierarchy**: Strict role-based access control (**Admin**, **Editor**, **Reader**, **Guest**).

---

## Architecture & High-Level Design

### System Architecture

```mermaid
flowchart LR
  FE[Frontend<br/>React 19 + Vite] -->|REST API, SSE| BE[Backend API<br/>FastAPI]
  BE -->|enqueue jobs| RQ[(Redis / ARQ Queue)]
  RQ --> WK[Worker<br/>ARQ scanners + jobs]
  BE --> GEM[Gemini API<br/>google-genai / google-adk]
  WK --> GEM
  BE --> DB[(PostgreSQL<br/>+ pgvector)]
  WK --> DB
  WK -.->|transactional outbox| DB
  DB -.->|pipeline_events poll| WK
  BE <-->|PDFs / covers| GCS[(Google Cloud Storage / Local)]
  WK <-->|PDFs / covers| GCS
  BE <-->|L0-L2 Cache| CACHE[(Redis Cache)]
  BE --> N4J[(Neo4j<br/>Knowledge Graph)]
  WK --> N4J
```

### Book Processing & Ingestion Pipeline

The worker runs an event-driven milestone state machine driving books from `pending` to `ready`.

```mermaid
flowchart TD
    %% Triggers
    subgraph Triggers [Event Triggers]
        T1[User Uploads PDF] -->|Creates Book + page stubs| InitDB
        T2[GCS Discovery Scanner<br/>every 5 min] -->|Registers Book + page stubs| InitDB
    end

    InitDB(["Book: status=pending<br/>Pages: all milestones idle"])

    %% Mandatory sequential pipeline
    subgraph Pipeline ["Mandatory Pipeline — OCR → Chunking → Embedding"]
        S_OCR["OCR Scanner<br/>groups claim by book"] -->|Claim idle, dispatch per book| J_OCR[OCR Job]
        S_CH["Chunking Scanner<br/>cross-book"] -->|"Claim idle<br/>dep: ocr=succeeded<br/>+ spell_check terminal when<br/>spell_check_enabled"| J_CH[Chunking Job]
        S_EM["Embedding Scanner<br/>cross-book"] -->|"Claim idle<br/>dep: chunking=succeeded"| J_EM[Embedding Job]
    end

    InitDB --> S_OCR

    %% Event Bus / Outbox — reactive low-latency triggers
    subgraph Outbox [Transactional Outbox]
        J_OCR -->|"Write Event<br/>ocr_succeeded"| OB[(pipeline_events)]
        J_CH -->|"Write Event<br/>chunking_succeeded"| OB
        J_EM -->|"Write Event<br/>embedding_succeeded"| OB

        OB -->|Poll, every 1 min + startup| ED[Event Dispatcher]

        ED -->|"Immediate dispatch chunking_job"| J_CH
        ED -->|"Immediate dispatch embedding_job"| J_EM
    end

    %% Book readiness — driven by PipelineDriver
    J_EM -->|embedding terminal| PD["Pipeline Driver<br/>every 1 min"]
    PD -->|"ALL pages terminal,<br/>zero exhausted failures"| Ready([Book: status=ready])
    PD -->|"ALL pages terminal,<br/>>=1 exhausted failure"| BookErr([Book: status=error])

    Ready -->|Auto-enqueue, once per book| J_SUM[Summary Job]
    Ready -.->|"graph_milestone reset to idle<br/>(manual trigger only)"| J_KG[Knowledge Graph Job]

    J_SUM -->|Save summary + embedding| PG[(PostgreSQL)]
    J_KG -->|"Index entities & relations"| N4J[(Neo4j)]

    %% Entity resolution
    subgraph Resolution ["Entity Resolution"]
        J_KG -->|"Bulk-enqueue entity rows"| GQ[(graph_resolution_queue)]
        GQ --> S_GR["Graph Resolution Scanner<br/>every 5 min"]
        S_GR -->|"Claim batch, dispatch per scope"| J_GR[Graph Resolution Job]
        J_GR -->|"Merge duplicates & parent boost"| N4J
    end

    %% Quality layer
    subgraph SpellCheck ["Quality Layer"]
        S_SC["Spell Check Scanner"] -->|Claim idle| J_SC[Spell Check Job]
    end
    InitDB -.->|ocr done| S_SC
    J_SC -->|"Write Event"| OB
```

### Agentic RAG Question Answering Pipeline

Question answering is served entirely by `ChatOrchestrator` — the single pipeline behind both `POST /api/chat/` and `POST /api/chat/stream`.

```mermaid
flowchart TD
    Q(["User Question + Context"]) --> ORCH["ChatOrchestrator"]
    ORCH --> RET_AGENT["[LLM] KitabimRetrievalAgent<br/>(Google ADK + 19 Tools)"]
    RET_AGENT --> RERANK{"rag_reranker_enabled?"}
    RERANK -- Yes --> RR["LLM Reranker"]
    RERANK -- No --> GRADE["Context Grading"]
    RR --> ANS_AGENT
    GRADE --> ANS_AGENT["[LLM] KitabimAnswerAgent<br/>(Streaming Answer Synthesis)"]
    ANS_AGENT --> SAVE["Save Turn & Enqueue Evaluation"]
```

### Knowledge Graph & Entity Resolution

1. **Extraction (`knowledge_graph_job`)**: Triggered manually via admin action (`POST /api/books/{id}/reprocess/graph`). Extracts entities and relationships into Neo4j using UUID keys and inserts entity records into PostgreSQL `graph_resolution_queue`.
2. **Resolution (`graph_resolution_scanner` → `graph_resolution_job`)**: Scheduled every 5 minutes. Claims queued entity batches oldest-generation-first (`FOR UPDATE SKIP LOCKED`), applies fuzzy/phonetic/alias matching with hard-match parent boosting, merges target entities in Neo4j, auto-resolves existing reviews, or flags ambiguous entities in `graph_resolution_reviews`.

### Interactive Archify Diagrams

Interactive HTML diagrams generated with [Archify](https://github.com/tt-a1i/archify) are available in [**`diagrams/`**](diagrams/README.md):

- [**System Architecture Map**](diagrams/system-architecture.html) (`diagrams/system-architecture.html`): Full infrastructure topology, service interactions, and pipeline views.
- [**Book Ingestion & RAG Chat Sequence**](diagrams/sequence-pipelines.html) (`diagrams/sequence-pipelines.html`): Step-by-step sequence flows for PDF upload, OCR processing, and RAG streaming.
- [**OCR & Document Processing Workflow**](diagrams/workflow-ocr-pipeline.html) (`diagrams/workflow-ocr-pipeline.html`): End-to-end workflow for PDF extraction, page splitting, OCR, and embedding commit.
- [**Hybrid Search & RAG Data Flow**](diagrams/dataflow-rag-hybrid-search.html) (`diagrams/dataflow-rag-hybrid-search.html`): Data flow from query intake to pgvector + Knowledge Graph lookup and Gemini synthesis.
- [**Book Processing Lifecycle**](diagrams/lifecycle-book-processing.html) (`diagrams/lifecycle-book-processing.html`): State machine transitions from `Uploaded` to `Indexed Ready`.
- [**Uyghur Spellcheck Sequence**](diagrams/sequence-spellcheck.html) (`diagrams/sequence-spellcheck.html`): Exact dictionary lookup, phonetic sound-alike matching, and edit distance candidate ranking.

---

## Monorepo Project Structure

```
kitabim-ai/
├── apps/
│   └── frontend/              # React 19 + Vite + TypeScript SPA
├── packages/
│   ├── backend-core/          # Shared Python core: models, repos, LLM clients, services, ADK tools
│   └── shared/                # Generated OpenAPI TypeScript types (npm workspace package)
├── services/
│   ├── backend/                # FastAPI HTTP API (routes, auth, middleware)
│   └── worker/                 # ARQ background processing worker (16 scanners, 10 jobs)
├── deploy/
│   ├── local/                 # Local Docker Compose rebuild & execution scripts
│   └── gcp/                    # Production GCP infrastructure & deployment scripts
├── scripts/                    # Operational, diagnostic, and database maintenance scripts
├── data/                       # Local volume storing uploaded PDFs and page images
├── docs/                       # Comprehensive architecture and design documentation
├── docker-compose.yml          # Local development Docker Compose manifest
├── Dockerfile.backend          # Production Dockerfile for Backend API service
└── Dockerfile.worker           # Production Dockerfile for Worker service
```

### Core Package Breakdown (`packages/backend-core/app/`)

- **`core/`**: Environment configurations (`config.py`), cache templates (`cache_config.py`), pipeline state constants (`pipeline.py`), character personas (`characters.py`), and i18n (`i18n.py`).
- **`db/`**: SQLAlchemy models (`models.py` — 30 PostgreSQL tables), database engine factory (`session.py`), system configuration seeds (`seeds.py`), and 18 repository classes in `db/repositories/`.
- **`llm/`**: `GeminiLLM` client, `TextChain` / `StructuredChain` wrappers, Redis rate limiting, and circuit breaker resilience.
- **`services/`**: Core business services including OCR, chunking, embeddings, spell-check, auto-correction, summary generation, storage abstraction, and sub-packages:
  - **`services/rag/`**: Shared retrieval primitives used by `ChatOrchestrator` — no handlers. Retrieval engine (`retrieval.py`), `QueryContext`, the 19 ADK tools (`rag/agent/tools.py`), the LLM reranker, and other tool-implementation helpers.
  - **`services/chat/`**: `ChatOrchestrator`, `KitabimRetrievalAgent`, `KitabimAnswerAgent`, conversation state management (`history.py`), and context builders.

---

## Technology Stack

| Layer | Technologies Used |
|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind CSS, Lucide Icons, PDF.js |
| **Backend API** | Python 3.13, FastAPI, Pydantic v2, SQLAlchemy (Async IO) |
| **Worker / Queue** | Python 3.13, ARQ (Async Redis Queue) |
| **Relational Database** | PostgreSQL 16+ with `pgvector` extension (Vector Similarity Search) |
| **Graph Database** | Neo4j 5+ (Cypher Graph Database for GraphRAG) |
| **Cache & Locking** | Redis (L0-L3 Query Caching, Distributed `MultiPageLock`, Rate Limiting) |
| **Storage** | Google Cloud Storage (GCS) with local `./data/` volume fallback |
| **AI & LLM Frameworks** | Google Gemini API (`google-genai` SDK), Google ADK (`google-adk` framework) |
| **Authentication** | JWT (httpOnly Cookies) + OAuth2 (Google, Facebook, Twitter/X, Instagram) |

---

## Getting Started (Local Development)

### Prerequisites

1. **Docker Desktop** installed and running.
2. **PostgreSQL** running standalone on the local host machine at `localhost:5432` (PostgreSQL is **not** containerized in Docker Compose locally; containers connect via `host.docker.internal:5432`).
3. A **Google Gemini API Key** from [Google AI Studio](https://aistudio.google.com).

### Environment Setup

Copy the environment template and set your API keys:

```bash
cp .env.template .env
```

Ensure `.env` contains at minimum:
```env
GEMINI_API_KEY=your_actual_gemini_api_key
DATABASE_URL=postgresql://kitabim:kitabim@host.docker.internal:5432/kitabim-ai
REDIS_URL=redis://redis:6379/0
```
> Note: the app reads a single `DATABASE_URL` connection string (see `packages/backend-core/app/core/config.py`), not separate `POSTGRES_*` vars. `docker-compose.yml` overrides `DATABASE_URL`/`REDIS_URL` for the `backend` and `worker` containers regardless of what's in `.env`.

### Running with Docker Compose

Build images and start all local development services:

```bash
./deploy/local/rebuild-and-restart.sh all
```

This starts Redis, Neo4j, Backend API, ARQ Worker, and Frontend UI in Docker containers.

### Local Service Endpoints

| Service | Access URL | Description |
|---|---|---|
| **Web Frontend** | http://localhost:30080 | React 19 Web Application |
| **Backend API Docs** | http://localhost:30800/docs | Swagger UI for FastAPI endpoints |
| **API Health Check** | http://localhost:30800/health | Backend health check endpoint |
| **Neo4j Browser** | http://localhost:37474 | Graph Database UI (`neo4j` / password configured in `.env`) |
| **Neo4j Bolt Port** | `localhost:37687` | Bolt protocol port for Neo4j connections |

### Rebuilding Services

When making code edits, re-build specific containers using the deployment helper:

```bash
# Rebuild a single service
./deploy/local/rebuild-and-restart.sh frontend
./deploy/local/rebuild-and-restart.sh backend
./deploy/local/rebuild-and-restart.sh worker

# Inspect logs
docker compose logs -f backend
docker compose logs -f worker
```

> ⚠️ **CRITICAL LOCAL RULE**: Do not rely solely on standalone dev servers (`npm run dev`). Always verify changes using Docker Compose to guarantee build consistency.

---

## Production Deployment & Data Safety

Production releases use automated GCP Compute Engine deployment scripts.

```bash
# Deploy to GCP production VM
./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]
```

### 🔒 Data Safety Rules
1. **Never run `docker system prune --volumes`** or any command that deletes persistent storage volumes in production or local environments.
2. **Never stop or remove stateful database containers** (`neo4j`, `postgres`, `redis`) during routine application code deployments.
3. **Never execute destructive graph data reset operations** (`scripts/reset_graph_data.py`) without explicit permission (`--confirm-reset-all-graph-data`).

---

## Documentation Index

Detailed architectural specs, milestone state machine details, and stage documentation are located in `docs/main/` and `diagrams/`:

| Document | Description |
|---|---|
| [**`diagrams/README.md`**](diagrams/README.md) | Interactive Archify system architecture, pipeline sequence, workflow, and lifecycle HTML diagrams |
| [**`SYSTEM_DESIGN.md`**](docs/main/SYSTEM_DESIGN.md) | High-level system architecture, data models, and technology stack |
| [**`WORKER_DESIGN.md`**](docs/main/WORKER_DESIGN.md) | Background worker design, ARQ cron schedule, scanners, and jobs |
| [**`BOOK_PROCESSING_DIAGRAM.md`**](docs/main/BOOK_PROCESSING_DIAGRAM.md) | Comprehensive mermaid diagrams for the book ingestion pipeline |
| [**`DOCUMENT_DISCOVERY_DESIGN.md`**](docs/main/DOCUMENT_DISCOVERY_DESIGN.md) | PDF discovery scanner, duplicate detection, and book registration |
| [**`OCR_DESIGN.md`**](docs/main/OCR_DESIGN.md) | Gemini Vision interactive and Batch OCR ingestion engine |
| [**`CHUNKING_DESIGN.md`**](docs/main/CHUNKING_DESIGN.md) | Text cleaning, Uyghur script normalization, and chunk splitting |
| [**`EMBEDDING_DESIGN.md`**](docs/main/EMBEDDING_DESIGN.md) | Vector embeddings, pgvector indexing, and batch embedding mode |
| [**`SPELLCHECK_DESIGN.md`**](docs/main/SPELLCHECK_DESIGN.md) | Uyghur dictionary spell-checking and auto-correction engine |
| [**`SUMMARY_DESIGN.md`**](docs/main/SUMMARY_DESIGN.md) | Book-level summary generation for RAG book selection |
| [**`CHAT_RAG_DESIGN.md`**](docs/main/CHAT_RAG_DESIGN.md) | ChatOrchestrator, 19 ADK tools, reranking, and evaluation |
| [**`KNOWLEDGE_GRAPH_DESIGN.md`**](docs/main/KNOWLEDGE_GRAPH_DESIGN.md) | Neo4j GraphRAG entity extraction and scheduled entity resolution |
| [**`PROJECT_STRUCTURE.md`**](docs/main/PROJECT_STRUCTURE.md) | Directory structure map, module responsibilities, and key files |
| [**`REQUIREMENTS.md`**](docs/main/REQUIREMENTS.md) | Business functional requirements and user role permission matrix |
| [**`UI_CSS_STANDARD.md`**](docs/main/UI_CSS_STANDARD.md) | Frontend CSS design system and styling standards |
| [**`openapi.json`**](docs/main/openapi.json) | OpenAPI 3.0 specification for backend REST endpoints |
