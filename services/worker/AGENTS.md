# AGENTS.md — Worker

## Service Purpose
ARQ worker that performs background OCR, embedding, and RAG preprocessing jobs via Redis.

## Code Location
- **Worker entry-point lives here** (`services/worker/`): `worker/`
- **Shared business logic** lives in `packages/backend-core/app` (DB, services, utils, queue)
- Both are on `PYTHONPATH` in the Docker image

## Structure
```
services/worker/
  worker/           ← ARQ WorkerSettings + scanners + jobs
    worker.py       ← WorkerSettings (arq worker.WorkerSettings)
    scanners/       ← cron scanners (gcs_discovery, pipeline_driver, ocr, chunking, embedding, stale_watchdog)
    jobs/           ← job executors (ocr_job, chunking_job, embedding_job)
```

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
```

## Dependencies
- Redis (required)
- PostgreSQL (required)
- Uses the shared `data/` directory for files

## Notes
- Queue is required; there is no local fallback.
- Local dev uses Docker Compose.
- Worker-specific code belongs in `services/worker/`. Shared code belongs in `packages/backend-core/app/`.

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in the root `docs/` folder.
