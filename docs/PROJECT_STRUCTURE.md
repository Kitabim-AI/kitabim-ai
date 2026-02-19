# Kitabim.AI — Project Structure Documentation

> **Generated:** 2026-02-14
> **Purpose:** Comprehensive overview of the codebase structure, architecture, and organization

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

**Kitabim.AI** is a monorepo-based intelligent Uyghur Digital Library platform that provides:

- **OCR Pipeline**: AI-powered extraction of Uyghur text from PDF documents using Google Gemini
- **Digital Curation**: Tools for editors to review, correct, and manage digitized content
- **RAG-Powered Reading**: AI chat assistant for answering questions about books using semantic search
- **User Management**: Role-based access control (Admin, Editor, Reader, Guest)

The project is structured as a **monorepo** with clear separation between frontend, backend, shared packages, and infrastructure.

---

## Repository Architecture

### Monorepo Structure

```
kitabim-ai/
├── apps/                    # Application layer
│   └── frontend/           # React/Vite UI application
├── packages/               # Shared code packages
│   ├── backend-core/      # Shared Python backend logic
│   └── shared/            # Shared TypeScript types/utils
├── services/              # Microservices
│   ├── backend/          # FastAPI REST API service
│   └── worker/           # ARQ background job worker
├── k8s/                  # Kubernetes manifests
│   └── local/           # Local development k8s config
├── scripts/             # Utility scripts and migrations
├── data/                # Processing Cache (gitignored)
│   ├── uploads/        # Transient PDF storage during OCR
│   └── covers/         # Transient cover storage
└── docs/               # Documentation
```

### Design Principles

1. **Shared Core Logic**: Both backend API and worker share code via `packages/backend-core`
2. **Clear Boundaries**: Frontend, backend, and worker are separate services with well-defined interfaces
3. **Local-First Development**: Kubernetes manifests for consistent local dev environment
4. **Database-Centric**: PostgreSQL with pgvector for all persistence and vector search
5. **Queue-Based Processing**: Redis + ARQ for async/background OCR and embedding jobs

---

## Directory Structure

### `/apps/frontend` - React/Vite UI

```
apps/frontend/
├── src/
│   ├── components/           # React components
│   │   ├── admin/           # User and book management
│   │   ├── auth/            # Login/OAuth components
│   │   ├── chat/            # AI chat interface
│   │   ├── common/          # Reusable UI components
│   │   ├── layout/          # App shell and navigation
│   │   ├── library/         # Book browsing and search
│   │   ├── reader/          # Book reader with RTL support
│   │   └── spell-check/     # OCR correction interface
│   ├── context/             # React context providers
│   ├── hooks/               # Custom React hooks
│   ├── services/            # API clients and helpers
│   └── tests/               # Frontend tests
├── dist/                    # Build output
├── nginx.conf              # Nginx config for production
├── AGENTS.md               # AI agent guidance
└── package.json
```

**Key Technologies:**
- React 19
- Vite 6
- TypeScript 5.8
- Tailwind CSS 3.4 (CDN)
- Lucide React (icons)
- pdf.js (PDF rendering)
- Vitest (testing)

### `/packages/backend-core` - Shared Python Backend

