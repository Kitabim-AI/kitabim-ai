"""
Worker — ARQ WorkerSettings.

Run with:
  arq worker.WorkerSettings

Cron schedule:
  gcs_discovery        every 5 min  — list GCS uploads/, register new books
  pipeline_driver      every 1 min  — state machine: init, reset, promote, book ready
  ocr_scanner          every 1 min  — claim ocr/idle pages (per book) + dispatch
  chunking_scanner     every 1 min  — claim chunking/idle pages + dispatch
  embedding_scanner    every 1 min  — claim embedding/idle pages + dispatch
  spell_check_scanner  every 1 min  — claim spell_check/idle pages + dispatch
  auto_correct_scanner daily at 3AM — apply auto-corrections in bulk
  stale_watchdog       every 30 min — reset in_progress pages past timeout → idle
  summary_scanner      every 5 min  — backfill/retry book_summaries for ready books
  maintenance_scanner  daily at 3AM — cleanup old processed events/logs
  reembedding_scanner  every 1 min  — backfill embedding_v2 (3072-dim) for all books (migration only — remove after 037)
"""
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.queue import worker_startup, worker_shutdown
from scanners.gcs_discovery_scanner import run_gcs_discovery_scanner
from scanners.pipeline_driver import run_pipeline_driver
from scanners.ocr_scanner import run_ocr_scanner
from scanners.chunking_scanner import run_chunking_scanner
from scanners.embedding_scanner import run_embedding_scanner
from scanners.spell_check_scanner import run_spell_check_scanner
from scanners.stale_watchdog import run_stale_watchdog
from scanners.summary_scanner import run_summary_scanner
from scanners.event_dispatcher import run_event_dispatcher
from scanners.maintenance_scanner import run_maintenance_scanner
from scanners.auto_correct_scanner import run_auto_correct_scanner
from jobs.ocr_job import ocr_job
from jobs.chunking_job import chunking_job
from jobs.embedding_job import embedding_job
from jobs.spell_check_job import spell_check_job
from jobs.summary_job import summary_job
from jobs.auto_correct_job import auto_correct_job
from jobs.reembedding_job import reembedding_job
from scanners.reembedding_scanner import run_reembedding_scanner


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [
        ocr_job,
        chunking_job,
        embedding_job,
        spell_check_job,
        summary_job,
        auto_correct_job,
        reembedding_job,
    ]

    # Build cron jobs list conditionally based on feature flags
    cron_jobs = [
        cron(run_auto_correct_scanner, hour=3, minute=0, run_at_startup=False),
        cron(run_gcs_discovery_scanner, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(run_pipeline_driver, run_at_startup=True),
        cron(run_ocr_scanner),
        cron(run_chunking_scanner),
        cron(run_embedding_scanner),
        cron(run_spell_check_scanner),
        cron(run_stale_watchdog, minute={0, 30}),
        cron(run_summary_scanner, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
        cron(run_event_dispatcher, run_at_startup=True),
        cron(run_maintenance_scanner, hour=3, minute=0),
        cron(run_reembedding_scanner),
    ]



    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    on_startup = worker_startup
    on_shutdown = worker_shutdown
