# Kitabim.AI Worker Blueprint

## System Overview
Asynchronous background worker service running ARQ task queues over Redis for Kitabim.AI, executing pipeline workflows including document OCR, text chunking, vector embeddings, Uyghur dictionary spell-checking, book summarization, historical term extraction, Neo4j knowledge graph construction, and scheduled watchdog tasks.

## Local Interface & Invariants
- `[worker.py:WorkerSettings]`: ARQ worker configuration defining Redis connection parameters, registered functions, scheduled cron jobs, concurrency limits, job timeouts, and lifecycle hooks (`on_startup=worker_startup`, `on_shutdown=worker_shutdown`).
- `[worker.py:WorkerSettings.functions]`: ARQ job handler list (`ocr_job`, `chunking_job`, `embedding_job`, `spell_check_job`, `llm_spell_check_job`, `summary_job`, `auto_correct_job`, `knowledge_graph_job`, `graph_resolution_job`, `rag_eval_job`, `extract_book_history_terms_task`) wrapped with request tracking.
- `[worker.py:WorkerSettings.cron_jobs]`: Scheduled ARQ cron jobs wrapped with `safe_cron_job` to isolate failures.
- `[worker.py:safe_cron_job]`: Decorator catching and logging unhandled exceptions to prevent cron task failures from crashing the worker process.
- `[manual_scan.py:main]`: Standalone CLI utility to execute `run_spell_check_scanner` against PostgreSQL and Redis manually.

## Subdirectories & System Boundaries
- Jobs: [./jobs/README.md](./jobs/README.md) - Asynchronous ARQ task handlers for document processing, OCR, chunking, embeddings, spell checking, and knowledge graphs.
- Scanners: [./scanners/README.md](./scanners/README.md) - Periodic cron scanners, event dispatchers, batch pollers, and stale task watchdogs.

## Global Invariants
- All worker job functions registered in `WorkerSettings.functions` are wrapped with `track_request_id` to maintain request context across asynchronous task boundaries (`[worker.py:WorkerSettings.functions]`).
- All cron tasks in `WorkerSettings.cron_jobs` are wrapped with `safe_cron_job` to ensure any unhandled exception in an individual periodic scanner is logged at `ERROR` level and suppressed, preserving worker uptime (`[worker.py:safe_cron_job]`).
- Queue configuration bounds maximum concurrent jobs to `settings.queue_max_jobs` and per-job execution timeout to `settings.queue_job_timeout` (`[worker.py:WorkerSettings]`).

## Global Side Effects
- Redis: Consumes jobs from Redis queues, acquires distributed locks, and scans worker heartbeat keys (`[worker.py:WorkerSettings]`).
- PostgreSQL: Reads, claims (`FOR UPDATE SKIP LOCKED`), updates, and commits `Book`, `Page`, `Chunk`, and milestone states (`[worker.py:WorkerSettings]`).
- External APIs: Calls Google Gemini APIs for OCR, embeddings, summarization, and knowledge graph extraction (`[worker.py:WorkerSettings]`).

## System Verification
- Run: `pytest services/worker/tests`

## Run (Dev)
```bash
PYTHONPATH=packages/backend-core:services/worker arq worker.WorkerSettings
```

## Backend Core Layout
```
/packages/backend-core
  /app
    /core
    /db
    /llm
    /models
    /services
    /utils
```

## Developer Notes
- Uses the shared backend core package in `/packages/backend-core`.
- Requires Redis (`REDIS_URL`) and PostgreSQL (`DATABASE_URL`).
- Local dev uses Docker Compose.