```
packages/backend-core/
└── app/
    ├── api/                 # API endpoints
    │   └── endpoints/       # Route handlers
    │       ├── auth.py      # OAuth and JWT auth
    │       ├── books.py     # Book CRUD, OCR, management
    │       ├── chat.py      # RAG chat endpoints
    │       ├── users.py     # User management
    │       └── ai.py        # Direct AI utilities
    ├── auth/                # Authentication logic
    │   └── dependencies.py  # FastAPI auth dependencies
    ├── core/                # Configuration and constants
    │   ├── config.py        # Environment settings
    │   └── prompts.py       # AI prompts for OCR, RAG, etc.
    ├── db/                  # Database layer
    │   ├── postgres.py      # PostgreSQL connection and session management
    │   ├── repositories/    # Repository pattern implementations
    │   └── models.py        # SQLAlchemy models
    ├── langchain/           # LangChain integrations
    │   ├── chains/          # LCEL chains
    │   ├── models/          # Model adapters
    │   └── embeddings/      # Embedding adapters
    ├── models/              # Pydantic schemas
    │   ├── schemas.py       # API request/response models
    │   └── user.py          # User models
    ├── services/            # Business logic
    │   ├── pdf_service.py   # PDF upload, OCR orchestration
    │   ├── rag_service.py   # RAG retrieval and chat
    │   ├── ocr_service.py   # Gemini OCR calls
    │   ├── chunking_service.py  # Semantic text chunking
    │   ├── spell_check_service.py  # OCR correction
    │   ├── token_service.py # JWT token management
    │   └── user_service.py  # User CRUD
    ├── utils/               # Utilities
    │   ├── errors.py        # Exception definitions
    │   └── text_helpers.py  # Text cleaning/normalization
    ├── main.py              # FastAPI application
    ├── queue.py             # Redis/ARQ queue client
    ├── jobs.py              # Background job definitions
    └── worker.py            # ARQ worker settings
```

**Key Technologies:**
- Python 3.13
- FastAPI (REST API)
- Pydantic (validation)
- PostgreSQL + asyncpg (database)
- pgvector (vector search)
- LangChain (AI orchestration)
- langchain-google-genai (Gemini integration)
- ARQ (background jobs)
- PyMuPDF (PDF processing)
- httpx (HTTP client)

### `/services/backend` - FastAPI API Service

```
services/backend/
├── scripts/              # Service-specific scripts
├── requirements.txt      # Python dependencies
├── requirements.postgres.txt  # PostgreSQL-specific deps
├── AGENTS.md            # AI agent guidance
└── README.md
```

**Purpose:** Runs the FastAPI REST API that consumes `packages/backend-core`. This is the main HTTP interface for the frontend.

### `/services/worker` - ARQ Background Worker

```
services/worker/
├── requirements.txt      # Python dependencies
├── AGENTS.md            # AI agent guidance
└── README.md
```

**Purpose:** Runs ARQ worker processes that consume jobs from Redis. Handles OCR, embedding generation, and indexing asynchronously.

### `/k8s/local` - Kubernetes Configuration

```
k8s/local/
├── backend.yaml         # Backend deployment + service
├── worker.yaml          # Worker deployment
├── frontend.yaml        # Frontend deployment + service
├── redis.yaml           # Redis deployment + service
├── configmap.yaml       # Non-secret configuration (example)
├── secrets.yaml         # Secrets template
└── README.md            # Deployment instructions
```

**Purpose:** Local Kubernetes manifests for Docker Desktop, minikube, or kind.

### `/scripts` - Utility Scripts

```
scripts/
├── init-db.sql                    # PostgreSQL schema
├── add-missing-columns.sql        # Schema migrations
├── backup_db.sh                   # Database backup
├── deploy_changes.sh              # Deploy to k8s
├── fix-*.py                       # Data migration scripts
├── check_*.py                     # Diagnostic scripts
├── migrate_*.py                   # Data transformation scripts
└── extract_proverbs.py            # Proverb extraction
```

**Purpose:** Database migrations, diagnostics, and maintenance utilities.

### `/data` - Runtime Data (Gitignored)

```
data/
├── uploads/             # Original PDF files (by SHA-256 hash)
├── covers/              # Extracted/uploaded cover images
└── backups/             # Database backups
```

**Purpose:** Persistent storage shared between backend and worker via volume mount.

### `/docs` - Documentation

```
docs/
├── REQUIREMENTS.md           # Business requirements (BRD)
├── SYSTEM_DESIGN.md         # Architecture and design
├── PROJECT_STRUCTURE.md     # This file
└── openapi.json             # OpenAPI 3.0 spec
```

