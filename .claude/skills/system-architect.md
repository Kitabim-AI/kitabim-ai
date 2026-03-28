# System Architect Skill — Kitabim AI

You are designing new features, integrations, and infrastructure changes for the kitabim-ai system. Before proposing changes, understand the full system topology. Every design decision must consider how the components interact, where state lives, and what fails when.

---

## System Topology

```
                        ┌─────────────────────────────────────────┐
                        │           GCP VM (Production)           │
                        │                                         │
  Browser ──HTTPS──► Nginx (443/80)                               │
                        │   ├──► Frontend (React/Nginx :80)       │
                        │   └──► Backend API (FastAPI :8000)      │
                        │              │                          │
                        │         Redis :6379 ◄──► Worker (arq)  │
                        │              │                          │
                        │         PostgreSQL (external managed)   │
                        │              │                          │
                        │         GCS Buckets                     │
                        │           ├── data bucket (PDFs)        │
                        │           └── media bucket (covers)     │
                        └─────────────────────────────────────────┘

External services:
  Gemini API ◄── Backend (RAG chat, summaries)
  Gemini API ◄── Worker (OCR, embeddings, spell-check)
  OAuth providers ◄── Backend (Google, Facebook, Twitter)
```

---

## Services

| Service | Image | Memory | Restarts | Port (prod) |
|---------|-------|--------|----------|-------------|
| `nginx` | `nginx:1.27-alpine` | 128 MB | always | 80, 443 |
| `frontend` | `kitabim-frontend` | 256 MB | always | internal only |
| `backend` | `kitabim-backend` | 1 GB | always | internal :8000 |
| `worker` | `kitabim-worker` | 1 GB | always | none |
| `redis` | `redis:7-alpine` | 512 MB (prod) / 256 MB (dev) | always | internal :6379 |

**PostgreSQL** is external (managed) in production — not a Docker service.

**Local dev** uses host Postgres (`host.docker.internal:5532`) and a shared `./data` bind mount.

**Production** uses a named Docker volume (`app_data`) mounted to `/mnt/kitabim-data` on the VM.

---

## Request Flow

### API request (authenticated)
```
Browser → Nginx (SSL termination) → Backend
  1. block_noisy_requests middleware — reject crawler/scanner paths
  2. enforce_app_id middleware — verify X-Kitabim-App-Id header
  3. CORS middleware
  4. add_request_id — inject X-Request-ID
  5. add_security_headers — HSTS, CSP, X-Frame-Options
  6. add_language_header — extract Accept-Language for i18n
  7. Route handler
    a. Auth dependency — validate JWT Bearer, cache user in Redis (5 min TTL)
    b. DB session dependency — auto-commit/rollback
    c. Business logic → service → repository → PostgreSQL
    d. Redis cache read/write
  8. Response
```

### Book processing pipeline
```
Upload (POST /api/books)
  └─ Backend: save to DB + GCS, enqueue arq job
       └─ Worker OCR scanner (cron 1 min)
            ├─ Claims idle pages FOR UPDATE SKIP LOCKED
            ├─ Sets ocr_milestone=in_progress, commits
            └─ Enqueues ocr_job
                 └─ Downloads PDF from GCS
                 └─ Calls Gemini Vision per page (semaphore-bounded)
                 └─ Writes text + ocr_milestone=succeeded + PipelineEvent
                 └─ event_dispatcher picks up PipelineEvent → enqueues chunking_job
                      └─ chunking_job → embedding_job → (spell_check_job)
                           └─ pipeline_driver marks book ready
                                └─ Enqueues summary_job
```

### Chat (streaming)
```
POST /api/chat/stream
  1. Check daily usage limit (user_chat_usage table)
  2. Query pgvector similarity search on chunks
  3. Build RAG context (up to rag_max_chars_per_book chars)
  4. Stream Gemini response as SSE (text/event-stream)
  5. Increment usage counter
  6. Record RAG evaluation metrics
```

