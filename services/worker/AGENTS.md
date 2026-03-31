# AGENTS.md — Worker

## Service Purpose
ARQ async worker that processes all background jobs via Redis. Runs the full document processing pipeline (GCS discovery → OCR → Chunking → Embedding → Summary → Word Index) plus spell-check and auto-correction jobs.

## Code Location
- **Worker-specific code lives here** (`services/worker/`): `worker.py`, `jobs/`, `scanners/`
- **Shared business logic** lives in `packages/backend-core/app/` (DB, services, utils, queue)
- Both are on `PYTHONPATH` in the Docker image

## Structure
```
services/worker/
  worker.py                        ← ARQ WorkerSettings entry point
  manual_scan.py                   ← Utility for manually triggering scans
  jobs/
    ocr_job.py                     ← OCR execution for a single page/book
    chunking_job.py                ← Text chunking job
    embedding_job.py               ← Vector embedding generation job
    spell_check_job.py             ← Spell-check job
    auto_correct_job.py            ← Auto-correction application job
    summary_job.py                 ← Text summarization job
  scanners/
    pipeline_driver.py             ← Main cron: drives the entire processing pipeline
    gcs_discovery_scanner.py       ← Discovers new files in Google Cloud Storage
    ocr_scanner.py                 ← Finds pages needing OCR, enqueues ocr_job
    chunking_scanner.py            ← Finds pages needing chunking, enqueues chunking_job
    embedding_scanner.py           ← Finds chunks needing embeddings, enqueues embedding_job
    spell_check_scanner.py         ← Finds pages needing spell-check, enqueues spell_check_job
    auto_correct_scanner.py        ← Finds pages needing auto-correct, enqueues auto_correct_job
    summary_scanner.py             ← Finds books needing summaries, enqueues summary_job
    stale_watchdog.py              ← Detects and resets stuck/stale jobs
    event_dispatcher.py            ← Event queue management
    maintenance_scanner.py         ← Periodic maintenance tasks
  tests/
    jobs/                          ← Unit tests for each job
    scanners/                      ← Unit tests for each scanner
```

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
```

## Dependencies
- Redis (required — job queue)
- PostgreSQL (required — job state and results)
- Google Cloud Storage (required — source documents)
- Shared `./data/` directory for intermediate files

## Notes
- Queue is required; there is no local fallback mode.
- Worker-specific code belongs in `services/worker/`. Shared/reusable code belongs in `packages/backend-core/app/`.
- Local dev uses Docker Compose (`./deploy/local/rebuild-and-restart.sh worker`).

## Standard Rules
- **GLOBAL RULES**: Refer to the root `AGENTS.md` for standardized project rules.
- **SCRIPTS**: All operational/debug scripts MUST go in the root `scripts/` folder.
- **DOCS**: All new documentation MUST go in `docs/<branch-name>/` (e.g. `docs/main/`). Run `git branch --show-current` for the branch name.