---

## Technology Stack

### Frontend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | React 19 | UI library |
| Build Tool | Vite 6 | Fast dev server and bundler |
| Language | TypeScript 5.8 | Type-safe JavaScript |
| Styling | Tailwind CSS 3.4 | Utility-first CSS |
| Icons | Lucide React | Icon library |
| PDF Rendering | pdf.js | Display PDF pages |
| Testing | Vitest + Testing Library | Unit and integration tests |
| HTTP Client | Fetch API | API communication |

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Framework | FastAPI | REST API framework |
| Language | Python 3.13 | Backend language |
| Validation | Pydantic | Request/response validation |
| Database | PostgreSQL 16+ | Primary data store |
| Vector Search | pgvector | Semantic similarity search |
| Queue | Redis + ARQ | Background job processing |
| AI Platform | Google Gemini | OCR and chat LLM |
| AI Framework | LangChain | AI orchestration |
| PDF Processing | PyMuPDF (fitz) | PDF parsing and rendering |
| Storage | Google Cloud Storage | Cloud-native artifact storage |
| HTTP Client | httpx | Async HTTP requests |

### Infrastructure

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Orchestration | Kubernetes | Container orchestration |
| Local Dev | Docker Desktop | K8s for local development |
| Containerization | Docker | Application packaging |
| Web Server (prod) | nginx | Frontend serving |

---

## Service Components

### 1. Frontend (React/Vite)

**Port:** 30080 (Kubernetes NodePort)
**Dev Port:** 5173 (Vite dev server)

**Responsibilities:**
- User interface for browsing, reading, and managing books
- Google OAuth login flow
- AI chat interface (per-book and global)
- Admin dashboard for user and book management
- Spell check and OCR correction UI
- Book reader with RTL support

**API Communication:**
- All API calls proxied to backend via `/api/*`
- No secrets in client code
- JWT tokens stored in httpOnly cookies

### 2. Backend API (FastAPI)

**Port:** 30800 (Kubernetes NodePort)
**Dev Port:** 8000

**Responsibilities:**
- REST API for all CRUD operations
- OAuth authentication and JWT token issuance
- Book upload and metadata management
- OCR job orchestration (enqueues to Redis)
- RAG chat endpoint (synchronous)
- User management and role-based access control
- Health checks (`/health`, `/ready`)

**Key Endpoints:**
- `POST /api/auth/google` - OAuth callback
- `POST /api/books/upload` - Upload PDF
- `POST /api/books/{id}/ocr/start` - Start OCR job
- `POST /api/chat` - RAG chat (global or per-book)
- `GET /api/books` - List books
- `PATCH /api/books/{id}` - Update book metadata
- `GET /api/users` - List users (admin)

### 3. Worker (ARQ)

**No HTTP port** (background process)

**Responsibilities:**
- Process OCR jobs from Redis queue
- Extract text from PDF pages using Gemini
- Generate embeddings for chunks
- Update PostgreSQL with results
- Handle job retries and error tracking
- Resumable processing (can restart without data loss)

**Job Types:**
- `process_pdf` - Full book OCR and indexing
- `reprocess_pdf` - Re-run OCR (respects verified pages)
- `reindex_pdf` - Regenerate embeddings only
- `process_single_page` - OCR one page

### 4. Redis

**Port:** 6379

**Responsibilities:**
- ARQ job queue
- Job status tracking
- Idempotency locks (prevent duplicate processing)

### 5. PostgreSQL

**Port:** 5432 (host machine)

**Responsibilities:**
- Primary data store for all entities
- Vector similarity search (pgvector)
- User accounts and sessions
- Book metadata and processing status
- Page text and chunks
- Audit logs (created_by, updated_by)

**Tables:**
- `books` - Book metadata
- `pages` - Page-level text and status
- `chunks` - Text chunks with vector embeddings
- `users` - User accounts
- `refresh_tokens` - JWT refresh tokens
- `jobs` - ARQ job tracking

