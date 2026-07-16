# Kitabim.AI — Project Structure Documentation (Deterministic Router Version)

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
- **Curation Workspace**: Offers spell-checking, multiple dictionaries, and editorial curation tools.
- **Deterministic Python RAG Router**: Converses with users about books, performing pgvector searches, Neo4j graph lookups, or direct PostgreSQL dictionary queries based on a deterministic decision tree.
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
    │   ├── repositories/    # Repo queries (including graph_repository.py, dictionary_repository.py)
    │   └── models.py        # SQLAlchemy entities (Book, Page, Word, Dictionary, Synonym, HistoryDictionary, NamesDictionary, EnglishUyghurDictionary)
    ├── llm/                 # Google GenAI LLM Integration Layer
    │   ├── chains.py        # TextChain & StructuredChain wrappers
    │   └── models.py        # GeminiLLM client wrapper, CircuitBreaker, RateLimiter
    ├── models/              # Pydantic validation schemas
    ├── services/            # Core business services
    │   ├── cache_service.py # Redis caching wrapper
    │   ├── rag_service.py   # RAG facade (router & telemetry records)
    │   ├── ocr_service.py   # OCR image text extraction
    │   ├── spell_check_service.py # Uyghur spell checking (against words table)
    │   ├── rag/             # RAG sub-modules
    │   │   ├── registry.py  # Priority-ordered intent handlers
    │   │   ├── context.py   # QueryContext per-request state
    │   │   ├── base_handler.py # QueryHandler interface
    │   │   ├── answer_builder.py # Answer synthesis utilities
    │   │   ├── query_rewriter.py # Pronoun resolution tool
    │   │   └── agent/       # Deterministic & ADK agent loop
    │   │       ├── prompts.py             # System instructions
    │   │       ├── config.py              # Constants
    │   │       ├── tools.py               # Registered RAG tools
    │   │       ├── adk_agent.py           # Fallback agent factory
    │   │       ├── deterministic_handler.py # Deterministic Python RAG Handler
    │   │       └── handler.py             # AgentRAGHandler invoking InMemoryRunner
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
- **Database**: PostgreSQL 17 + pgvector (embedding similarity) + Trigram indexes (dictionary search)
- **Graph DB**: Neo4j (Bolt protocol, Cypher queries)
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
- Dedicated curation tabs for managing words, dictionary definitions, synonyms, names, and historical entries.

### 2. Backend API
**Port**: 30800 (Production), 8000 (Dev)
- Implements FastAPI routes for CRUD operations, uploads, chat streaming, and user permissions.
- Exposes dictionary-related routes:
  - `/api/words` — Spellcheck vocabulary list.
  - `/api/dictionary` — Main Uyghur dictionary definition editor.
  - `/api/synonyms` — Headwords with synonym arrays.
  - `/api/names-dictionary` — Person names starting with Uyghur letters.
  - `/api/history-dictionary` — Historical terminology.
  - `/api/english-uyghur` — Bilingual dictionary.
- Enqueues pipeline jobs to Redis.
- Writes request metadata and user thumbs-up/down feedback to the `rag_evaluations` table.

### 3. Worker Service
- Background ARQ job executor.
- Runs loop scanners that lease `idle` pages atomically and run matching jobs:
  - `ocr_job`: Translates PDF images to text.
  - `chunking_job`: Semantically slices pages.
  - `embedding_job`: Creates vector embeddings.
  - `spell_check_job`: Detects misspelling corrections using the `words` table.
  - `summary_job`: Generates book summaries.
  - `knowledge_graph_job`: Populates Neo4j relationships.

---

## Key Files and Their Purpose

| File | Purpose |
|------|---------|
| `packages/backend-core/app/llm/models.py` | Contains `GeminiLLM` class satisfying `LLMProvider` protocol, wraps google-genai client, and applies `CircuitBreaker` and `RedisRateLimiter` logic. |
| `packages/backend-core/app/llm/chains.py` | Implements `TextChain` formatting templates and `.ainvoke()`/`.astream()` wrappers to maintain compatibility with downstream answer builders. |
| `packages/backend-core/app/services/rag/agent/deterministic_handler.py` | Implements `DeterministicRAGHandler` which parses inputs using a unified LLM analyzer call and routes queries through a fixed, high-performance Python decision tree. |
| `packages/backend-core/app/services/rag/agent/tools.py` | Standardized Python function definitions wrapping repo lookups, pgvector similarity, Neo4j Graph relations, and multi-dictionary database queries. |
| `packages/backend-core/app/db/repositories/dictionary_repository.py` | Executes SQL exact, wildcard, and pg_trgm similarity queries to lookup words, definitions, synonyms, names, and translations. |
