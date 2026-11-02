# Local Development Deployment Scripts

## Overview
Automation shell and PowerShell scripts for local development builds, container orchestration, environment variable rotation, and PostgreSQL schema migration management under Docker Compose.

## Interface
- `[rebuild-and-restart.sh:COMPONENT]`: Shell script rebuild target (`all`, `backend`, `worker`, or `frontend`).
- `[rebuild-and-restart.sh:NEW_APP_ID]`: Rotates `SECURITY_APP_ID` with a 16-byte random hex token in the root `.env` file during full rebuilds.
- `[rebuild-and-restart.sh:rebuild_component]`: Builds and starts a designated container service via `docker compose build` and `docker compose up -d`.
- `[rebuild-and-restart.sh:schema_migrations]`: Awaits PostgreSQL readiness, verifies `schema_migrations` table, and executes unapplied migrations from `packages/backend-core/migrations/*.sql`.
- `[rebuild-and-restart.ps1:Component]`: PowerShell equivalent script for Windows environments.
- `[rebuild-and-restart.ps1:Rebuild-Component]`: PowerShell function to rebuild individual services.

## Invariants
- `[rebuild-and-restart.sh]`: PostgreSQL must be running as a standalone host service on `127.0.0.1:5432` with user/database `kitabim`/`kitabim-ai`.
- `[rebuild-and-restart.sh]`: Migration files containing `rollback` in their names are excluded from execution.
- `[rebuild-and-restart.sh]`: Applied migrations are recorded idempotently in `schema_migrations`.

## Side Effects
- `[rebuild-and-restart.sh:NEW_APP_ID]`: Modifies the root `.env` file in-place to rotate `SECURITY_APP_ID`.
- `[rebuild-and-restart.sh:rebuild_component]`: Builds Docker images and starts background containers via Docker Compose.
- `[rebuild-and-restart.sh:schema_migrations]`: Executes database DDL and DML statements against the local PostgreSQL instance.

## Verification
- Run: `docker compose ps`