---

## State Ownership

| State | Owner | Notes |
|-------|-------|-------|
| Book metadata + pipeline status | PostgreSQL | Source of truth |
| Page text + milestones | PostgreSQL | Written by worker jobs |
| Vector embeddings | PostgreSQL (pgvector) | Written by embedding_job |
| User sessions (JWT) | JWT token (stateless) + Redis cache | Cache TTL 5 min |
| Refresh tokens | PostgreSQL | Invalidated on logout |
| Job queue | Redis | arq uses Redis lists |
| Cache (books, configs, users) | Redis | LRU eviction, 256–512 MB cap |
| Raw PDFs | GCS data bucket | `uploads/{book_id}.pdf` |
| Cover images | GCS media bucket | `covers/{book_id}.jpg` |
| Intermediate files | Docker volume `/app/data` | Shared by backend + worker |

**Redis is ephemeral** — data can be lost on restart (local dev uses no persistence; prod uses `appendonly yes`). Never store anything in Redis that cannot be reconstructed from PostgreSQL.

---

## Shared Code Boundary

```
packages/backend-core/     ← imported by BOTH backend and worker
  app/
    db/          models, session, repositories
    services/    business logic (no FastAPI/arq imports)
    models/      Pydantic schemas
    core/        config, cache_config, pipeline constants, i18n, prompts
    langchain/   LLM + embedding models
    utils/       observability, errors, text, security

services/backend/          ← backend-only
  api/endpoints/           route handlers
  auth/                    JWT, OAuth, dependencies

services/worker/           ← worker-only
  jobs/                    arq job functions
  scanners/                cron scanner functions
  worker.py                WorkerSettings entry point
```

**Rule**: logic that both backend and worker need goes in `packages/backend-core/`. Nothing in `packages/backend-core/` may import from `services/backend/` or `services/worker/`.

---

## Designing a New Feature

Work through these questions before writing any code:

### 1. Where does the data live?
- New entity → new table → migration file first
- Extension of existing entity → new column → migration file first
- Ephemeral/computed → Redis cache (if reconstructable) or in-memory

### 2. Who reads and writes it?
- API only → endpoint + repository in `services/backend/`
- Worker only → job/scanner + repository in `services/worker/` (logic in `backend-core`)
- Both → repository and service in `packages/backend-core/`; call from both

### 3. Is it synchronous or async?
- Fast (<200 ms, no external API) → handle in the request cycle
- Slow (LLM call, file processing, large DB scan) → enqueue as an arq job
- Periodic (cleanup, backfill, discovery) → arq cron scanner

### 4. Does it need the pipeline state machine?
- Yes → add `*_milestone` column to `Page` and `Book` (denormalized), write scanner + job, update `pipeline_driver`, `stale_watchdog`, `event_dispatcher`
- No → standalone job or cron task

### 5. What is the failure mode?
- Can the user retry manually? → surface `status`/`error` fields via API
- Should it auto-retry? → use `retry_count` pattern; `pipeline_driver` resets failed milestones
- Is failure acceptable silently? → book-level jobs (summary) can fail without blocking book availability

### 6. What needs to be cached?
- Frequently-read, rarely-written → Redis with TTL from `settings.cache_ttl_*`
- Per-user state → include `user_id` in cache key
- Admin-only queries → do not cache (or explicitly opt in)
- After any write → invalidate affected keys immediately

### 7. Auth and access control
- Public endpoint → no auth dependency
- Authenticated readers → `require_reader`
- Content management → `require_editor`
- System administration → `require_admin`
- Never relax auth on an existing endpoint without understanding downstream effects

---

## Adding a New Pipeline Step

Checklist for adding a step (e.g. `my_step`) to the OCR → Chunking → Embedding chain:

