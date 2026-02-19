from arq.connections import RedisSettings
from arq.cron import cron

from app.core.config import settings
from app.queue import process_pdf_job, worker_shutdown, worker_startup, scheduled_gcs_sync
from app.services.maintenance import rescue_stale_jobs


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    functions = [process_pdf_job, scheduled_gcs_sync]
    cron_jobs = [
        cron(rescue_stale_jobs, run_at_startup=True, minute={0, 30}),
        # Reduced to 30 minutes - event-driven discovery is primary now
        cron(scheduled_gcs_sync, minute={0, 30})
    ]
    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    max_retries = settings.queue_max_retries
    on_startup = worker_startup
    on_shutdown = worker_shutdown