---

## Data Flow

### Book Upload and OCR Processing

```
1. User uploads PDF via Frontend
   ↓
2. Frontend → POST /api/books/upload
   ↓
3. Backend:
   - Calculates SHA-256 hash
   - Checks for duplicates in PostgreSQL
   - Saves PDF to data/uploads/{hash}.pdf
   - Creates book record (status=pending)
   - Returns book metadata
   ↓
4. Editor starts OCR via Frontend
   ↓
5. Frontend → POST /api/books/{id}/ocr/start
   ↓
6. Backend:
   - Updates book status to 'processing'
   - Enqueues process_pdf job to Redis
   - Returns job ID
   ↓
7. Worker (ARQ):
   - Fetches job from Redis
   - Downloads PDF from **Private GCS Bucket** to data/uploads/
   - For each page:
     * Renders page to image
     * Calls Gemini OCR API
     * Saves text to PostgreSQL pages table
     * Updates page status
   - After all pages:
     * Chunks text semantically
     * Generates embeddings via Gemini
     * Saves chunks to PostgreSQL
     * Uploads cover image to **Public GCS Media Bucket**
     * Updates book status to 'ready'
     * **Auto-cleans local data/ folder** (PDF and Cover)
   ↓
8. Frontend polls /api/books/{id} for status
   ↓
9. Book appears in library (if public)
```

### RAG Chat Flow

```
1. User asks question via chat interface
   ↓
2. Frontend → POST /api/chat
   {
     "message": "ئۇيغۇر تىلى نېمە؟",
     "book_id": "uuid" (optional),
     "conversation_history": [...]
   }
   ↓
3. Backend:
   - Generates embedding for question (Gemini)
   - Performs vector similarity search in PostgreSQL:
     * If book_id provided: filter by book_id
     * If global chat: use intelligent routing/librarian
   - Retrieves top K chunks (by cosine similarity)
   - Builds prompt with context and question
   - Calls Gemini chat API via LangChain
   - Returns answer in Uyghur
   ↓
4. Frontend displays answer with citations
```

### User Authentication Flow

```
1. User clicks "Sign in with Google"
   ↓
2. Frontend redirects to Google OAuth
   ↓
3. Google redirects back to backend callback
   ↓
4. Backend → POST /api/auth/google
   - Validates OAuth code
   - Fetches user info from Google
   - Creates or updates user in PostgreSQL
   - Checks if user email is in admin list
   - Generates JWT access + refresh tokens
   - Sets httpOnly cookies
   - Returns user profile
   ↓
5. Frontend stores user in context
   ↓
6. Subsequent requests include JWT in Authorization header
   ↓
7. Backend validates JWT via auth dependency
```

---

## Configuration Management

### Local Development (.env file)

Used when running services manually (outside Kubernetes):

```bash
# Database
DATABASE_URL=postgresql://omarjan@localhost:5432/kitabim_ai

# Redis
REDIS_URL=redis://localhost:6379/0

# AI
GEMINI_API_KEY=your-key
GEMINI_MODEL_NAME=gemini-3-flash-preview
GEMINI_EMBEDDING_MODEL=models/gemini-embedding-001

# Auth
JWT_SECRET_KEY=random-32-char-secret
GOOGLE_CLIENT_ID=your-client-id
GOOGLE_CLIENT_SECRET=your-secret

# Storage
DATA_DIR=/Users/Omarjan/Projects/kitabim-ai/data
```

### Kubernetes (ConfigMap + Secrets)

Used in Docker Desktop/minikube/kind deployment:

**k8s/local/secrets.yaml:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kitabim-secrets
stringData:
  GEMINI_API_KEY: "your-actual-key"
  JWT_SECRET_KEY: "your-jwt-secret"
  GOOGLE_CLIENT_ID: "..."
  GOOGLE_CLIENT_SECRET: "..."
