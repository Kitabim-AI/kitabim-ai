# Backend Core

Shared backend Python package used by the API service (`services/backend/`) and the
worker service (`services/worker/`). It is not run standalone — it has no `main.py`
or `worker.py` of its own. Both services put `packages/backend-core` on
`PYTHONPATH` alongside their own service directory (see `Dockerfile.backend` /
`Dockerfile.worker`) and import from it as the `app` package (e.g. `app.core.config`,
`app.db.models`, `app.services...`).

## Contents (`app/`)

- `core/` — settings (`config.py`), i18n (`i18n.py`), cache config, pipeline state
  constants, prompts, character personas.
- `db/` — SQLAlchemy models (`models.py`, 30 tables), engine/session factory
  (`session.py`), config seeds (`seeds.py`), and 18 repository classes in
  `db/repositories/`.
- `llm/` — Gemini client and chain wrappers (`chains.py`, `models.py`).
- `services/` — business logic (OCR, chunking, embeddings, spell-check,
  auto-correction, summaries, storage, entity resolution, etc.), plus the
  `services/chat/` (ChatOrchestrator) and `services/rag/` sub-packages.
- `utils/` — shared helpers (circuit breaker, rate limiter, redis lock,
  security, text/markdown utils).
- `decorators/` — shared decorators.

## Migrations

Raw numbered SQL files in `migrations/` (no ORM migration tool / no Alembic).
See `migrations/README.md` for naming convention and how to run them locally
and in production (`./scripts/run_migration_prod.sh`).

## Tests

Pytest tests live in `tests/` (config at repo-root `pytest.ini`). Run from the
repo root:

```bash
pytest packages/backend-core/tests
```

## Local Dev

Local dev runs everything via Docker Compose — see `./deploy/local/rebuild-and-restart.sh`.
There is no standalone `uvicorn`/`arq` invocation for this package; the actual
entry points are `services/backend/main.py` (`uvicorn main:app`) and
`services/worker/worker.py` (`arq worker.WorkerSettings`), each run from its own
service directory with `packages/backend-core` on `PYTHONPATH`.
