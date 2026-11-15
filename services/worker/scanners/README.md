# Worker Scanners

## Overview
Periodic cron scanners, event dispatchers, batch API pollers, and watchdog tasks that drive the V2 book processing pipeline, claim eligible rows using PostgreSQL row-level locks, poll Gemini Batch API jobs, discover new PDFs in cloud storage, recover stale tasks, and prune expired pipeline events.

## Interface
- `[auto_correct_scanner.py:run_auto_correct_scanner]`: `async def run_auto_correct_scanner(ctx) -> None`
- `[batch_embedding_poller_scanner.py:run_batch_embedding_poller_scanner]`: `async def run_batch_embedding_poller_scanner(ctx) -> None`
- `[batch_ocr_poller_scanner.py:run_batch_ocr_poller_scanner]`: `async def run_batch_ocr_poller_scanner(ctx) -> None`
- `[chunking_scanner.py:run_chunking_scanner]`: `async def run_chunking_scanner(ctx) -> None`
- `[embedding_scanner.py:run_embedding_scanner]`: `async def run_embedding_scanner(ctx) -> None`
- `[event_dispatcher.py:run_event_dispatcher]`: `async def run_event_dispatcher(ctx) -> None`
- `[gcs_discovery_scanner.py:run_gcs_discovery_scanner]`: `async def run_gcs_discovery_scanner(ctx) -> None`
- `[graph_resolution_scanner.py:run_graph_resolution_scanner]`: `async def run_graph_resolution_scanner(ctx) -> None`
- `[graph_scanner.py:run_graph_scanner]`: `async def run_graph_scanner(ctx) -> None`
- `[maintenance_scanner.py:run_maintenance_scanner]`: `async def run_maintenance_scanner(ctx) -> None`
- `[ocr_scanner.py:run_ocr_scanner]`: `async def run_ocr_scanner(ctx) -> None`
- `[structure_scanner.py:run_structure_scanner]`: `async def run_structure_scanner(ctx) -> None`
- `[pipeline_driver.py:run_pipeline_driver]`: `async def run_pipeline_driver(ctx) -> None`
- `[spell_check_scanner.py:run_spell_check_scanner]`: `async def run_spell_check_scanner(ctx) -> None`
- `[stale_watchdog_scanner.py:STALE_THRESHOLD_MINUTES]`: Constant `30`
- `[stale_watchdog_scanner.py:run_stale_watchdog]`: `async def run_stale_watchdog(ctx) -> None`
- `[summary_scanner.py:run_summary_scanner]`: `async def run_summary_scanner(ctx) -> None`

## Invariants
- **Lock-Free Concurrent Claiming**: `ocr_scanner`, `spell_check_scanner`, `chunking_scanner`, `embedding_scanner`, `event_dispatcher`, and `graph_scanner` claim eligible database rows using `FOR UPDATE SKIP LOCKED` so multiple workers never double-claim the same pages, books, or events (`[ocr_scanner.py:run_ocr_scanner]`, `[spell_check_scanner.py:run_spell_check_scanner]`, `[chunking_scanner.py:run_chunking_scanner]`, `[embedding_scanner.py:run_embedding_scanner]`, `[event_dispatcher.py:run_event_dispatcher]`, `[graph_scanner.py:run_graph_scanner]`).
- **Stage Dependencies & Feature Flags**:
  - `chunking_scanner` and `event_dispatcher` require `Page.ocr_milestone == 'succeeded'`, and when `spell_check_enabled == 'true'`, also require `Page.spell_check_milestone in ['succeeded', 'failed']` before claiming pages for chunking (`[chunking_scanner.py:run_chunking_scanner]`, `[event_dispatcher.py:run_event_dispatcher]`).
  - `embedding_scanner` requires `Page.chunking_milestone == 'succeeded'` and routes to `submit_batch_embedding_job` when `embed_batch_enabled == 'true'`, or enqueues `embedding_job` otherwise (`[embedding_scanner.py:run_embedding_scanner]`).
  - `spell_check_scanner` exits early unless `spell_check_enabled == 'true'` and caps concurrent books undergoing spell check at `settings.max_concurrent_spell_check_books` (`[spell_check_scanner.py:run_spell_check_scanner]`).
  - `auto_correct_scanner` exits early unless `auto_correct_enabled == 'true'`; `graph_scanner` and `graph_resolution_scanner` exit early unless `kg_enabled == 'true'` (`[auto_correct_scanner.py:run_auto_correct_scanner]`, `[graph_scanner.py:run_graph_scanner]`, `[graph_resolution_scanner.py:run_graph_resolution_scanner]`).
