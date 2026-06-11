# Kitabim.AI — Project Structure Documentation (Google ADK Version)

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Architecture](#repository-architecture)
3. [Directory Structure](#directory-structure)
4. [Technology Stack](#technology-stack)
5. [Service Components](#service-components)
6. [Data Flow](#data-flow)
7. [Configuration Management](#configuration-management)
8. [Development Workflow](#development-workflow)
9. [Deployment Architecture](#deployment-architecture)
10. [Key Files and Their Purpose](#key-files-and-their-purpose)

---

## Overview

**Kitabim.AI** is a monorepo-based digital library and intelligent query engine for Uyghur literature. It features:

- **OCR Ingestion Pipeline**: Extracts text page-by-page from PDFs using Gemini Vision.
- **Curation Workspace**: Offers spell-checking, dictionaries, and editorial curation tools.
- **ADK-Backed Agentic RAG**: Converses with users about books, performing pgvector searches and Memgraph graph lookups.
- **User Identity**: Manages JWT authentication and social logins.

---

## Repository Architecture

```
kitabim-ai/
├── apps/                    # Application layer
│   └── frontend/           # React/Vite TypeScript frontend SPA
├── packages/               # Shared packages
│   └── backend-core/      # Shared Python backend logic (Shared Core)
├── services/              # Microservices
│   ├── backend/          # FastAPI HTTP REST API service
│   └── worker/           # ARQ background task processor
├── deploy/                # Deployment & Infrastructure
│   ├── local/            # Local Docker Compose rebuild scripts
│   └── gcp/              # Production deploy scripts
├── scripts/               # Operational/diagnostic scripts
├── data/                  # Persistent data directory (uploads/covers)
└── docker-compose.yml     # Primary local environment launcher
```

---

## Directory Structure

### `/packages/backend-core` - Shared Logic & Data Layer

```
packages/backend-core/
└── app/
    ├── core/                # System configuration and prompts
    │   ├── config.py        # Settings loader
    │   ├── cache_config.py  # Redis TTLs and keys
    │   └── prompts.py       # Base prompt templates
    ├── db/                  # Database connections, ORM models, repos
    │   ├── postgres.py      # SQLAlchemy connection
    │   ├── repositories/    # Repo queries (including graph_repository.py)
    │   └── models.py        # SQLAlchemy entities
    ├── llm/                 # Google GenAI LLM Integration Layer
    │   ├── chains.py        # TextChain & StructuredChain wrappers
    │   └── models.py        # GeminiLLM client wrapper, CircuitBreaker, RateLimiter
    ├── models/              # Pydantic validation schemas
    ├── services/            # Core business services
    │   ├── cache_service.py # Redis caching wrapper
    │   ├── rag_service.py   # RAG facade (router & telemetry records)
    │   ├── ocr_service.py   # OCR image text extraction
    │   ├── rag/             # RAG sub-modules
    │   │   ├── registry.py  # Priority-ordered intent handlers
    │   │   ├── context.py   # QueryContext per-request state
    │   │   ├── base_handler.py # QueryHandler interface
    │   │   ├── answer_builder.py # Answer synthesis utilities
    │   │   ├── query_rewriter.py # Pronoun resolution tool
    │   │   └── agent/       # ADK-based agent loop
    │   │       ├── prompts.py    # System instructions
    │   │       ├── config.py     # Constants
    │   │       ├── tools.py      # 11 registered tools
    │   │       ├── adk_agent.py  # Agent factory
    │   │       └── handler.py    # AgentRAGHandler invoking InMemoryRunner
    │   └── book_milestone_service.py
    ├── utils/               # Text processing, citation parsing, observability
    ├── queue.py             # ARQ client interface
    └── jobs.py              # Background job routing
```

---

## Technology Stack

### Frontend
- **Framework**: React 19
- **Build**: Vite 6, TypeScript 5.8
- **Styles**: Tailwind CSS 3.4
- **PDF**: pdf.js (Client-side rendering)

### Backend
- **Framework**: FastAPI (Python 3.13)
- **Database**: PostgreSQL 17 + pgvector (embedding similarity)
- **Graph DB**: Memgraph (Bolt protocol, Cypher queries)
- **Cache/Queue**: Redis 7 + ARQ (task execution)
- **AI Stack**:
  - **Google ADK (`google-adk`)**: Manages the agentic ReAct loop and tool-calling execution.
  - **google-genai SDK (`google-genai`)**: Handles direct LLM text generation, OCR, summaries, KG entity extraction, and embedding generations.

- **PDF Parsing**: PyMuPDF

---

## Service Components

### 1. Frontend SPA
**Port**: 30080 (Production), 5173 (Dev)
- User interface for reading, chat, curation, and admin dashboards.
- Integrates Google, Facebook, and X OAuth logins.
- Displays streaming agent steps (`planning`, `decomposing`, `thinking`, `tool`, `grading`) alongside answer chunks.

### 2. Backend API
**Port**: 30800 (Production), 8000 (Dev)
- Implements FastAPI routes for CRUD operations, uploads, chat streaming, and user permissions.
- Enqueues pipeline jobs to Redis.
- Writes request metadata and user thumbs-up/down feedback to the `rag_evaluations` table.

### 3. Worker Service
- Background ARQ job executor.
- Runs loop scanners that lease `idle` pages atomically and run matching jobs:
  - `ocr_job`: Translates PDF images to text.
  - `chunking_job`: Semantically slices pages.
  - `embedding_job`: Creates vector embeddings.
  - `spell_check_job`: Detects misspelling corrections.
  - `summary_job`: Generates book summaries.
  - `knowledge_graph_job`: Populates Memgraph relationships.
- *Background Ragas evaluation jobs are deleted.*

---

## Key Files and Their Purpose

| File | Purpose |
|------|---------|
| `packages/backend-core/app/llm/models.py` | Contains `GeminiLLM` class satisfying `LLMProvider` protocol, wraps google-genai client, and applies `CircuitBreaker` and `RedisRateLimiter` logic. |
| `packages/backend-core/app/llm/chains.py` | Implements `TextChain` formatting templates and `.ainvoke()`/`.astream()` wrappers to maintain compatibility with downstream answer builders. |
| `packages/backend-core/app/services/rag/agent/adk_agent.py` | Agent factory creating the ADK `Agent` with tools list and system instructions. |
| `packages/backend-core/app/services/rag/agent/handler.py` | Runs `AgentRAGHandler`. Orchestrates the planning/decompose pre-steps, calls ADK `InMemoryRunner`, parses tool calls and responses, and runs grading/synthesis post-steps. |
| `packages/backend-core/app/services/rag/agent/tools.py` | Standardized Python function definitions decorated as ADK-callable tools, wrapping repo lookups, pgvector, and Memgraph Bolt connections. |