```

**k8s/local/configmap.yaml:**
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: kitabim-config
data:
  DATABASE_URL: "postgresql://user@host.docker.internal:5432/kitabim_ai"
  REDIS_URL: "redis://redis:6379/0"
  GEMINI_MODEL_NAME: "gemini-3-flash-preview"
  DATA_DIR: "/app/data"
  # ... other non-secret config
```

**Volume Mounts:**
- `/app/data` → Host path: `/Users/Omarjan/Projects/kitabim-ai/data`

---

## Development Workflow

### Setup

1. **Clone repository**
   ```bash
   git clone <repo-url>
   cd kitabim-ai
   ```

2. **Install PostgreSQL** (macOS)
   ```bash
   brew install postgresql@16
   brew services start postgresql@16
   createdb kitabim_ai
   ```

3. **Initialize database**
   ```bash
   psql kitabim_ai < scripts/init-db.sql
   ```

4. **Install frontend dependencies**
   ```bash
   npm install
   ```

5. **Install backend dependencies**
   ```bash
   pip install -r services/backend/requirements.txt
   ```

6. **Configure environment**
   - Copy `.env.example` to `.env`
   - Add your `GEMINI_API_KEY`

### Running Locally (Manual)

**Terminal 1: Backend**
```bash
PYTHONPATH=packages/backend-core uvicorn app.main:app --reload --port 8000 --app-dir packages/backend-core
```

**Terminal 2: Worker**
```bash
PYTHONPATH=packages/backend-core python -m arq app.worker.WorkerSettings
```

**Terminal 3: Frontend**
```bash
npm run dev
```

**Terminal 4: Redis**
```bash
redis-server
```

### Running with Kubernetes (Recommended)

1. **Enable Kubernetes in Docker Desktop**
   - Settings → Kubernetes → Enable Kubernetes

2. **Build images**
   ```bash
   docker build -t kitabim-backend:local -f Dockerfile.backend .
   docker build -t kitabim-worker:local -f Dockerfile.worker .
   docker build -t kitabim-frontend:local -f apps/frontend/Dockerfile .
   ```

3. **Deploy**
   ```bash
   kubectl apply -f k8s/local/
   ```

4. **Access**
   - Frontend: http://localhost:30080
   - Backend: http://localhost:30800

5. **Logs**
   ```bash
   kubectl logs -f deployment/backend
   kubectl logs -f deployment/worker
   ```

### Testing

**Frontend:**
```bash
npm test                  # Run tests
npm run test:coverage    # With coverage
```

**Backend:**
```bash
python3.13 -m pytest services/backend/tests
```

---

## Deployment Architecture

### Local Development (Docker Desktop Kubernetes)

```
┌─────────────────────────────────────────────────────────┐
│                     Docker Desktop                       │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Kubernetes Cluster                     │ │
│  │                                                     │ │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐         │ │
│  │  │ Frontend │  │ Backend  │  │  Worker  │         │ │
│  │  │ (nginx)  │  │ (FastAPI)│  │  (ARQ)   │         │ │
│  │  │ :30080   │  │  :30800  │  │          │         │ │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘         │ │
│  │       │             │              │               │ │
│  │       └─────────────┼──────────────┘               │ │
│  │                     │                              │ │
│  │                ┌────▼─────┐          ┌───────┐     │ │
│  │                │  Redis   │          │  GCS  │     │ │
│  │                │  :6379   │          │CloudSt│     │ │
│  │                └──────────┘          └───────┘     │ │
│  │                                                     │ │
│  │  Volume Cache: /app/data → host data/               │ │
│  └─────────────────────────────────────────────────────┘ │
│                                                          │
│  Container connects to host PostgreSQL via              │
│  host.docker.internal:5432                              │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
           ┌──────────────────────────┐
           │   Host Machine           │
           │                          │
           │  PostgreSQL :5432        │
           │  (kitabim_ai database)   │
           │                          │
           │  data/ directory         │
           │   ├── uploads/           │
           │   └── covers/            │
           └──────────────────────────┘
```