- **Pipeline State Machine (`pipeline_driver.py`)**:
  - Excludes books with `Book.status in ('ready', 'error')` (`[pipeline_driver.py:_V1_READY_STATUSES]`).
  - Resets failed milestones back to `'idle'` only when `Page.retry_count < max_retries` (`ocr_max_retry_count`, default 3), capped at 5,000 pages per query (`[pipeline_driver.py:run_pipeline_driver]`).
  - Transitions a book to `status='ready'`, `pipeline_step='ready'`, `graph_milestone='idle'` only when all its pages (`count > 0`) are terminal and `failed_exhausted == 0`, or to `status='error'`, `pipeline_step='failed'` when all pages are terminal and `failed_exhausted > 0` (`[pipeline_driver.py:run_pipeline_driver]`).
- **Stale Watchdog Exemption & Thresholds (`stale_watchdog_scanner.py`)**:
  - Exempts pages belonging to active (`'submitting'`, `'submitted'`, `'running'`) `BatchOCRJob` or `BatchEmbeddingJob` records from stale resets (`[stale_watchdog_scanner.py:run_stale_watchdog]`).
  - Marks an `in_progress` page stale if its worker has no `worker:heartbeat:<worker_id>` key in Redis and `claimed_at < now - 2m`, or if `claimed_at < now - 30m` (`STALE_THRESHOLD_MINUTES = 30`); resets `Book.graph_milestone` after 1 hour (`[stale_watchdog_scanner.py:run_stale_watchdog]`).
- **GCS Discovery & Maintenance**:
  - `gcs_discovery_scanner` processes only `.pdf` blobs under `uploads/`, deduplicating against existing filenames, 12-char MD5 `book_id` stems, and SHA-256 `content_hash` (`[gcs_discovery_scanner.py:run_gcs_discovery_scanner]`).
  - `maintenance_scanner` deletes only `PipelineEvent` rows where `processed.is_(True)` and `created_at < cutoff_date` (`[maintenance_scanner.py:run_maintenance_scanner]`).

## Side Effects
- **PostgreSQL Mutations**: Claims and updates `Page`, `Book`, `PipelineEvent`, and `graph_resolution_queue` rows; creates `Book` and `Page` stubs for newly discovered GCS PDFs; deletes expired `PipelineEvent` rows; updates book milestones via `BookMilestoneService` (`[ocr_scanner.py:run_ocr_scanner]`, `[pipeline_driver.py:run_pipeline_driver]`, `[gcs_discovery_scanner.py:run_gcs_discovery_scanner]`, `[maintenance_scanner.py:run_maintenance_scanner]`).
- **Redis Queue & Heartbeats**: Enqueues `ocr_job`, `spell_check_job`, `chunking_job`, `embedding_job`, `auto_correct_job`, `summary_job`, `knowledge_graph_job`, and `graph_resolution_job` into Redis via ARQ, and scans `worker:heartbeat:*` keys in `run_stale_watchdog` (`[ocr_scanner.py:run_ocr_scanner]`, `[event_dispatcher.py:run_event_dispatcher]`, `[stale_watchdog_scanner.py:run_stale_watchdog]`).
- **External Gemini Batch APIs & Cloud Storage**: Polls Gemini Batch API endpoints and processes completed batches (`[batch_ocr_poller_scanner.py:run_batch_ocr_poller_scanner]`, `[batch_embedding_poller_scanner.py:run_batch_embedding_poller_scanner]`), submits batch embedding jobs (`[embedding_scanner.py:run_embedding_scanner]`), and downloads/re-uploads standardized PDFs and cover images in storage (`[gcs_discovery_scanner.py:run_gcs_discovery_scanner]`).

## Verification
- Run: `pytest services/worker/tests`