1. **Migration** — add `my_step_milestone` to `pages` and `books`
2. **ORM** — add `Mapped` fields to `Page` and `Book` in `models.py`
3. **Scanner** — `scanners/my_step_scanner.py` — claim with `FOR UPDATE SKIP LOCKED`; dependency gate on previous step's `*_milestone == "succeeded"`
4. **Job** — `jobs/my_step_job.py` — per-page session isolation, emit `PipelineEvent`
5. **BookMilestoneService** — extend to handle `my_step`
6. **pipeline_driver** — add `my_step_milestone` to the reset logic and terminal detection
7. **stale_watchdog** — add `my_step_milestone` to `where_conditions` and `update_values`
8. **event_dispatcher** — add handler for `my_step_succeeded` if it should trigger the next step reactively
9. **Register** — add job to `WorkerSettings.functions`, scanner to `WorkerSettings.cron_jobs`
10. **API** — expose milestone status in the `Book` response schema if the frontend needs to show progress

---

## Adding a New External Integration

1. **Credentials** — add to `Settings` dataclass in `core/config.py`; never hardcode or `os.environ.get()` at call sites
2. **Client init** — initialise the client once (in `lifespan` for backend, in `worker_startup` for worker); store on `app.state` or as a module-level singleton
3. **Circuit breaker** — wrap LLM/embedding calls in the existing circuit breaker pattern (`app/utils/circuit_breaker.py`) for graceful degradation
4. **Timeout** — all external calls must have an explicit timeout; never let them block indefinitely
5. **Cache** — cache results where the same input reliably produces the same output (RAG queries are cached by `cache_ttl_rag_query`)
6. **Error budget** — decide: is failure blocking (raise `HTTPException`) or degrading (log + return fallback)?

---

## Scaling Considerations

| Bottleneck | Current mitigation | If load increases |
|------------|-------------------|------------------|
| LLM API rate limits | Semaphore per job, `embed_batch_size` | Increase worker replicas; add per-model rate limiter |
| DB connections | Pool size in `Settings` (backend 10/15, worker 5/10) | Increase pool; add PgBouncer |
| Redis memory | 256 MB (dev) / 512 MB (prod), LRU eviction | Increase `maxmemory`; split cache/queue Redis instances |
| Worker parallelism | `queue_max_jobs` in `Settings` | Increase `max_jobs`; run multiple worker replicas (be careful: scanners use `FOR UPDATE SKIP LOCKED` so multiple workers are safe) |
| Frontend static assets | Nginx serves compiled Vite output | CDN in front of Nginx |

**Worker replicas are safe** because all scanner claiming uses `FOR UPDATE SKIP LOCKED` — two workers will never process the same page simultaneously.

---

## Security Boundaries

| Boundary | Enforcement |
|----------|------------|
| Public internet → services | Nginx TLS termination; `enforce_app_id` middleware |
| Between services | Internal Docker network (`networks: internal`); no ports exposed except Nginx 80/443 |
| API auth | JWT Bearer; role-based `require_*` dependencies |
| File access | GCS signed URLs for private content; only `covers` are public via `/api/covers/` |
| IP logging | Hashed before storage (`security.hash_ip()`) |
| CORS | Configurable `cors_origins` in `settings` |
| Content Security | CSP, HSTS, X-Frame-Options headers via middleware |

---

## Local vs Production Differences

| Aspect | Local dev | Production (GCP) |
|--------|-----------|-----------------|
| PostgreSQL | Host machine port 5532 | External managed instance |
| Redis persistence | None (ephemeral) | `appendonly yes`, `appendfsync everysec` |
| Redis memory | 256 MB | 512 MB |
| File storage | `./data` bind mount | `/mnt/kitabim-data` named volume |
| GCS | Real GCS with service account key | Same |
| Images | Built locally | Pulled from `$REGISTRY` |
| Nginx | Not present (ports exposed directly) | Present (SSL termination) |
| Rebuild | `./deploy/local/rebuild-and-restart.sh` | `./deploy/gcp/deploy.sh` |
