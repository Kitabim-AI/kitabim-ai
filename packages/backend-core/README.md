# Backend Core

Shared backend Python package used by the API service and the worker.

Local dev uses Docker Compose.

## Run (Dev)

```bash
PYTHONPATH=packages/backend-core uvicorn app.main:app --reload --port 8000 --app-dir packages/backend-core
```

## Worker (Dev)

```bash
PYTHONPATH=packages/backend-core python -m arq app.worker.WorkerSettings
```
