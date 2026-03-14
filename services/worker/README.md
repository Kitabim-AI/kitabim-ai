# Kitabim.AI Worker

Runs background jobs (OCR/embedding/RAG processing) from Redis using ARQ.

## Run (Dev)

```bash
PYTHONPATH=packages/backend-core python -m arq app.worker.WorkerSettings
```

## Backend Core Layout
```
/packages/backend-core
  /app
    /api
    /services
    /langchain
    /core
    /db
    /models
    /utils
```

## Notes
- Uses the shared backend core package in `/packages/backend-core`.
- Requires Redis (`REDIS_URL`) and PostgreSQL (`DATABASE_URL`).
- Local dev uses Docker Compose.
