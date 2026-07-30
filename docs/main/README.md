# Kitabim.ai Documentation

Kitabim.ai is a monorepo platform for OCR digitization, editorial curation, and RAG-powered conversational reading of Uyghur-language books. This directory contains the technical documentation for the platform.

---

## Documentation Index

### Architecture & Design

| Document | Contents |
|----------|----------|
| [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) | System architecture, data model, AI model configuration, key flows |
| [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) | Monorepo layout, service responsibilities, worker jobs/scanners, key files |
| [WORKER_DESIGN.md](WORKER_DESIGN.md) | Event-driven pipeline architecture, state machine, worker components |
| [book_processing_diagram.md](book_processing_diagram.md) | Visual diagrams of the book processing pipeline |

### Pipeline Stages

| Document | Contents |
|----------|----------|
| [DOCUMENT_DISCOVERY_DESIGN.md](DOCUMENT_DISCOVERY_DESIGN.md) | Manual upload + GCS bucket discovery, duplicate detection, DOCX vs. PDF entry paths |
| [OCR_DESIGN.md](OCR_DESIGN.md) | Gemini Vision OCR, soft-skip retries, table-of-contents detection, batch OCR mode |
| [CHUNKING_DESIGN.md](CHUNKING_DESIGN.md) | Recursive character splitting, chunk upsert strategy, TOC page handling |
| [EMBEDDING_DESIGN.md](EMBEDDING_DESIGN.md) | Gemini embedding generation, pgvector storage, batch embedding mode |
| [SPELLCHECK_DESIGN.md](SPELLCHECK_DESIGN.md) | Spellcheck + auto-correct — independent quality layer, dictionary-based corrections |
| [SUMMARY_DESIGN.md](SUMMARY_DESIGN.md) | Book-level summary generation + embedding for RAG book routing |
| [CHAT_RAG_DESIGN.md](CHAT_RAG_DESIGN.md) | `ChatOrchestrator` and `RAGService`/`HandlerRegistry` — retrieval, Google ADK agent tools, reranking, judge scoring, tool reference |
| [KNOWLEDGE_GRAPH_DESIGN.md](KNOWLEDGE_GRAPH_DESIGN.md) | Entity/relationship extraction and entity resolution into Neo4j (GraphRAG) |

Two independent chat pipelines exist today: `ChatOrchestrator` (`packages/backend-core/app/services/chat/`) persists conversation history and is the default for the streaming endpoint; `RAGService`/`HandlerRegistry` (both covered in [CHAT_RAG_DESIGN.md](CHAT_RAG_DESIGN.md)) has no conversation persistence and is used otherwise. See [SYSTEM_DESIGN.md §6B](SYSTEM_DESIGN.md) for how the two relate.

### Other

| Document | Contents |
|----------|----------|
| [NEO4J_CONNECTION.md](NEO4J_CONNECTION.md) | Neo4j graph schema, connection settings, local/production access |
| [UI_CSS_STANDARD.md](UI_CSS_STANDARD.md) | Frontend Tailwind conventions, dark mode, RTL handling |
| [REQUIREMENTS.md](REQUIREMENTS.md) | Product requirements, user roles/permissions, feature specifications |
| [openapi.json](openapi.json) | Generated OpenAPI specification for the REST API |

---

## Quick Start for Developers

1. **Understanding the system:**
   - Start with [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md) for the architecture overview.
   - Read [WORKER_DESIGN.md](WORKER_DESIGN.md) to understand the book processing pipeline.
   - Check [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) for codebase layout and where things live.
   - For the chat assistant specifically, read [CHAT_RAG_DESIGN.md](CHAT_RAG_DESIGN.md).

2. **Local development:**
   - Rebuild and restart: `./deploy/local/rebuild-and-restart.sh [all|backend|worker|frontend]`
   - Frontend: http://localhost:30080 · Backend API: http://localhost:30800 · Neo4j Browser: http://localhost:37474
   - Worker logs: `docker compose logs -f worker` · Backend logs: `docker compose logs -f backend`

3. **Production:**
   - Deploy: `./deploy/gcp/scripts/deploy.sh [tag]`
   - Deployment layout: `deploy/gcp/`

---

## Technology Stack

- **Database:** PostgreSQL with pgvector (HNSW index on `chunks`, IVFFlat on `book_summaries`) + Neo4j graph database
- **Cache/Queue:** Redis
- **Backend:** Python 3.13, FastAPI, SQLAlchemy 2.0 (async) + asyncpg
- **Worker:** ARQ (async Redis queue)
- **Frontend:** React 19, Vite, TypeScript, Tailwind CSS
- **AI:** Google Gemini — models are read from `system_configs` at request time, never hardcoded (see [SYSTEM_DESIGN.md](SYSTEM_DESIGN.md#7-gemini-integration-strategy) for current defaults). Built on `google-genai` (direct generation/embeddings) and `google-adk` (both RAG handlers' tool execution).
- **Storage:** Google Cloud Storage
- **Deployment:** Docker Compose on GCP

---

## Related Resources

- [Project root README](../../README.md)
- [FastAPI docs](https://fastapi.tiangolo.com/)
- [Google ADK docs](https://github.com/google/adk-python)
- [Google GenAI SDK docs](https://github.com/googleapis/python-genai)
- [Gemini API docs](https://ai.google.dev/gemini-api/docs)
- [pgvector docs](https://github.com/pgvector/pgvector)
