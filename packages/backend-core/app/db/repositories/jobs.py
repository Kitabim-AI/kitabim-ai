"""Jobs repository with SQLAlchemy"""
from __future__ import annotations

from typing import Optional
from datetime import datetime

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Job
from app.db.repositories.base import BaseRepository


class JobsRepository(BaseRepository[Job]):
    """Repository for background jobs"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Job)

    async def get_by_key(self, job_key: str) -> Optional[Job]:
        """Get job by job_key"""
        result = await self.session.execute(
            select(Job).where(Job.job_key == job_key)
        )
        return result.scalar_one_or_none()

    async def create_or_reset(
        self,
        job_key: str,
        job_type: str,
        book_id: str,
        metadata: Optional[dict] = None
    ) -> Job:
        """Create a new job or reset an existing failed/completed job"""
        now = datetime.utcnow()
        existing = await self.get_by_key(job_key)

        if existing:
            if existing.status in {"queued", "running"}:
                return existing
            
            # Reset existing job
            existing.status = "queued"
            existing.type = job_type
            existing.book_id = book_id
            existing.attempts = 0
            existing.last_error = None
            existing.updated_at = now
            if metadata is not None:
                existing.payload = metadata
            
            await self.session.flush()
            return existing

        # Create new job
        new_job = Job(
            job_key=job_key,
            type=job_type,
            book_id=book_id,
            status="queued",
            attempts=0,
            payload=metadata or {},
            created_at=now,
            updated_at=now
        )
        self.session.add(new_job)
        await self.session.flush()
        return new_job

    async def update_status(self, job_key: str, status: str, error: Optional[str] = None) -> None:
        """Update job status and optional error"""
        stmt = (
            update(Job)
            .where(Job.job_key == job_key)
            .values(
                status=status,
                last_error=error,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def increment_attempts(self, job_key: str) -> None:
        """Increment job attempts count"""
        stmt = (
            update(Job)
            .where(Job.job_key == job_key)
            .values(
                attempts=Job.attempts + 1,
                updated_at=datetime.utcnow()
            )
        )
        await self.session.execute(stmt)
        await self.session.flush()


def get_jobs_repository(session: AsyncSession) -> JobsRepository:
    """Factory function for dependency injection"""
    return JobsRepository(session)
