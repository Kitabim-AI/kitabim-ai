"""Admin endpoints for Uyghur history dictionary extraction and staging queue."""

from __future__ import annotations

import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings
from app.db.session import get_session
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.models.user import User
from auth.dependencies import require_admin

logger = logging.getLogger(__name__)

router = APIRouter()


async def enqueue_task(task_name: str, *args, **kwargs) -> str:
    """Enqueue an ARQ background job."""
    try:
        redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        job = await redis.enqueue_job(task_name, *args, **kwargs)
        await redis.aclose()
        return job.job_id if job else "queued"
    except Exception as exc:
        logger.warning(f"Could not enqueue ARQ job {task_name}: {exc}")
        return "queued-fallback"


class ExtractHistoryRequest(BaseModel):
    min_significance: Optional[int] = 5


class BulkApproveRequest(BaseModel):
    staging_ids: List[int]


ExtractHistoryRequest.model_rebuild()
BulkApproveRequest.model_rebuild()


@router.post("/books/{book_id}/extract-history")
async def trigger_history_extraction(
    book_id: str,
    req: ExtractHistoryRequest,
    current_admin: User = Depends(require_admin),
):
    """Trigger background ARQ extraction task for a specific book ("تارىخىي ئاتالغۇلارنى تېپىش")."""
    job_id = await enqueue_task(
        "extract_book_history_terms_task",
        book_id,
        req.min_significance or 5,
    )
    return {
        "status": "queued",
        "jobId": job_id,
        "bookId": book_id,
        "message": "تارىخىي ئاتالغۇلارنى تېپىش ۋەزىپىسى باشلاندى.",
    }


@router.get("/history-dictionary/staging")
async def list_staging_terms(
    status_filter: str = Query("pending", alias="status"),
    category: Optional[str] = Query(None),
    min_significance: Optional[int] = Query(None, alias="minSignificance"),
    book_id: Optional[str] = Query(None, alias="bookId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """List staging queue terms ordered by significance_score DESC."""
    repo = DictionaryRepository(db)
    return await repo.get_staging_terms(
        status=status_filter,
        category=category,
        min_significance=min_significance,
        book_id=book_id,
        page=page,
        page_size=page_size,
    )


@router.post("/history-dictionary/staging/{staging_id}/approve")
async def approve_staging_term(
    staging_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Approve candidate term and publish to live history_dictionary."""
    repo = DictionaryRepository(db)
    result = await repo.approve_staging_term(staging_id)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staging candidate not found or already processed",
        )
    return {"status": "success", "item": result}


@router.post("/history-dictionary/staging/bulk-approve")
async def bulk_approve_staging_terms(
    req: BulkApproveRequest,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Bulk approve multiple staging candidate terms."""
    repo = DictionaryRepository(db)
    approved_count = 0
    for sid in req.staging_ids:
        res = await repo.approve_staging_term(sid)
        if res:
            approved_count += 1
    return {"status": "success", "approvedCount": approved_count}


@router.delete("/history-dictionary/staging/{staging_id}")
async def reject_staging_term(
    staging_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Reject candidate term."""
    repo = DictionaryRepository(db)
    success = await repo.reject_staging_term(staging_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Staging candidate not found",
        )
    return {"status": "success", "message": "Candidate rejected"}
