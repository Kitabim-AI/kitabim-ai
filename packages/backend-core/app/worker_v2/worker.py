"""
Worker v2 — ARQ WorkerSettings.

Separate from worker v1 (app/worker.py). Run with:
  arq app.worker_v2.worker.WorkerV2Settings

Cron schedule:
  gcs_discovery     every 5 min  — list GCS uploads/, register new books
  pipeline_driver   every 1 min  — state machine: init, reset, promote, book ready
  ocr_scanner       every 1 min  — claim ocr/idle pages (per book) + dispatch
  chunking_scanner  every 1 min  — claim chunking/idle pages + dispatch
  embedding_scanner every 1 min  — claim embedding/idle pages + dispatch
  stale_watchdog    every 30 min — reset in_progress pages past timeout → idle
"""
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.queue import worker_startup, worker_shutdown
from app.worker_v2.scanners.gcs_discovery_scanner import run_gcs_discovery_scanner
from app.worker_v2.scanners.pipeline_driver import run_pipeline_driver
from app.worker_v2.scanners.ocr_scanner import run_ocr_scanner
from app.worker_v2.scanners.chunking_scanner import run_chunking_scanner
from app.worker_v2.scanners.embedding_scanner import run_embedding_scanner
from app.worker_v2.scanners.stale_watchdog import run_stale_watchdog
from app.worker_v2.jobs.ocr_job import v2_ocr_job
from app.worker_v2.jobs.chunking_job import v2_chunking_job
from app.worker_v2.jobs.embedding_job import v2_embedding_job


class WorkerV2Settings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [
        v2_ocr_job,
        v2_chunking_job,
        v2_embedding_job,
    ]

    cron_jobs = [
        cron(run_gcs_discovery_scanner, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(run_pipeline_driver, run_at_startup=True),
        cron(run_ocr_scanner),
        cron(run_chunking_scanner),
        cron(run_embedding_scanner),
        cron(run_stale_watchdog, minute={0, 30}),
    ]

    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    on_startup = worker_startup
    on_shutdown = worker_shutdown
