# Kitabim.AI

**Kitabim.AI** is the definitive intelligent knowledge base for Uyghur literature, history, and culture — semantically indexing books published in the Uyghur language and making that knowledge explorable through AI-powered conversation.

---

## Mission & Scale

Uyghur is spoken by millions yet remains severely underrepresented in the digital world. Kitabim.AI is building the most comprehensive and authentic Uyghur-language knowledge base ever assembled, targeting the complete corpus of Uyghur-language publications across literature, history, poetry, science, and culture.

**Target:** books published in Uyghur — the complete written record of a civilization.

This is not a search index or a catalogue. It is a living, queryable knowledge base where the entire body of Uyghur written knowledge can be explored through natural-language conversation.

---

## The Problem We Solve

Uyghur literature, history, and culture exist almost entirely in physical form. Millions of speakers have no way to search, discover, or query the written knowledge of their own civilization — and as physical books become scarce, that knowledge risks being lost entirely. Even where text can be extracted by OCR, a keyword search fails: Uyghur is agglutinative, pronouns are ambiguous, and a reader rarely knows which of hundreds of books holds the answer they need.

**Our solution is a knowledge-base agent** that reasons over the entire corpus before it answers. Instead of a single vector search, a language-model agent decides which tools to call, in which order, to collect enough evidence before forming a response.

---

## Knowledge Base Agent — Agentic RAG with Google ADK

The query assistant interface runs an **agentic loop built on Google ADK**. The system supports two execution pathways: **`ChatOrchestrator`** (ADK-native two-agent pipeline with persisted conversation history) and **`RAGService` / `HandlerRegistry`** (gated between `DeterministicRAGHandler` and `LLMRoutedRAGHandler`).

```mermaid
flowchart TD
    Q(["User Question + Context"]) --> ROUTE{"Has conversationId or<br/>use_adk_chat_v2?"}

    ROUTE -- Yes (Default for Stream) --> ORCH["ChatOrchestrator Pipeline<br/>(Persisted Conversation History)"]
    ORCH --> RET_AGENT["[LLM] Retrieval Agent<br/>(Google ADK + 19 Tools)"]
    RET_AGENT --> GRADE_ORCH["Context Grading"]
    GRADE_ORCH --> ANS_AGENT["[LLM] Answer Agent<br/>(Streaming Synthesis + Citations)"]
    ANS_AGENT --> SAVE["Persist Turn & Return"]

    ROUTE -- No --> REG["RAGService / HandlerRegistry"]
    REG --> DET_CHECK{"use_deterministic_router?"}
    DET_CHECK -- Yes --> DET["DeterministicRAGHandler<br/>(ADK Workflow Graph)"]
    DET_CHECK -- No --> LLM_RAG["LLMRoutedRAGHandler<br/>(ADK ReAct Loop + 19 Tools)"]
    DET --> GRADE_REG["Context Grading & Synthesis"]
    LLM_RAG --> GRADE_REG
    GRADE_REG --> RETURN["Return Answer"]
```

**How Agentic RAG works:**

1. **Preprocessing & Signal Extraction**
   - **Intent detection** — classifies page-specific questions, metadata queries, dictionary lookups, scripture questions, and content search.
   - **Query Decomposition** — for queries containing multiple questions, an LLM call splits them into up to 4 self-contained sub-questions so context is retrieved for each.
   - **Co-reference Resolution** — resolves Uyghur pronouns and follow-up markers using conversation history (`rewrite_query`).

2. **Context Injection** — before the first tool call, the query is enriched with a `[Context]` block including the current book ID (if reading in reader mode), previously-referenced book IDs from conversation history, and category filters.

3. **Google ADK Reasoning & Tool Execution** — the agent executes a reasoning loop using Google ADK (`google-adk`), choosing from **19 specialized retrieval, catalog, dictionary, and Quran tools**:
   - **Content Retrieval**: `search_chunks` (pgvector similarity search), `search_books_by_summary` (summary embedding search), `find_books_by_title`, `get_book_summary`, `get_current_page` (reader page text), `rewrite_query`, `get_sister_volumes`.
   - **Catalog & Metadata**: `get_book_author`, `get_books_by_author`, `search_catalog`.
   - **Dictionary & Language**: `lookup_uyghur_word`, `lookup_history_term`, `translate_english_to_uyghur`, `check_word_spelling`, `lookup_uyghur_name`, `search_language_sources`, `lookup_proverbs`, `lookup_synonyms`.
   - **Scripture**: `search_quran` (Surah/Ayah vector search and translation lookup).

4. **Post-Processing (Grading & Synthesis)**
   - **Deduplication and Grading** — merges retrieved passages and filters low-relevance chunks using relative score thresholds.
   - **Answer Synthesis** — generates a streaming response with inline citations pointing to source books, volumes, and page numbers.

---

## Core Technologies and AI Stack

The platform is built on specialized database, AI, and backend technologies:

