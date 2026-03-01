# Kitabim.AI Backend (LangChain)

## Setup
- Create `.env` at the repo root with the same variables as `.env.example`.
- Install dependencies:
  - `pip install -r services/backend/requirements.txt`

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

## Run (Dev)
- `PYTHONPATH=packages/backend-core uvicorn app.main:app --reload --port 8000 --app-dir packages/backend-core`
- Queue worker (required): `PYTHONPATH=packages/backend-core python -m arq app.worker.WorkerSettings`

## Notes
- Local dev uses Kubernetes manifests in `/k8s/local`.
- Uses PostgreSQL from `DATABASE_URL` and the shared `data/` folder for uploads/covers.
- Override the data location with `DATA_DIR` (useful for Docker/K8s).
- The Gemini API key stays on the backend; the frontend proxies AI calls via `/api/ai`.
- Redis is required for background jobs (`REDIS_URL`).
- Core code now lives in `packages/backend-core`.
- API contract matches `docs/openapi.json`.
- LangChain-native chains/adapters live under `app/langchain`.
