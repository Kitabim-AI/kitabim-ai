"""Batch jobs repository with SQLAlchemy"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import BatchJob, BatchRequest
from app.db.repositories.base import BaseRepository


class BatchJobsRepository(BaseRepository[BatchJob]):
    """Repository for Gemini Batch API jobs"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BatchJob)

    async def create_job(
        self, 
        job_type: str, 
        request_count: int, 
        input_file_uri: Optional[str] = None
    ) -> BatchJob:
        """Create a new batch job record"""
        job = BatchJob(
            job_type=job_type,
            request_count=request_count,
            input_file_uri=input_file_uri,
            status="created"
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_by_remote_id(self, remote_id: str) -> Optional[BatchJob]:
        """Get batch job by Google remote job ID"""
        stmt = select(BatchJob).where(BatchJob.remote_job_id == remote_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_jobs(self, job_type: Optional[str] = None) -> List[BatchJob]:
        """Get jobs that are currently in progress or just created"""
        stmt = select(BatchJob).where(BatchJob.status.in_(["submitted", "created"]))
        if job_type:
            stmt = stmt.where(BatchJob.job_type == job_type)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_job_status(
        self, 
        job_id: UUID, 
        status: str, 
        remote_job_id: Optional[str] = None,
        remote_status: Optional[str] = None,
        output_file_uri: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update batch job status and related fields"""
        values = {
            "status": status,
            "updated_at": datetime.now(timezone.utc)
        }
        if remote_job_id:
            values["remote_job_id"] = remote_job_id
        if remote_status:
            values["remote_status"] = remote_status
        if output_file_uri:
            values["output_file_uri"] = output_file_uri
        if error_message:
            values["error_message"] = error_message
        if status == "completed":
            values["completed_at"] = datetime.now(timezone.utc)

        stmt = update(BatchJob).where(BatchJob.id == job_id).values(**values)
        await self.session.execute(stmt)
        await self.session.flush()


class BatchRequestsRepository(BaseRepository[BatchRequest]):
    """Repository for individual requests within a Gemini Batch Job"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BatchRequest)

    async def create_requests(self, requests_data: List[dict]) -> None:
        """Bulk insert batch requests"""
        for data in requests_data:
            req = BatchRequest(**data)
            self.session.add(req)
        await self.session.flush()

    async def find_by_job(self, batch_job_id: UUID) -> List[BatchRequest]:
        """Find all requests associated with a batch job"""
        stmt = select(BatchRequest).where(BatchRequest.batch_job_id == batch_job_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status_by_job(self, batch_job_id: UUID, status: str) -> int:
        """Update status for all requests in a job"""
        stmt = (
            update(BatchRequest)
            .where(BatchRequest.batch_job_id == batch_job_id)
            .values(status=status)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount
