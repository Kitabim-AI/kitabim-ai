# AGENTS.md — Kitabim.AI

## Scope
This file provides guidance for automated agents working in this repo.

## Repository Rules
- Keep the monorepo structure intact.
- Local development uses **Kubernetes (Docker Desktop, minikube, or kind)**.
- Database: **PostgreSQL (local host)**. MongoDB is removed.

## Microservices
- Backend API: `services/backend` (FastAPI, uses `packages/backend-core`)
- Worker: `services/worker` (ARQ, uses `packages/backend-core`)
- Frontend: `apps/frontend` (React/Vite)

## Shared Configuration
- Environment variables live at the repo root in `.env` (see `.env.example`).
- Secrets and config for local k8s deployment live in `k8s/local/`.
- Shared data volume is `./data` (uploads and covers).

## Local Dev (Kubernetes)
- Build images, then apply manifests in `k8s/local/`.
- The application connects to PostgreSQL on your local host via `host.docker.internal:5432`.
- See `KUBERNETES_DEPLOYMENT.md` for the current quickstart commands and ports.
- **CRITICAL DEPLOYMENT RULE**: Do not rely on local dev servers (like `npm run dev`) for final change application. You MUST always deploy all code changes to Kubernetes to ensure they are available in the cluster. Run `./rebuild-and-restart.sh [frontend|backend|worker|all]` to rebuild the Docker image and restart the Kubernetes deployment after modifying files.
- **IMAGE TAGGING**: Always build images with the `:local` tag and deploy using the same tag. This is the standardized tag used in the local cluster manifests. Never use `:latest` or other dynamic tags for local development.

## File Management & Tooling
- **SCRIPTS**: All scripts (operational, debugging, diagnostic, or testing) MUST be placed in the `scripts/` folder at the repo root. Never create ad-hoc scripts in the root or service-specific folders.
- **DOCUMENTATION**: All documentation (other than root-level `README.md` and `AGENTS.md`) MUST be placed in the `docs/` folder.
- **CLEANUP**: Always clean up temporary files, scratchpads, or logs immediately after use. Do not leave `.txt` or `.json` artifacts in the root.

## Code Conventions
- Backend/worker code lives in `packages/backend-core/app`.
- Keep secrets out of the frontend; all AI calls are proxied via the backend.
- Prefer small, surgical edits; update docs when behavior changes.
