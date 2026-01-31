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
- MongoDB (required)
- Redis (required, queue/worker)
- UyghurOCR service (optional, only if `OCR_PROVIDER=local`)

## Notes
- Do not move secrets into the frontend; backend owns all AI keys.
- Update `README.md` and `SYSTEM_DESIGN.md` when API behavior changes.
- Local dev uses Docker Desktop Kubernetes (see `infra/k8s/docker-desktop`).
