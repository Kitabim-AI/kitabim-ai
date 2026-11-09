# Kitabim.AI Backend Blueprint

## System Overview
FastAPI HTTP application providing REST API endpoints, user authentication, RBAC authorization, book and page management, dictionary exploration, Uyghur spell checking, RAG query pipelines, and system configuration for Kitabim.AI.

## Local Interface & Invariants
- `[main.py:app]`: FastAPI application instance with lifespan handler, CORS, rate limiting, and security middlewares.
- `[main.py:lifespan]`: Context manager initializing logging, translations, JWT secret validation, UserCheck config validation and 0-credit `/status` startup probe, SQLAlchemy database session pools, system config seeding, ADK DatabaseSessionService, and the Redis pub/sub invalidation listener.
- `[main.py:redis_pubsub_listener]`: Background task subscribing to the `user_invalidation` Redis Pub/Sub channel to evict user profiles from `user_lru_cache`.
- `[main.py:limiter]`: Slowapi rate limiter bound to client remote IP addresses.
- `[main.py:add_language_header]`: HTTP middleware setting request language context (`ug` or `en`, default `ug`).
- `[main.py:add_security_headers]`: HTTP middleware enforcing `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Permissions-Policy`, HSTS, and Content Security Policy.
- `[main.py:add_request_id]`: HTTP middleware generating or propagating `X-Request-ID` and setting async context.
- `[main.py:block_noisy_requests]`: HTTP middleware returning early 404 for scanners matching `settings.security_block_prefixes` and `settings.security_block_paths`.
- `[main.py:enforce_app_id]`: HTTP middleware enforcing `X-Kitabim-App-Id == settings.security_app_id` on non-GET `/api/` requests (exempting OAuth bootstrap).
- `[main.py:get_cover]`: Route `GET /api/covers/{book_id}.jpg` serving local cover images or redirecting to Google Cloud Storage.
- `[main.py:get_public_config]`: Route `GET /api/config` serving public configuration flags (`collectionPageSize`, `showChatCost`, `maxUploadMb`).
- `[main.py:root]`, `[main.py:health]`, `[main.py:ready]`: Service health and readiness probes (`GET /`, `GET /health`, `GET /ready`).

## Subdirectories & System Boundaries
- API: [./api/README.md](./api/README.md) - HTTP API routing namespace and endpoint controllers.
- Auth: [./auth/README.md](./auth/README.md) - Authentication, JWT lifecycle, RBAC dependencies, and OAuth providers.

## Global Invariants
- `enforce_app_id` rejects any non-GET/OPTIONS request under `/api/` with HTTP 403 unless `X-Kitabim-App-Id` matches `settings.security_app_id`, exempting only `/api/auth/refresh`, `/api/auth/google/`, `/api/auth/facebook/`, and `/api/auth/twitter/` (`[main.py:enforce_app_id]`).
- `lifespan` validates JWT secrets at startup and aborts startup with `RuntimeError` in production if secrets are missing or invalid (`[main.py:lifespan]`).
- Readiness probe `GET /ready` performs a `SELECT 1` query against PostgreSQL and raises HTTP 503 if the database is unreachable (`[main.py:ready]`).
- Background Redis Pub/Sub listener reconnects automatically every 5 seconds if connection is lost (`[main.py:redis_pubsub_listener]`).

## Global Side Effects
- Database: Initializes SQLAlchemy connection pool (`init_db`) and seeds system configs in PostgreSQL (`[main.py:lifespan]`).
- External APIs: Probes UserCheck `GET https://api.usercheck.com/status` at startup when `USERCHECK_ENABLED=true` (`[main.py:lifespan]`).
- Redis: Subscribes to `user_invalidation` channel on Redis pub/sub (`[main.py:redis_pubsub_listener]`).
- Storage: Serves static covers from `settings.covers_dir` or redirects to Google Cloud Storage (`[main.py:get_cover]`).

## System Verification
- Run: `pytest services/backend/tests`

## Setup & Development
- Create `.env` at the repo root with the same variables as `.env.example`.
- Install dependencies: `pip install -r services/backend/requirements.txt`
- Run dev server:
  ```bash
  PYTHONPATH=packages/backend-core:services/backend uvicorn main:app --reload --port 8000 --app-dir services/backend
  ```
- Queue worker (required, runs from `services/worker/`):
  ```bash
  PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
  ```

## Backend Core Layout
```
/packages/backend-core
  /app
    /core
    /db
    /decorators
    /llm
    /models
    /services
    /utils
    jobs.py
    queue.py
```

## Developer Notes
- Local dev uses Docker Compose.
- Uses PostgreSQL from `DATABASE_URL` and the shared `data/` folder for uploads/covers.
- Override the data location with `DATA_DIR` (set to `/app/data` inside Docker Compose).
- The Gemini API key stays on the backend; the frontend proxies AI calls via `/api/ai`.
- Redis is required for background jobs (`REDIS_URL`).
- Core business logic lives in `packages/backend-core`.
- API contract matches `docs/openapi.json`.
