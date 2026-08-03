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
from app.core.i18n import t
from app.db.session import get_session
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.services.dictionary_staging_service import (
    DictionaryStagingService,
    StagingConflictsUnresolvedError,
)
from app.services.history_extraction_service import HistoryFactSynthesisError
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


class ResolveFactRequest(BaseModel):
    status: str
    text: Optional[str] = None


ExtractHistoryRequest.model_rebuild()
BulkApproveRequest.model_rebuild()
ResolveFactRequest.model_rebuild()


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
        "message": t("messages.history_extraction_started"),
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
    service = DictionaryStagingService(db)
    try:
        result = await service.approve_staging_term(staging_id)
    except StagingConflictsUnresolvedError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=t("errors.staging_conflicts_unresolved"),
        )
    except HistoryFactSynthesisError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=t("errors.staging_synthesis_failed"),
        )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("errors.staging_candidate_not_found"),
        )
    return {"status": "success", "item": result}


@router.post("/history-dictionary/staging/bulk-approve")
async def bulk_approve_staging_terms(
    req: BulkApproveRequest,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Bulk approve multiple staging candidate terms. Items with unresolved
    conflicts or a failed synthesis are skipped and reported, not silently dropped."""
    service = DictionaryStagingService(db)
    approved_count = 0
    results = []
    for sid in req.staging_ids:
        try:
            res = await service.approve_staging_term(sid)
        except StagingConflictsUnresolvedError:
            results.append({"stagingId": sid, "status": "conflict"})
            continue
        except HistoryFactSynthesisError:
            results.append({"stagingId": sid, "status": "synthesis_failed"})
            continue
        if res:
            approved_count += 1
            results.append({"stagingId": sid, "status": "approved"})
        else:
            results.append({"stagingId": sid, "status": "not_found"})
    return {"status": "success", "approvedCount": approved_count, "results": results}


@router.delete("/history-dictionary/staging/{staging_id}")
async def reject_staging_term(
    staging_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Reject candidate term."""
    service = DictionaryStagingService(db)
    success = await service.reject_staging_term(staging_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("errors.staging_candidate_not_found"),
        )
    return {"status": "success", "message": "Candidate rejected"}


@router.patch("/history-dictionary/staging/{staging_id}/facts/{fact_id}")
async def resolve_staging_fact(
    staging_id: int,
    fact_id: int,
    req: ResolveFactRequest,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Resolve a single fact (accept/reject/edit) on a pending staging candidate."""
    if req.status not in ("active", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=t("errors.invalid_fact_status"),
        )
    service = DictionaryStagingService(db)
    result = await service.resolve_fact(staging_id, fact_id, req.status, req.text)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("errors.staging_fact_not_found"),
        )
    return {"status": "success", "item": result}


@router.post("/history-dictionary/staging/{staging_id}/synthesize")
async def synthesize_staging_definition(
    staging_id: int,
    db: AsyncSession = Depends(get_session),
    current_admin: User = Depends(require_admin),
):
    """Regenerate the preview `definition` from the candidate's current active facts."""
    service = DictionaryStagingService(db)
    try:
        definition = await service.synthesize_definition(staging_id)
    except HistoryFactSynthesisError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=t("errors.staging_synthesis_failed"),
        )
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=t("errors.staging_candidate_not_found"),
        )
    return {"status": "success", "definition": definition}
