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

## Code Conventions
- Backend/worker code lives in `packages/backend-core/app`.
- Keep secrets out of the frontend; all AI calls are proxied via the backend.
- Prefer small, surgical edits; update docs when behavior changes.
