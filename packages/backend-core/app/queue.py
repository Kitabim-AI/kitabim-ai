from __future__ import annotations

from typing import Optional

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.db import session as db_session  # Import module to access global dynamically
from app.db.session import init_db, close_db
from app.db.repositories.jobs import JobsRepository
from app.db.repositories.books import BooksRepository
from app.services.pdf_service import process_pdf_task
from app.langchain import configure_langchain
from app.utils.observability import configure_logging

_POOL = None


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(settings.redis_url)


async def _get_pool():
    global _POOL
    if _POOL is None:
        _POOL = await create_pool(_redis_settings())
    return _POOL


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
    configure_logging()
    configure_langchain()
    # Initialize SQLAlchemy (PostgreSQL)
    await init_db()


async def worker_shutdown(ctx):
    await close_db()


async def process_pdf_job(ctx, book_id: str, job_key: Optional[str] = None):
    try:
        await process_pdf_task(book_id, job_key, raise_on_error=True)
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


# ARQ Worker Settings
class WorkerSettings:
    """ARQ worker configuration"""
    functions = [process_pdf_job]
    redis_settings = _redis_settings()
    on_startup = worker_startup
    on_shutdown = worker_shutdown
    max_jobs = settings.queue_max_jobs
    job_timeout = settings.queue_job_timeout
    max_tries = settings.queue_max_retries
