# Kitabim.AI

**Kitabim.AI** is an intelligent Uyghur Digital Library. It digitizes Uyghur books through AI-powered OCR, supports editorial curation, and lets readers have natural-language conversations with the library's contents.

---

## The Problem We Solve

Uyghur books have no digital search. A reader looking for a passage, a character, or a theme in a shelf of novels has no tool to help them. Even if text is extracted by OCR, a keyword search fails — Uyghur is agglutinative, pronouns are ambiguous, and the user rarely knows which of fifty books holds the answer.

**Our solution is an agentic reading assistant** that reasons over the entire library before it answers. Instead of a single vector search, a language model agent decides which tools to call, in which order, to collect enough evidence before forming a response.

---

## AI Reading Assistant — Agentic RAG

The chat interface is powered by a **ReAct-loop agent** that runs for every question not handled by a specialized fast-path handler.

**How it works:**

1. **Context injection** — before the first LLM call, the agent's opening message is enriched with the current book ID (when reading a specific book), previously-referenced book IDs from the conversation, and a genre/category filter. This often eliminates the discovery step entirely.

2. **Tool-calling loop (up to 4 steps)** — the agent LLM decides which retrieval tools to call and in what order:
   - `search_chunks` — pgvector similarity search over indexed passages (L1 + L2 cache)
   - `search_books_by_summary` — embedding search over AI-generated book summaries, used to discover which books cover a topic when no book is in context (L3 cache)
   - `find_books_by_title` — resolve a book title named in the question to internal IDs
   - `get_book_summary` — fetch the full semantic summary for a specific book; used for plot, theme, and character questions
   - `get_current_page` — raw text of the page currently open in the reader
   - `rewrite_query` — resolve Uyghur pronouns and co-references via LLM rewrite (L0 cache)
   - `get_book_author` / `get_books_by_author` — catalog metadata lookups
   - `search_catalog` — library browsing and general listing queries

3. **Early exit** — the loop stops as soon as 8 or more unique passages are collected, or when the agent signals it has enough context.

4. **Context assembly** — collected chunks are deduplicated by `(book_id, page)`, sorted by relevance score, and capped at 15. Metadata context from catalog and author tools is prepended.

5. **Answer generation** — a separate LLM call produces a streaming response from the assembled context, with inline citations pointing to book, volume, and page.

**Specialized fast-path handlers** (enabled via `rag_fast_handlers_enabled` system config, default off) handle common patterns before the agent runs: identity and capability questions, "who wrote X?" and "what did Y write?" metadata lookups, follow-up detection (Uyghur pronouns, "چۇ" topic-shift clitic), and in-reader page/volume scoped questions.

**4-level cache** — query rewrite (L0), query embedding (L1), chunk search results (L2), book summary search results (L3) — minimizes redundant LLM and database calls within a session.

See [docs/main/AGENTIC_RAG_DESIGN.md](docs/main/AGENTIC_RAG_DESIGN.md) for the full design and [docs/main/QUESTION_ANSWERING_DIAGRAM.md](docs/main/QUESTION_ANSWERING_DIAGRAM.md) for visual pipeline diagrams.

---

## Features

### OCR & Digitization Pipeline
- Upload PDFs and extract Uyghur text page-by-page using Google Gemini Vision
- Milestone-based processing (`ocr → chunking → embedding`) with resumable jobs and real-time progress tracking
- Text cleaning tailored for Uyghur script (removes OCR noise, header/footer markers)
- Semantic chunking with overlapping windows; upsert strategy so re-chunking is idempotent
- AI-generated book summaries stored with embeddings for topic-based book discovery

### Curation Workspace
- Per-page spell-check against a Uyghur dictionary with one-click corrections
- Auto-correction rules for common OCR errors applied in bulk
- Editor role with review queue; books go public only after editorial sign-off

### User Management & Admin
- Google OAuth login; role-based access: **Admin**, **Editor**, **Reader**, **Guest**
- JWT access + refresh tokens via httpOnly cookies
- Admin dashboard with per-book pipeline stats, user management, and RAG evaluation metrics
- All AI models and thresholds configurable at runtime via `system_configs` table — no redeploy required

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

```bash
# Rebuild a single service after code changes
./deploy/local/rebuild-and-restart.sh [frontend|backend|worker]

# Logs
docker compose logs -f backend
docker compose logs -f worker
```

---

## Documentation

| Document | Contents |
|----------|----------|
| [docs/main/SYSTEM_DESIGN.md](docs/main/SYSTEM_DESIGN.md) | Architecture overview, data model, key flows, technology stack |
| [docs/main/AGENTIC_RAG_DESIGN.md](docs/main/AGENTIC_RAG_DESIGN.md) | Handler registry, agent tools, loop logic, caching, latency budget |
| [docs/main/QUESTION_ANSWERING_DIAGRAM.md](docs/main/QUESTION_ANSWERING_DIAGRAM.md) | Visual pipeline and handler routing diagrams |
| [docs/main/WORKER_DESIGN.md](docs/main/WORKER_DESIGN.md) | Event-driven pipeline, scanners, jobs, state machine |
| [docs/main/PROJECT_STRUCTURE.md](docs/main/PROJECT_STRUCTURE.md) | Full directory structure, service responsibilities, configuration reference |
| [docs/main/REQUIREMENTS.md](docs/main/REQUIREMENTS.md) | Business requirements and user role permission matrix |
| [docs/main/UI_CSS_STANDARD.md](docs/main/UI_CSS_STANDARD.md) | Frontend CSS and Tailwind conventions |
| [docs/main/SECURITY_AUDIT.md](docs/main/SECURITY_AUDIT.md) | Security controls and audit findings |
| [docs/main/openapi.json](docs/main/openapi.json) | OpenAPI 3.0 spec for the REST API |
