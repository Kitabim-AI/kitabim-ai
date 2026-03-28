# AGENTS.md — Kitabim.AI

## Scope
This file provides guidance for automated agents working in this repo.

## Repository Rules
- Keep the monorepo structure intact.
- Local development uses **Docker Compose**.
- Database: **PostgreSQL (local host)**. MongoDB is removed.

## Microservices
- **Backend API**: `services/backend/` — FastAPI HTTP service (uses `packages/backend-core`)
- **Worker**: `services/worker/` — ARQ background job processor (uses `packages/backend-core`)
- **Frontend**: `apps/frontend/` — React/Vite TypeScript SPA
- **Shared backend library**: `packages/backend-core/` — DB models, repos, services, RAG, utils
- **Shared TS types**: `packages/shared/` — TypeScript API contracts shared with frontend

## Technology Stack
- **Frontend**: React 19, TypeScript, Vite, Tailwind CSS
- **Backend API**: Python, FastAPI, SQLAlchemy, Alembic
- **Worker**: Python, ARQ (async task queue over Redis)
- **Database**: PostgreSQL
- **Cache / Queue**: Redis
- **Storage**: Google Cloud Storage + local `./data/` volume
- **AI/ML**: Google Gemini API, LangChain, vector embeddings
- **Auth**: JWT + OAuth2 (Google, Facebook, Twitter/X)

## Key Domains
1. **OCR Pipeline**: PDF → OCR → Chunking → Embedding → Word Index
2. **RAG System**: Query → Retrieval → Gemini generation (multiple context handlers)
3. **Spell-Check**: Uyghur spell-checking with custom auto-correct rules and dictionary
4. **User Management**: JWT auth, OAuth providers, usage/rate limiting
5. **Admin Panel**: System config, dictionary editor, auto-correct rules, user management, stats

## Shared Configuration
- Environment variables live at the repo root in `.env` (see `.env.template`).
- Shared data volume is `./data/` (uploads and page images).
- GCP deployment env lives in `deploy/gcp/.env` (see `deploy/gcp/.env.template`).

## Local Dev (Docker Compose)
- Build images and start all services: `./deploy/local/rebuild-and-restart.sh all`
- Rebuild a single service: `./deploy/local/rebuild-and-restart.sh [frontend|backend|worker]`
- The application connects to PostgreSQL on your local host via `host.docker.internal:5532`.
- Frontend: http://localhost:30080 | Backend: http://localhost:30800
- **CRITICAL LOCAL RULE**: Do not rely on local dev servers (like `npm run dev`) for final change application. You MUST always use Docker Compose to ensure changes are reflected.

## Production Deployment
- **CRITICAL PRODUCTION RULE**: Use the automated deployment script for all production releases. This ensures the correct architecture (linux/amd64), registry tagging, and VM sync.
- Run: `./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]` from the repository root.
- The script handles building, pushing, and remote deployment commands.
- GCP infra: Compute Engine VM + Cloud Storage + Nginx reverse proxy (`deploy/gcp/nginx/`).

## File Management & Tooling
- **SCRIPTS**: Operational, diagnostic, and testing scripts MUST be placed in `scripts/`. Local deployment/rebuild scripts MUST be in `deploy/local/`. Never create ad-hoc scripts in the root or service folders.
- **DOCUMENTATION**: All documentation (other than root-level `README.md` and `AGENTS.md`) MUST be placed in `docs/<branch-name>/` (e.g. `docs/main/` on the `main` branch), unless explicitly asked otherwise. Run `git branch --show-current` to get the current branch name.
- **CLEANUP**: Always clean up temporary files, scratchpads, or logs immediately after use. Do not leave `.txt` or `.json` artifacts in the root.

## Code Conventions
- Shared business logic lives in `packages/backend-core/app/` — not in service folders.
- Backend-specific code (routes, auth, locales) lives in `services/backend/`.
- Worker-specific code (jobs, scanners) lives in `services/worker/`.
- Keep secrets out of the frontend; all AI calls are proxied via the backend.
- Prefer small, surgical edits; update docs when behavior changes.
