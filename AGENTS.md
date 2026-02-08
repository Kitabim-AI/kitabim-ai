# AGENTS.md — Kitabim.AI

## Scope
This file provides guidance for automated agents working in this repo.

## Repository Rules
- Keep the monorepo structure intact.
- Local development uses **Docker Desktop Kubernetes**. Docker Compose is not supported.

## Microservices
- Backend API: `services/backend` (FastAPI, uses `packages/backend-core`)
- Backend API: `services/backend` (FastAPI, uses `packages/backend-core`)
- Worker: `services/worker` (ARQ, uses `packages/backend-core`)
- Frontend: `apps/frontend` (React/Vite)

## Shared Configuration
- Environment variables live at the repo root in `.env` (see `.env.example`).
- Secrets live in `infra/k8s/docker-desktop/secret.yaml` and config in `infra/k8s/docker-desktop/configmap.yaml`.
- Shared data volume is `./data` (uploads and covers).

## Local Dev (Docker Desktop Kubernetes)
- Build images, then apply manifests in `infra/k8s/docker-desktop`.
- See `README.md` for the current quickstart commands and ports.

## Code Conventions
- Backend/worker code lives in `packages/backend-core/app`.
- Keep secrets out of the frontend; all AI calls are proxied via the backend.
- Prefer small, surgical edits; update docs when behavior changes.
