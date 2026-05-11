# Kitabim.AI

**Kitabim.AI** is an intelligent Uyghur Digital Library platform. It combines AI-powered OCR, a curation workflow, and a RAG-powered reading assistant to make Uyghur books searchable and interactive.

---

## Features

### OCR & Digitization Pipeline
- Upload PDFs and extract Uyghur text page-by-page using **Google Gemini Vision**
- Milestone-based processing pipeline (`ocr → chunking → embedding → spell_check`) with resumable jobs and real-time progress tracking
- Text cleaning tailored for Uyghur script (removes OCR noise, header/footer markers)
- Semantic chunking with overlapping windows for high-recall retrieval

### Curation Workspace
- Per-page spell-check against a Uyghur dictionary with one-click corrections
- Auto-correction rules for common OCR errors applied in bulk
- Editor role with review queue; books go public only after editorial sign-off

### AI Reading Assistant (Agentic RAG)
- Per-book and global library chat powered by **Gemini** and **pgvector** similarity search
- **Agentic retrieval loop** — always-on: an LLM agent runs a ReAct loop (up to 4 steps, early-exit at 8 chunks) and decides which of 7 tools to call: chunk search, summary search, title lookup, author lookup, catalog search, and pronoun rewriting
- **Context injection**: the agent's first message includes the current book ID, context book IDs, and category filter — the agent skips book-discovery entirely when the context is known
- **Intent routing**: 8 specialized handlers cover metadata queries (author, volume info), follow-up detection, and page/volume-scoped questions before reaching the agentic loop. Follow-up detection catches Uyghur pronouns, explicit markers, and the "چۇ" topic-shift clitic
- **4-level caching**: query rewrite (L0), query embedding (L1), chunk search results (L2), summary search results (L3)
- Streaming responses via SSE; `used_book_ids` returned per response for frontend context tracking
- Per-user daily chat limits with role-based overrides

### User Management
- Google OAuth login; role-based access: **Admin**, **Editor**, **Reader**, **Guest**
- JWT access + refresh tokens via httpOnly cookies
- Admin dashboard with per-book pipeline stats, user management, and RAG evaluation metrics

### Infrastructure
- All AI models and thresholds configurable at runtime via `system_configs` (no redeploy needed)
- Redis-backed circuit breaker protecting all LLM and external API calls
- 3-tier caching layer (Redis) with per-key TTLs and cache-miss logging
- Transactional outbox pattern for reliable pipeline event dispatch

---

## Architecture

```
apps/frontend/          React 19 + Vite SPA (RTL, Uyghur keyboard support)
services/backend/       FastAPI REST API
services/worker/        ARQ background worker (OCR, chunking, embedding, summaries)
packages/backend-core/  Shared Python code (models, repositories, RAG services)
```

All services share `packages/backend-core`. The worker and API never duplicate database or AI logic.

For a full architecture diagram and data model see [docs/main/SYSTEM_DESIGN.md](docs/main/SYSTEM_DESIGN.md).  
For directory structure and key files see [docs/main/PROJECT_STRUCTURE.md](docs/main/PROJECT_STRUCTURE.md).  
For the agentic RAG design see [docs/main/AGENTIC_RAG_DESIGN.md](docs/main/AGENTIC_RAG_DESIGN.md).  
For the current question answering pipeline diagram see [docs/main/QUESTION_ANSWERING_DIAGRAM.md](docs/main/QUESTION_ANSWERING_DIAGRAM.md).

---

## Local Development (Docker Compose)

### Prerequisites

- Docker Desktop (or Docker Engine + Docker Compose)
- A `GEMINI_API_KEY` from [Google AI Studio](https://aistudio.google.com)

### Quickstart

**1. Configure environment**
```bash
cp .env.template .env
# Fill in GEMINI_API_KEY and other required values
```

**2. Start all services**
```bash
./deploy/local/rebuild-and-restart.sh all
```

**3. Access**

| Service | URL |
|---------|-----|
| Web UI | http://localhost:30080 |
| API + Swagger | http://localhost:30800/docs |
| Health check | http://localhost:30800/health |

PostgreSQL runs on host port `5532`. `DATABASE_URL` inside Docker uses the `postgres` service hostname on port `5432`.

### Common commands

```bash
# Rebuild a single service
./deploy/local/rebuild-and-restart.sh [frontend|backend|worker]

# Logs
docker compose logs -f backend
docker compose logs -f worker

# Status
docker compose ps

# Stop
docker compose down
```

### Tests

```bash
# Frontend
npm test

# Backend
python3.13 -m pytest services/backend/tests
```

---

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 6, TypeScript 5.8, Tailwind CSS 3.4, pdf.js |
| API | FastAPI, Python 3.13, Pydantic, asyncpg |
| Database | PostgreSQL 17 + pgvector (3072-dim embeddings, HNSW index) |
| Caching / Queue | Redis 7 + ARQ |
| AI | Google Gemini (OCR, embeddings, chat, agentic tool calling) |
| AI Framework | LangChain + langchain-google-genai |
| Storage | Google Cloud Storage (private PDF bucket, public covers CDN) |
| Production | GCE VM + Docker Compose + Artifact Registry + nginx |

---

## Production Deployment

```bash
# Build, push images, sync config, and deploy to the production VM
./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]
```

The script builds multi-arch images, pushes to Artifact Registry, syncs `docker-compose.yml`, `.env`, and the nginx config to the VM, then performs a zero-downtime rolling restart with a health-check gate.

See [docs/main/PRODUCTION_DEPLOYMENT.md](docs/main/PRODUCTION_DEPLOYMENT.md) for the full runbook.

> **Note:** `deploy/gcp/` is gitignored — production scripts and config are kept local only.

---

## Key Runtime Configuration (`system_configs` table)

These values are changed via the admin API at runtime — no redeploy required.

| Key | Purpose |
|-----|---------|
| `gemini_chat_model` | Model used for answer generation |
| `gemini_embedding_model` | Model used for chunk and query embeddings |
| `gemini_agent_loop_model` | Fast model for agent tool-calling decisions |
| `rag_eval_enabled` | `"true"` writes per-request metrics to `rag_evaluations` |
| `summary_similarity_threshold` | Minimum score for summary-based book selection |
