# Kitabim.AI Worker

Runs background jobs (OCR/embedding/RAG processing) from Redis using ARQ.

## Run (Dev)

```bash
PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
```

## Backend Core Layout
```
/packages/backend-core
  /app
    /core
    /db
    /llm
    /models
    /services
    /utils
```

## Notes
- Uses the shared backend core package in `/packages/backend-core`.
- Requires Redis (`REDIS_URL`) and PostgreSQL (`DATABASE_URL`).
- Local dev uses Docker Compose.
