from __future__ import annotations

from typing import Optional

from arq import create_pool, cron
from arq.connections import RedisSettings

from app.core.config import settings
from app.db import session as db_session  # Import module to access global dynamically
from app.db.session import init_db, close_db
from app.db.repositories.jobs import JobsRepository
from app.db.repositories.books import BooksRepository
from app.services.pdf_service import process_pdf_task
from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json
from app.services.discovery_service import DiscoveryService
import logging

logger = logging.getLogger("app.queue")

_POOL = None


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def _get_pool():
    global _POOL
    if _POOL is None:
        _POOL = await create_pool(_redis_settings())
    return _POOL


async def trigger_discovery_check():
    """Triggered after job completion to check for new books"""
    async with db_session.async_session_factory() as session:
        discovery = DiscoveryService(session)
        try:
            result = await discovery.sync_gcs_books(force=False)
            log_json(logger, logging.INFO, "Post-job discovery check", **result)
        except Exception as e:
            log_json(logger, logging.WARNING, "Discovery check failed", error=str(e))


async def enqueue_pdf_processing(
    book_id: str,
    reason: str = "requested",
    background_tasks=None,
) -> dict:
    job_key = f"process_pdf:{book_id}"

    # Check if session factory is initialized
    if db_session.async_session_factory is None:
        raise RuntimeError("Database not initialized. async_session_factory is None.")

    # Use a fresh session to create/reset the job
    async with db_session.async_session_factory() as session:
        repo = JobsRepository(session)
        await repo.create_or_reset(job_key, "process_pdf", book_id, {"reason": reason})
        await session.commit()

    redis = await _get_pool()
    await redis.enqueue_job("process_pdf_job", book_id=book_id, job_key=job_key)
    return {"status": "queued", "jobKey": job_key}


async def worker_startup(ctx):
    # Configure logging level from environment
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    configure_logging(level=log_level)
    configure_langchain()
    # Initialize SQLAlchemy (PostgreSQL)
    await init_db()

    # Seed system configurations
    try:
        from app.db.seeds import seed_system_configs
        async with db_session.async_session_factory() as session:
            await seed_system_configs(session)
    except Exception as exc:
        log_json(logger, logging.ERROR, "Worker system config seeding failed", error=str(exc))


async def worker_shutdown(ctx):
    await close_db()


async def process_pdf_job(ctx, book_id: str, job_key: Optional[str] = None):
    try:
        await process_pdf_task(book_id, job_key, raise_on_error=True)

        # Trigger next discovery after successful completion
        await trigger_discovery_check()

    except Exception as exc:
        job_try = ctx.get("job_try", 1)
        if job_key:
            # Use fresh session for status update
            async with db_session.async_session_factory() as session:
                repo = JobsRepository(session)
                if job_try < settings.queue_max_retries:
                    await repo.update_status(job_key, "retrying", str(exc))
                else:
                    await repo.update_status(job_key, "failed", str(exc))
                await session.commit()
        raise


async def scheduled_gcs_sync(ctx):
    """Scheduled cron job to discover books in GCS"""
    async with db_session.async_session_factory() as session:
        discovery = DiscoveryService(session)
        try:
            result = await discovery.sync_gcs_books()
            log_json(logger, logging.INFO, "Auto GCS sync finished", **result)
        except Exception as e:
            log_json(logger, logging.ERROR, "Auto GCS sync failed", error=str(e))
            raise


# ARQ Worker Settings (Deprecated in favor of app.worker)
# The worker now uses app.worker.WorkerSettings
