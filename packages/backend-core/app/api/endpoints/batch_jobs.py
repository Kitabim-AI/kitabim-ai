"""Batch Jobs Admin API endpoints"""
from __future__ import annotations

from typing import Optional, List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.session import get_session
from app.db.models import BatchJob, BatchRequest
from app.auth.dependencies import require_admin
from app.services.batch_service import BatchService
from app.services.gemini_batch_client import GeminiBatchClient

router = APIRouter()


def to_camel(string: str) -> str:
    """Convert snake_case to camelCase"""
    components = string.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])


class BatchJobResponse(BaseModel):
    """Batch job response schema with camelCase conversion"""
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True
    )

    id: UUID
    job_type: str
    remote_job_id: Optional[str] = None
    status: str
    remote_status: Optional[str] = None
    request_count: int
    input_file_uri: Optional[str] = None
    output_file_uri: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class BatchJobStats(BaseModel):
    """Statistics about batch jobs"""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    total_jobs: int
    jobs_by_status: List["BatchJobStatusCount"]
    jobs_by_type: List["BatchJobTypeCount"]
    total_requests_processed: int
    active_jobs_count: int


class BatchJobStatusCount(BaseModel):
    """Count of jobs by status"""
    status: str
    count: int


class BatchJobTypeCount(BaseModel):
    """Count of jobs by type"""
    job_type: str
    count: int


class SubmitBatchResponse(BaseModel):
    """Response from manual batch submission"""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    success: bool
    job_id: Optional[UUID] = None
    message: str


@router.get("/batch-jobs/", response_model=List[BatchJobResponse])
async def list_batch_jobs(
    status: Optional[str] = None,
    job_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    List batch jobs with optional filtering.

    Admin only endpoint.
    """
    stmt = select(BatchJob).order_by(BatchJob.created_at.desc())

    if status:
        stmt = stmt.where(BatchJob.status == status)
    if job_type:
        stmt = stmt.where(BatchJob.job_type == job_type)

    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    jobs = result.scalars().all()

    return [BatchJobResponse.model_validate(job) for job in jobs]


@router.get("/batch-jobs/stats", response_model=BatchJobStats)
async def get_batch_job_stats(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Get statistics about batch jobs.

    Admin only endpoint.
    """
    # Total jobs
    total_stmt = select(func.count()).select_from(BatchJob)
    total_result = await session.execute(total_stmt)
    total_jobs = total_result.scalar() or 0

    # Jobs by status
    status_stmt = select(
        BatchJob.status,
        func.count().label('count')
    ).group_by(BatchJob.status)
    status_result = await session.execute(status_stmt)
    jobs_by_status = [
        BatchJobStatusCount(status=row.status, count=row.count)
        for row in status_result
    ]

    # Jobs by type
    type_stmt = select(
        BatchJob.job_type,
        func.count().label('count')
    ).group_by(BatchJob.job_type)
    type_result = await session.execute(type_stmt)
    jobs_by_type = [
        BatchJobTypeCount(job_type=row.job_type, count=row.count)
        for row in type_result
    ]

    # Total requests processed
    requests_stmt = select(func.sum(BatchJob.request_count)).select_from(
        BatchJob
    ).where(BatchJob.status == 'completed')
    requests_result = await session.execute(requests_stmt)
    total_requests = requests_result.scalar() or 0

    # Active jobs
    active_stmt = select(func.count()).select_from(BatchJob).where(
        BatchJob.status.in_(['created', 'submitted'])
    )
    active_result = await session.execute(active_stmt)
    active_count = active_result.scalar() or 0

    return BatchJobStats(
        total_jobs=total_jobs,
        jobs_by_status=jobs_by_status,
        jobs_by_type=jobs_by_type,
        total_requests_processed=total_requests,
        active_jobs_count=active_count
    )


@router.get("/batch-jobs/{job_id}", response_model=BatchJobResponse)
async def get_batch_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Get details of a specific batch job.

    Admin only endpoint.
    """
    stmt = select(BatchJob).where(BatchJob.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")

    return BatchJobResponse.model_validate(job)


@router.post("/batch-jobs/submit-ocr", response_model=SubmitBatchResponse)
async def submit_ocr_batch(
    limit: int = 1000,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Manually trigger OCR batch submission.

    Admin only endpoint.
    """
    batch_service = BatchService(session)

    try:
        job_id = await batch_service.submit_ocr_batch(limit=limit)

        if job_id:
            return SubmitBatchResponse(
                success=True,
                job_id=job_id,
                message=f"OCR batch job submitted successfully"
            )
        else:
            return SubmitBatchResponse(
                success=False,
                message="No pending OCR pages found"
            )
    except Exception as e:
        return SubmitBatchResponse(
            success=False,
            message=f"Failed to submit OCR batch: {str(e)}"
        )


@router.post("/batch-jobs/submit-embedding", response_model=SubmitBatchResponse)
async def submit_embedding_batch(
    limit: int = 2000,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Manually trigger embedding batch submission.

    Admin only endpoint.
    """
    batch_service = BatchService(session)

    try:
        job_id = await batch_service.submit_embedding_batch(limit=limit)

        if job_id:
            return SubmitBatchResponse(
                success=True,
                job_id=job_id,
                message=f"Embedding batch job submitted successfully"
            )
        else:
            return SubmitBatchResponse(
                success=False,
                message="No chunks needing embeddings found"
            )
    except Exception as e:
        return SubmitBatchResponse(
            success=False,
            message=f"Failed to submit embedding batch: {str(e)}"
        )


@router.post("/batch-jobs/{job_id}/cancel")
async def cancel_batch_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Cancel a running batch job.

    Admin only endpoint.
    """
    # Get the job
    stmt = select(BatchJob).where(BatchJob.id == job_id)
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(status_code=404, detail="Batch job not found")

    if job.status not in ['created', 'submitted']:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'"
        )

    if not job.remote_job_id:
        raise HTTPException(
            status_code=400,
            detail="Job has no remote ID, cannot cancel"
        )

    # Cancel via Gemini API
    client = GeminiBatchClient()
    try:
        client.cancel_job(job.remote_job_id)
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel remote job: {str(e)}"
        )

    # Update job status in DB
    job.status = 'failed'
    job.error_message = 'Cancelled by admin'
    job.updated_at = datetime.now()
    await session.commit()

    return {"success": True, "message": "Batch job cancelled"}


@router.post("/batch-jobs/poll")
async def poll_batch_jobs(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Manually trigger batch job polling.

    Admin only endpoint.
    """
    batch_service = BatchService(session)

    try:
        await batch_service.poll_and_process_jobs()
        return {"success": True, "message": "Batch jobs polled successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to poll batch jobs: {str(e)}"
        )


@router.post("/batch-jobs/finalize")
async def finalize_pages(
    session: AsyncSession = Depends(get_session),
    _: dict = Depends(require_admin)
):
    """
    Manually trigger page finalization (marking pages as indexed).

    Admin only endpoint.
    """
    batch_service = BatchService(session)

    try:
        await batch_service.finalize_indexed_pages()
        return {"success": True, "message": "Pages finalized successfully"}
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to finalize pages: {str(e)}"
        )
