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
  graph_scanner        every 5 min  — backfill/retry book knowledge graphs for ready books
                                      (NOTE: written but not registered below — extraction
                                      is manual-only per reprocess_graph, see design v2 §3)
  graph_resolution_scanner every 5 min — claim graph_resolution_queue rows, dispatch
                                      graph_resolution_job (entity resolution v2 §4)
  maintenance_scanner  daily at 3AM — cleanup old processed events/logs
"""

import functools
import logging
from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.queue import worker_startup, worker_shutdown
from app.utils.observability import track_request_id, log_json
from scanners.gcs_discovery_scanner import run_gcs_discovery_scanner
from scanners.pipeline_driver import run_pipeline_driver
from scanners.ocr_scanner import run_ocr_scanner
from scanners.chunking_scanner import run_chunking_scanner
from scanners.embedding_scanner import run_embedding_scanner
from scanners.spell_check_scanner import run_spell_check_scanner
from scanners.stale_watchdog_scanner import run_stale_watchdog
from scanners.summary_scanner import run_summary_scanner
from scanners.event_dispatcher import run_event_dispatcher
from scanners.maintenance_scanner import run_maintenance_scanner
from scanners.auto_correct_scanner import run_auto_correct_scanner
from scanners.batch_ocr_poller_scanner import run_batch_ocr_poller_scanner
from scanners.batch_embedding_poller_scanner import (
    run_batch_embedding_poller_scanner,
)
from scanners.graph_resolution_scanner import run_graph_resolution_scanner
from jobs.ocr_job import ocr_job
from jobs.chunking_job import chunking_job
from jobs.embedding_job import embedding_job
from jobs.spell_check_job import spell_check_job
from jobs.summary_job import summary_job
from jobs.auto_correct_job import auto_correct_job
from jobs.knowledge_graph_job import knowledge_graph_job
from jobs.graph_resolution_job import graph_resolution_job
from jobs.rag_eval_job import rag_eval_job
from jobs.history_extraction_job import extract_book_history_terms_task


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

    functions = [
        ocr_job,
        chunking_job,
        embedding_job,
        spell_check_job,
        summary_job,
        auto_correct_job,
        knowledge_graph_job,
        graph_resolution_job,
        rag_eval_job,
        extract_book_history_terms_task,
    ]

    # Build cron jobs list conditionally based on feature flags
    cron_jobs = [
        cron(run_auto_correct_scanner, hour=3, minute=0, run_at_startup=False),
        cron(
            run_gcs_discovery_scanner,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
        cron(run_pipeline_driver, run_at_startup=True),
        cron(run_ocr_scanner),
        cron(run_batch_ocr_poller_scanner),
        cron(run_chunking_scanner),
        cron(run_embedding_scanner),
        cron(run_batch_embedding_poller_scanner),
        cron(run_spell_check_scanner),
        cron(run_stale_watchdog, minute={0, 30}),
        cron(
            run_summary_scanner, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}
        ),
        cron(
            run_graph_resolution_scanner,
            minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55},
        ),
        cron(run_event_dispatcher, run_at_startup=True),
        cron(run_maintenance_scanner, hour=3, minute=0),
    ]

    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    on_startup = worker_startup
    on_shutdown = worker_shutdown


# Wrap all worker job functions with track_request_id to support request_id context propagation
WorkerSettings.functions = [track_request_id(f) for f in WorkerSettings.functions]


def safe_cron_job(func):
    """Wrapper decorator to prevent cron job exceptions from crashing the worker."""
    cron_logger = logging.getLogger(func.__module__)

    @functools.wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        try:
            return await func(ctx, *args, **kwargs)
        except Exception as exc:
            log_json(
                cron_logger,
                logging.ERROR,
                "Cron job failed with unhandled exception",
                cron_job=func.__name__,
                error=str(exc),
            )
            # Suppress exception so worker doesn't crash

    return wrapper


# Wrap all worker cron jobs with safe_cron_job to prevent unhandled exceptions from crashing the worker
for job in WorkerSettings.cron_jobs:
    job.coroutine = safe_cron_job(job.coroutine)
