from __future__ import annotations

from datetime import datetime
from typing import Any, Optional


from sqlalchemy.ext.asyncio import AsyncSession
from app.db.repositories.jobs import JobsRepository


async def create_or_reset_job(session: AsyncSession, job_key: str, job_type: str, book_id: str, metadata: Optional[dict] = None):
    repo = JobsRepository(session)
    job = await repo.create_or_reset(job_key, job_type, book_id, metadata)
    return job


async def update_job_status(session: AsyncSession, job_key: str, status: str, error: Optional[str] = None) -> None:
    repo = JobsRepository(session)
    await repo.update_status(job_key, status, error)


async def increment_attempts(session: AsyncSession, job_key: str) -> None:
    repo = JobsRepository(session)
    await repo.increment_attempts(job_key)
