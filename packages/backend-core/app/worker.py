from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.queue import (
    process_pdf_job, worker_shutdown, worker_startup, scheduled_gcs_sync,
    gemini_batch_submission_cron, gemini_batch_polling_cron
)
from app.services.maintenance import rescue_stale_jobs


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_pdf_job, scheduled_gcs_sync, gemini_batch_submission_cron, gemini_batch_polling_cron]
    cron_jobs = [
        cron(rescue_stale_jobs, run_at_startup=True, minute={0, 30}),
        # Reduced to 30 minutes - event-driven discovery is primary now
        cron(scheduled_gcs_sync, minute={0, 30}),
        # Gemini Batch Submission: Every 15 minutes
        cron(gemini_batch_submission_cron, minute={0, 15, 30, 45}),
        # Gemini Batch Polling: Every 1 minute (dynamic early-exit inside function based on SystemConfig)
        cron(gemini_batch_polling_cron)
    ]
    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    max_retries = settings.queue_max_retries
    on_startup = worker_startup
    on_shutdown = worker_shutdown
