# AGENTS.md — Backend API

## Service Purpose
FastAPI API service that orchestrates uploads, OCR, embeddings, and RAG. It runs the shared backend core package.

## Code Location
- Core logic lives in `packages/backend-core/app`.
- This service is a thin runtime wrapper.

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core uvicorn app.main:app --reload --port 8000 --app-dir packages/backend-core
```

## Dependencies
- PostgreSQL (required, host or container)
- Redis (required, queue/worker)

## Notes
- Do not move secrets into the frontend; backend owns all AI keys.
- Update `README.md` and `SYSTEM_DESIGN.md` when API behavior changes.
- Local dev uses Kubernetes (see `k8s/local`).

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in the root `docs/` folder.
