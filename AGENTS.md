# AGENTS.md — Kitabim.AI

## Scope
This file provides guidance for automated agents working in this repo.

## Repository Rules
- Keep the monorepo structure intact.
- Local development uses **Docker Compose**.
- Database: **PostgreSQL (local host)**. MongoDB is removed.

## Microservices
- Backend API: `services/backend` (FastAPI, uses `packages/backend-core`)
- Worker: `services/worker` (ARQ, uses `packages/backend-core`)
- Frontend: `apps/frontend` (React/Vite)

## Shared Configuration
- Environment variables live at the repo root in `.env` (see `.env.template`).
- Shared data volume is `./data` (uploads and covers).

## Local Dev (Docker Compose)
- Build images and start all services using `./deploy/local/rebuild-and-restart.sh all`.
- The application connects to PostgreSQL on your local host via `host.docker.internal:5432`.
- **CRITICAL LOCAL RULE**: Do not rely on local dev servers (like `npm run dev`) for final change application. You MUST always use Docker Compose to ensure changes are reflected. Run `./deploy/local/rebuild-and-restart.sh [frontend|backend|worker|all]` to rebuild and restart services after modifying files.

## Production Deployment
- **CRITICAL PRODUCTION RULE**: Use the automated deployment script for all production releases. This ensures the correct architecture (linux/amd64), registry tagging, and VM sync.
- Run: `./deploy/gcp/scripts/deploy.sh [IMAGE_TAG]` from the repository root.
- The script handles building, pushing, and remote deployment commands.

## File Management & Tooling
- **SCRIPTS**: Operational, diagnostic, and testing scripts MUST be placed in the `scripts/` folder. Local deployment and rebuild scripts MUST be placed in `deploy/local/`. Never create ad-hoc scripts in the root or service-specific folders.
- **DOCUMENTATION**: All documentation (other than root-level `README.md` and `AGENTS.md`) MUST be placed in the `docs/` folder.
- **CLEANUP**: Always clean up temporary files, scratchpads, or logs immediately after use. Do not leave `.txt` or `.json` artifacts in the root.

## Code Conventions
- Backend/worker code lives in `packages/backend-core/app`.
- Keep secrets out of the frontend; all AI calls are proxied via the backend.
- Prefer small, surgical edits; update docs when behavior changes.
