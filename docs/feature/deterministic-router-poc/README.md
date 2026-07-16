# Kitabim.ai Documentation

**Last Updated:** 2026-06-27

Welcome to the Kitabim.ai documentation. Kitabim.ai is the definitive intelligent knowledge base for Uyghur literature, history, and culture — targeting the complete corpus of Uyghur-language publications. This directory contains comprehensive technical documentation for the platform.

---

## 📚 Documentation Index

### **🏗️ Architecture & Design**

| Document | Description | Status |
|----------|-------------|--------|
| [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) | High-level system architecture and design decisions | ✅ Current |
| [WORKER_DESIGN.md](WORKER_DESIGN.md) | Event-driven pipeline architecture and worker components | ✅ Current |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Monorepo structure and codebase organization | ✅ Current |
| [RAG_DETERMINISTIC_ROUTER_DESIGN.md](RAG_DETERMINISTIC_ROUTER_DESIGN.md) | Deterministic Python RAG router — signal extraction, intent paths, dictionary routing | ✅ Current |
| [AGENTIC_RAG_DESIGN.md](AGENTIC_RAG_DESIGN.md) | Fallback agentic RAG design — Google ADK loop, 16 tools, context grading | ✅ Current |
| [QUESTION_ANSWERING_DIAGRAM.md](QUESTION_ANSWERING_DIAGRAM.md) | Visual pipeline diagram — deterministic router and fallback agentic RAG | ✅ Current |
| [BOOK_PROCESSING_DIAGRAM.md](BOOK_PROCESSING_DIAGRAM.md) | Visual diagrams of the book processing pipeline | ✅ Current |

### **⚡ Performance & Optimization**

| Document | Description | Status |
|----------|-------------|--------|
| Pipeline optimizations | MAX_PARALLEL_PAGES=6, EMBED_BATCH_SIZE=50 — see `.env.template` | ✅ Applied (env vars only) |
| Redis caching strategy | Redis caching for books, configs, proverbs — see `.env.template` CACHE_TTL_* vars | ✅ Complete |

### **🤖 AI & RAG**

| Document | Description | Status |
|----------|-------------|--------|
| [RAG_DETERMINISTIC_ROUTER_DESIGN.md](RAG_DETERMINISTIC_ROUTER_DESIGN.md) | Deterministic router, intent classification, dictionary path selection | ✅ Current |
| [AGENTIC_RAG_DESIGN.md](AGENTIC_RAG_DESIGN.md) | Fallback ReAct loop, 16 tools, Google ADK loop, grading | ✅ Current |
| [QUESTION_ANSWERING_DIAGRAM.md](QUESTION_ANSWERING_DIAGRAM.md) | Full pipeline visual diagram — current state | ✅ Current |

### **🔧 Features & Implementation**

| Document | Description | Status |
|----------|-------------|--------|
| Hierarchical RAG with book summaries | `book_summaries` table + `summary_scanner` + `summary_job` | ✅ Implemented |
| Knowledge Graph with Neo4j | Neo4j + `graph_scanner` + `knowledge_graph_job` | ✅ Implemented |
| Multi-Dictionary Workspace | Tables for words, definitions, synonyms, names, history, and translations | ✅ Implemented |
| [UI_CSS_STANDARD.md](UI_CSS_STANDARD.md) | Frontend CSS conventions and Tailwind standards | ✅ Current |

### **📋 Requirements & Specifications**

| Document | Description | Status |
|----------|-------------|--------|
| [REQUIREMENTS.md](REQUIREMENTS.md) | Product requirements and feature specifications | ✅ Current |
| [openapi.json](openapi.json) | OpenAPI specification for REST API | ✅ Generated |

---

## 🎯 Quick Start Guides

### **For Developers**

1. **Understanding the System:**
   - Start with [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for architecture overview
   - Read [WORKER_DESIGN.md](WORKER_DESIGN.md) to understand the pipeline
   - Check [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for codebase layout

2. **Making Changes:**
   - Performance: See `.env.template` for pipeline tuning vars (MAX_PARALLEL_PAGES, EMBED_BATCH_SIZE, CACHE_TTL_*)
   - UI: Follow [UI_CSS_STANDARD.md](UI_CSS_STANDARD.md) conventions

---

## 🏗️ Current System State (June 2026)

### Technology Stack
- **Database:** PostgreSQL 17 with pgvector + Neo4j graph database
- **Cache/Queue:** Redis 7
- **Backend:** Python 3.13 + FastAPI + SQLAlchemy
- **Frontend:** React 19 + Vite 6 + TypeScript 5.8
- **Worker:** ARQ (async Redis queue)
- **AI:** Google Gemini 3.5 Flash & 3.0 Flash Preview (OCR, embeddings, router query analysis, chat)
- **Storage:** Google Cloud Storage
- **Deployment:** Docker Compose on GCP VM (e2-standard-2)

### Recent Major Changes
- ✅ **2026-06-27:** Multi-Dictionary & Curation Workspace — implemented dedicated SQL tables for words (spell check), definitions, synonyms, historical terms, person names, and English-Uyghur translations. Added curation panels in the admin dashboard and integrated them as Path B (Dictionary / Language Sources) in the Deterministic RAG Router.
- ✅ **2026-06-19:** Structured query signal extraction with unified LLM analyzer call, coreference resolution, and inline composite query decomposition in a single LLM pass.
- ✅ **2026-06-11:** Google ADK & google-genai Migration — migrated to Google ADK (for agent loops) and first-party google-genai SDK (for direct LLM tasks). Removed background evaluation jobs and simplified stats to focus on user feedback.
- ✅ **2026-05-21:** GraphRAG with Neo4j Integration — added `query_knowledge_graph` tool (16 tools total), registered `knowledge_graph_job` running concurrently on book readiness to extract and index semantic entities and relationship networks in Neo4j database.
- ✅ **2026-05-15:** Fast-path handlers permanently removed — `DeterministicRAGHandler` is the primary handler, routing queries deterministically; `AgentRAGHandler` is the fallback.
