# Kitabim.AI Backend

## Setup
- Create `.env` at the repo root with the same variables as `.env.example`.
- Install dependencies:
  - `pip install -r services/backend/requirements.txt`

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

## Run (Dev)
- `PYTHONPATH=packages/backend-core:services/backend uvicorn main:app --reload --port 8000 --app-dir services/backend`
- Queue worker (required, runs from `services/worker/`): `PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings`

## Notes
- Local dev uses Docker Compose.
- Uses PostgreSQL from `DATABASE_URL` and the shared `data/` folder for uploads/covers.
- Override the data location with `DATA_DIR` (set to `/app/data` inside Docker Compose).
- The Gemini API key stays on the backend; the frontend proxies AI calls via `/api/ai`.
- Redis is required for background jobs (`REDIS_URL`).
- Core code now lives in `packages/backend-core`.
- API contract matches `docs/openapi.json`.