- **Google ADK (`google-adk`)**: Serves as the agentic reasoning engine, coordinating the ReAct loop and automated tool dispatching for the RAG assistant.
- **google-genai SDK (`google-genai`)**: Used for all direct LLM generation and embedding calls across the application (OCR pipeline, summarization, entity extraction, text/structured chains).
- **Neo4j**: A graph database storing semantic networks of entities (Persons, Locations, Organizations, Works, Events) extracted from books, queried using Cypher for GraphRAG.
- **pgvector (PostgreSQL)**: PostgreSQL with `pgvector` stores page-chunk embeddings (Gemini Embedding v2) and performs similarity searches.
- **ARQ (Redis)**: Asynchronous task queue running background processing pipelines (OCR, chunking, embedding, summary extraction, and Neo4j ingestion).
- **FastAPI**: Asynchronous Python web framework providing API routes, user auth, rate limits, and streaming responses.

---

## Features

### OCR & Digitization Pipeline
- Upload PDFs and extract Uyghur text page-by-page using Google Gemini Vision.
- Milestone-based processing (`ocr → chunking → embedding`) with resumable jobs and real-time progress tracking.
- Text cleaning tailored for Uyghur script (removes OCR noise, header/footer markers).
- Semantic chunking with overlapping windows; upsert strategy so re-chunking is idempotent.
- AI-generated book summaries stored with embeddings for topic-based book discovery.
- **Knowledge Graph Ingestion (GraphRAG)**: Extracts Person, Location, Organization, Work, and Event entities and their semantic relationships from book chunks, building a knowledge network in Neo4j.

### Curation Workspace
- Per-page spell-check against a Uyghur dictionary with one-click corrections.
- Auto-correction rules for common OCR errors applied in bulk.
- Editor role with review queue; books go public only after editorial sign-off.

### User Management & Admin
- OAuth login (Google, Facebook, X).
- Role-based access: **Admin**, **Editor**, **Reader**, **Guest**.
- JWT access + refresh tokens via httpOnly cookies.
- Admin dashboard with per-book pipeline stats, user management, and user feedback analytics.
- All AI models and thresholds are configurable at runtime via `system_configs` table — no redeploy required.

---

## Quick Start (Docker Compose)

**Prerequisites:** Docker Desktop and a `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com).

```bash
cp .env.template .env
# Fill in GEMINI_API_KEY and other required values

./deploy/local/rebuild-and-restart.sh all
```

| Service | URL |
|---------|-----|
| Web UI | http://localhost:30080 |
| API + Swagger | http://localhost:30800/docs |
| Health check | http://localhost:30800/health |
| Neo4j Bolt | localhost:37687 |
| Neo4j Browser (UI) | http://localhost:37474 |

```bash
# Rebuild a single service after code changes
./deploy/local/rebuild-and-restart.sh [frontend|backend|worker]

# Logs
docker compose logs -f backend
docker compose logs -f worker
```


## Documentation

All architectural and design documents are located under the `docs/` directory.

| Document | Contents |
|----------|----------|
| [docs/main/SYSTEM_DESIGN.md](docs/main/SYSTEM_DESIGN.md) | Architecture overview, data model, key flows, technology stack |
| [docs/main/WORKER_DESIGN.md](docs/main/WORKER_DESIGN.md) | Event-driven pipeline, scanners, jobs, state machine |
| [docs/main/BOOK_PROCESSING_DIAGRAM.md](docs/main/BOOK_PROCESSING_DIAGRAM.md) | Visual diagrams of the book processing pipeline |
| [docs/main/DOCUMENT_DISCOVERY_DESIGN.md](docs/main/DOCUMENT_DISCOVERY_DESIGN.md) | Manual upload + GCS bucket discovery, duplicate detection |
| [docs/main/OCR_DESIGN.md](docs/main/OCR_DESIGN.md) | Gemini Vision OCR, soft-skip retries, batch OCR mode |
| [docs/main/CHUNKING_DESIGN.md](docs/main/CHUNKING_DESIGN.md) | Recursive character splitting, chunk upsert strategy |
| [docs/main/EMBEDDING_DESIGN.md](docs/main/EMBEDDING_DESIGN.md) | Gemini embeddings, pgvector storage, batch embedding mode |
| [docs/main/SPELLCHECK_DESIGN.md](docs/main/SPELLCHECK_DESIGN.md) | Spellcheck + auto-correct — independent quality layer |
| [docs/main/SUMMARY_DESIGN.md](docs/main/SUMMARY_DESIGN.md) | Book-level summary generation for RAG book routing |
| [docs/main/CHAT_RAG_DESIGN.md](docs/main/CHAT_RAG_DESIGN.md) | ChatOrchestrator + RAGService/HandlerRegistry — retrieval, agent tools, reranking, judge scoring |
| [docs/main/KNOWLEDGE_GRAPH_DESIGN.md](docs/main/KNOWLEDGE_GRAPH_DESIGN.md) | Entity/relationship extraction into Neo4j (GraphRAG) |
| [docs/main/PROJECT_STRUCTURE.md](docs/main/PROJECT_STRUCTURE.md) | Full directory structure, service responsibilities, configuration reference |
| [docs/main/REQUIREMENTS.md](docs/main/REQUIREMENTS.md) | Business requirements and user role permission matrix |
| [docs/main/UI_CSS_STANDARD.md](docs/main/UI_CSS_STANDARD.md) | Frontend CSS and Tailwind conventions |
| [docs/main/openapi.json](docs/main/openapi.json) | OpenAPI 3.0 spec for the REST API |
