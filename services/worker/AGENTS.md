# AGENTS.md — Worker

## Service Purpose
ARQ worker that performs background OCR, embedding, and RAG preprocessing jobs via Redis.

## Code Location
- Job logic lives in `packages/backend-core/app`.
- This service is a thin runtime wrapper.

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core python -m arq app.worker.WorkerSettings
```

## Dependencies
- Redis (required)
- MongoDB (required)
- Uses the shared `data/` directory for files

## Notes
- Queue is required; there is no local fallback.
- Local dev uses Docker Desktop Kubernetes (see `infra/k8s/docker-desktop`).