### Key Characteristics

- **Stateless Services**: Backend, worker, frontend are stateless (can scale horizontally)
- **Stateful Data**: PostgreSQL on host; files in Google Cloud Storage (GCS)
- **Shared Cache**: `data/` directory mounted for transient, high-speed file processing
- **Service Discovery**: Kubernetes DNS (e.g., `redis:6379`, `backend:8000`)
- **Load Balancing**: Kubernetes service layer (though only 1 replica in dev)

---

## Key Files and Their Purpose

### Root Level

| File | Purpose |
|------|---------|
| `README.md` | Main project documentation and quickstart |
| `AGENTS.md` | Guidance for AI agents working on the repo |
| `package.json` | NPM workspace configuration |
| `.env` | Local development environment variables |
| `.gitignore` | Git ignore patterns |
| `Dockerfile.backend` | Backend service container image |
| `Dockerfile.worker` | Worker service container image |

### Backend Core

| File | Purpose |
|------|---------|
| `app/main.py` | FastAPI application entry point |
| `app/worker.py` | ARQ worker settings and entry point |
| `app/queue.py` | Redis/ARQ queue client |
| `app/jobs.py` | Background job function definitions |
| `app/core/config.py` | Environment configuration loader |
| `app/core/prompts.py` | AI prompts for OCR, RAG, categorization |
| `app/api/endpoints/books.py` | Book CRUD and management endpoints |
| `app/api/endpoints/auth.py` | Authentication endpoints |
| `app/api/endpoints/chat.py` | RAG chat endpoint |
| `app/services/pdf_service.py` | PDF processing orchestration |
| `app/services/rag_service.py` | RAG retrieval and chat logic |
| `app/db/session.py` | PostgreSQL session management |
| `app/db/repositories/` | Repository pattern implementations |

### Frontend

| File | Purpose |
|------|---------|
| `src/App.tsx` | Main application component and routing |
| `src/components/library/LibraryPage.tsx` | Book browsing interface |
| `src/components/reader/ReaderPage.tsx` | Book reader with navigation |
| `src/components/chat/ChatInterface.tsx` | AI chat UI |
| `src/components/admin/ManagementPage.tsx` | Admin dashboard |
| `src/services/authService.ts` | Authentication API client |
| `src/hooks/useAuth.ts` | Authentication state hook |

### Infrastructure

| File | Purpose |
|------|---------|
| `k8s/local/backend.yaml` | Backend deployment and service |
| `k8s/local/worker.yaml` | Worker deployment |
| `k8s/local/redis.yaml` | Redis deployment and service |
| `scripts/init-db.sql` | PostgreSQL schema initialization |

---

## Summary

Kitabim.AI is a **well-structured monorepo** with:

✅ **Clear separation of concerns** (frontend, backend, worker, shared packages)
✅ **Modern tech stack** (React 19, FastAPI, PostgreSQL with pgvector)
✅ **Scalable architecture** (queue-based processing, vector search)
✅ **Local-first development** (Kubernetes for consistent environments)
✅ **Comprehensive documentation** (BRD, system design, OpenAPI spec)

**Code Statistics:**
- **Backend:** 45 Python files in `packages/backend-core/app`
- **Frontend:** 47 TypeScript/TSX files in `apps/frontend/src`
- **API:** 1087 lines in OpenAPI spec (docs/openapi.json)
- **Database:** 6 core tables with pgvector support

The architecture supports the three core workflows:
1. **Digitization** - Upload → OCR → Indexing
2. **Curation** - Edit → Spell Check → Verify
3. **Reading** - Browse → Read → Ask AI

All services communicate via well-defined interfaces (REST API, Redis queue, PostgreSQL) and can be scaled independently based on load characteristics.

---

*Last Updated: 2026-02-19*
