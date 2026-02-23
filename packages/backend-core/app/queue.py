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
from app.services.batch_service import BatchService
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
    force_realtime: bool = False,
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
    await redis.enqueue_job("process_pdf_job", book_id=book_id, job_key=job_key, force_realtime=force_realtime)
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


async def process_pdf_job(ctx, book_id: str, job_key: Optional[str] = None, force_realtime: bool = False):
    try:
        await process_pdf_task(book_id, job_key, raise_on_error=True, force_realtime=force_realtime)

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


async def gemini_batch_submission_cron(ctx):
    """Submits pending OCR and Embedding work to Gemini"""
    async with db_session.async_session_factory() as session:
        from app.langchain.models import is_llm_available
        if not await is_llm_available():
            log_json(logger, logging.WARNING, "LLM circuit breaker open, skipping batch submission")
            return

        batch_service = BatchService(session)
        try:
            # 1. First, chunk any pages that finished OCR
            await batch_service.chunk_ocr_done_pages(limit=1000)
            
            # 2. Submit new OCR batches
            await batch_service.submit_ocr_batch(limit=5000)
            
            # 3. Submit new Embedding batches
            await batch_service.submit_embedding_batch(limit=10000)
            
            log_json(logger, logging.INFO, "Batch submission cron finished")
        except Exception as e:
            log_json(logger, logging.ERROR, "Batch submission cron failed", error=str(e))


async def gemini_batch_polling_cron(ctx):
    """Checks for completed Gemini Batch jobs and processes results dynamically"""
    import time
    from app.db.repositories.system_configs import SystemConfigsRepository

    async with db_session.async_session_factory() as session:
        # Check system config polling interval
        config_repo = SystemConfigsRepository(session)
        interval_str = await config_repo.get_value("batch_polling_interval_minutes", "10")
        last_polled_str = await config_repo.get_value("batch_last_polled_at", "0")
        
        try:
            interval_minutes = int(interval_str)
            last_polled = float(last_polled_str)
        except ValueError:
            interval_minutes = 10
            last_polled = 0
            
        current_time = time.time()
        elapsed_minutes = (current_time - last_polled) / 60.0
        
        if elapsed_minutes < interval_minutes:
            # Skip polling, interval hasn't passed yet
            return

        # Update last polled time
        await config_repo.set_value("batch_last_polled_at", str(current_time))
        
        batch_service = BatchService(session)
        try:
            # 1. Poll and process results
            await batch_service.poll_and_process_jobs()
            
            # 2. Finalize statuses for completed books/pages
            await batch_service.finalize_indexed_pages()
            
            log_json(logger, logging.INFO, "Batch polling cron finished")
        except Exception as e:
            log_json(logger, logging.ERROR, "Batch polling cron failed", error=str(e))


# ARQ Worker Settings (Deprecated in favor of app.worker)
# The worker now uses app.worker.WorkerSettings
