# AGENTS.md — Backend API

## Service Purpose
FastAPI REST API service. Handles all HTTP requests from the frontend, authentication, and orchestrates uploads, RAG queries, spell-check, and admin operations. Does NOT run background jobs — those go to the worker via Redis/ARQ.

## Code Location
- **Backend-specific code lives here** (`services/backend/`): `main.py`, `api/`, `auth/`, `locales/`
- **Shared business logic** lives in `packages/backend-core/app/` (DB models, repos, services, RAG, utils, queue)
- Both are on `PYTHONPATH` in the Docker image

## Structure
```
services/backend/
  main.py                      ← FastAPI app entry point
  requirements.txt             ← Python dependencies
  api/
    endpoints/
      ai.py                    ← AI/Gemini endpoints
      auth.py                  ← Authentication (login, OAuth callbacks, refresh)
      auto_correct_rules.py    ← Auto-correction rule management
      books.py                 ← Book catalog CRUD
      chat.py                  ← Chat/RAG query endpoints
      contact.py               ← Contact form submission
      dictionary.py            ← Dictionary management
      spell_check.py           ← Spell-check endpoints
      stats.py                 ← Statistics dashboard data
      system_configs.py        ← System configuration editor
      users.py                 ← User management (admin)
  auth/
    dependencies.py            ← FastAPI dependency injection (current_user, etc.)
    jwt_handler.py             ← JWT token creation & validation
    oauth_providers.py         ← OAuth routing dispatcher
    providers/
      base.py                  ← Base OAuth provider interface
      google.py                ← Google OAuth
      facebook.py              ← Facebook OAuth
      twitter.py               ← Twitter/X OAuth
  locales/
    en.json                    ← English i18n strings
    ug.json                    ← Uyghur i18n strings
  tests/
    api/                       ← Endpoint tests
    auth/                      ← Auth unit tests
```

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core:services/backend uvicorn main:app --reload --port 8000 --app-dir services/backend
```

## Dependencies
- PostgreSQL (required)
- Redis (required — used to enqueue jobs for the worker)

## Notes
- Backend owns all AI API keys; never expose them to the frontend.
- Backend-specific code belongs in `services/backend/`. Shared/reusable code belongs in `packages/backend-core/app/`.
- Local dev uses Docker Compose (`./deploy/local/rebuild-and-restart.sh backend`).

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in `docs/<branch-name>/` (e.g. `docs/main/`). Run `git branch --show-current` for the branch name.
