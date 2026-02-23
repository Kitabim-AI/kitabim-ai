"""Statistics API endpoints"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.db.session import get_session
from app.db.models import Book, Page, Job, BatchJob
from app.auth.dependencies import require_admin
from app.services.batch_service import BatchService

router = APIRouter()


class BookStatusCount(BaseModel):
    status: str
    count: int


class JobStatusCount(BaseModel):
    status: str
    count: int


class JobTypeCount(BaseModel):
    type: str
    count: int


class PageStats(BaseModel):
    total: int
    indexed: int
    unindexed: int
    percentage_indexed: float
    error: int = 0
    pages_by_status: list["PageStatusCount"] = []


class PageStatusCount(BaseModel):
    status: str
    count: int


class SystemStats(BaseModel):
    total_books: int
    books_by_status: list[BookStatusCount]
    page_stats: PageStats
    jobs_by_status: list[JobStatusCount]
    jobs_by_type: list[JobTypeCount]
    batch_jobs_by_status: list[JobStatusCount] = []


@router.get("/", response_model=SystemStats)
async def get_system_stats(
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get system-wide statistics (admin only)"""

    # Count total books
    total_books_stmt = select(func.count()).select_from(Book)
    total_books_result = await session.execute(total_books_stmt)
    total_books = total_books_result.scalar() or 0

    # Count books by status
    books_by_status_stmt = (
        select(Book.status, func.count(Book.id))
        .group_by(Book.status)
        .order_by(func.count(Book.id).desc())
    )
    books_by_status_result = await session.execute(books_by_status_stmt)
    books_by_status = [
        BookStatusCount(status=status, count=count)
        for status, count in books_by_status_result.all()
    ]

    # Count total pages
    total_pages_stmt = select(func.count()).select_from(Page)
    total_pages_result = await session.execute(total_pages_stmt)
    total_pages = total_pages_result.scalar() or 0

    # Count indexed pages
    indexed_pages_stmt = select(func.count()).select_from(Page).where(Page.is_indexed == True)
    indexed_pages_result = await session.execute(indexed_pages_stmt)
    indexed_pages = indexed_pages_result.scalar() or 0

    # Count error pages
    error_pages_stmt = select(func.count()).select_from(Page).where(Page.status == "error")
    error_pages_result = await session.execute(error_pages_stmt)
    error_pages = error_pages_result.scalar() or 0

    # Pages by status
    pages_by_status_stmt = (
        select(Page.status, func.count(Page.id))
        .group_by(Page.status)
        .order_by(func.count(Page.id).desc())
    )
    pages_by_status_result = await session.execute(pages_by_status_stmt)
    pages_by_status = [
        PageStatusCount(status=status or "unknown", count=count)
        for status, count in pages_by_status_result.all()
    ]

    # Calculate unindexed and percentage
    unindexed_pages = total_pages - indexed_pages
    percentage_indexed = (indexed_pages / total_pages * 100) if total_pages > 0 else 0.0

    # Count jobs by status
    jobs_by_status_stmt = (
        select(Job.status, func.count(Job.job_key))
        .group_by(Job.status)
        .order_by(func.count(Job.job_key).desc())
    )
    jobs_by_status_result = await session.execute(jobs_by_status_stmt)
    jobs_by_status = [
        JobStatusCount(status=status or "unknown", count=count)
        for status, count in jobs_by_status_result.all()
    ]

    # Count jobs by type
    jobs_by_type_stmt = (
        select(Job.type, func.count(Job.job_key))
        .group_by(Job.type)
        .order_by(func.count(Job.job_key).desc())
    )
    jobs_by_type_result = await session.execute(jobs_by_type_stmt)
    jobs_by_type = [
        JobTypeCount(type=job_type or "unknown", count=count)
        for job_type, count in jobs_by_type_result.all()
    ]

    # Count batch jobs by status
    batch_jobs_stmt = (
        select(BatchJob.status, func.count(BatchJob.id))
        .group_by(BatchJob.status)
        .order_by(func.count(BatchJob.id).desc())
    )
    batch_jobs_result = await session.execute(batch_jobs_stmt)
    batch_jobs_by_status = [
        JobStatusCount(status=status or "unknown", count=count)
        for status, count in batch_jobs_result.all()
    ]

    return {
        "total_books": total_books,
        "books_by_status": books_by_status,
        "page_stats": {
            "total": total_pages,
            "indexed": indexed_pages,
            "unindexed": unindexed_pages,
            "percentage_indexed": round(percentage_indexed, 2),
            "error": error_pages,
            "pages_by_status": pages_by_status
        },
        "jobs_by_status": jobs_by_status,
        "jobs_by_type": jobs_by_type,
        "batch_jobs_by_status": batch_jobs_by_status
    }


@router.post("/batch/submit")
async def trigger_batch_submission(
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger batch submission (admin only)"""
    batch_service = BatchService(session)
    # 1. First, chunk any pages that finished OCR
    await batch_service.chunk_ocr_done_pages(limit=100)

    # 2. Submit new OCR batches
    ocr_job_id = await batch_service.submit_ocr_batch(limit=1000)

    # 3. Submit new Embedding batches
    embed_job_id = await batch_service.submit_embedding_batch(limit=2000)

    return {
        "status": "success",
        "ocr_batch_id": str(ocr_job_id) if ocr_job_id else None,
        "embed_batch_id": str(embed_job_id) if embed_job_id else None
    }


@router.post("/batch/poll")
async def trigger_batch_polling(
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Manually trigger batch polling and processing (admin only)"""
    batch_service = BatchService(session)
    # 1. Poll and process results
    await batch_service.poll_and_process_jobs()

    # 2. Finalize statuses for completed books/pages
    await batch_service.finalize_indexed_pages()

    return {"status": "success"}
