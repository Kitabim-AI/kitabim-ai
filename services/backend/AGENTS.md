# AGENTS.md — Backend API

## Service Purpose
FastAPI API service that handles HTTP requests, authentication, and orchestrates uploads, OCR, embeddings, and RAG.

## Code Location
- **Backend-specific code lives here** (`services/backend/`): `main.py`, `api/`, `auth/`, `locales/`
- **Shared business logic** lives in `packages/backend-core/app` (DB, services, utils, queue, langchain, models)
- Both are on `PYTHONPATH` in the Docker image

## Structure
```
services/backend/
  main.py        ← FastAPI app entry point
  api/           ← HTTP route handlers (endpoints)
  auth/          ← JWT, OAuth, dependency injection
  locales/       ← i18n translation JSON files
```

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core:services/backend uvicorn main:app --reload --port 8000 --app-dir services/backend
```

## Dependencies
- PostgreSQL (required, host or container)
- Redis (required, queue/worker)

## Notes
- Do not move secrets into the frontend; backend owns all AI keys.
- Backend-specific code belongs in `services/backend/`. Shared code belongs in `packages/backend-core/app/`.
- Local dev uses Kubernetes (see `k8s/local`).

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in the root `docs/` folder.
