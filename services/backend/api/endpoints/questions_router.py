"""Admin and public API endpoints for RAG evaluation questions"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository
from app.models.schemas import (
    RagQuestionsPage,
    RagQuestionAdmin,
    RagQuestionToggle,
    RagQuestionToggleResponse,
)
from auth.dependencies import require_admin

router = APIRouter()


@router.get("/admin/questions", response_model=RagQuestionsPage)
async def get_admin_questions(
    limit: int = 20,
    offset: int = 0,
    query: Optional[str] = None,
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Return all RAG evaluation questions, newest first, paginated.

    Admin-only endpoint.
    """
    repo = RAGEvaluationsRepository(session)
    items, total = await repo.get_questions_paginated(
        limit=limit, offset=offset, query=query
    )
    return RagQuestionsPage(
        items=[RagQuestionAdmin.model_validate(item) for item in items],
        total=total,
        offset=offset,
        limit=limit,
    )


@router.patch(
    "/admin/questions/{eval_id}/featured",
    response_model=RagQuestionToggleResponse,
)
async def toggle_featured_question(
    eval_id: int,
    body: RagQuestionToggle,
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """
    Set or clear the show_on_homepage flag for a question.

    Admin-only endpoint.
    """
    repo = RAGEvaluationsRepository(session)
    updated = await repo.toggle_show_on_homepage(eval_id, body.show_on_homepage)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found",
        )
    return RagQuestionToggleResponse(
        id=updated.id,
        show_on_homepage=updated.show_on_homepage,
    )


@router.get("/featured", response_model=List[str])
async def get_featured_questions(
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
):
    """
    Return questions flagged for home-page display (show_on_homepage=True).

    Public endpoint — no auth required.
    """
    repo = RAGEvaluationsRepository(session)
    return await repo.get_featured_questions(limit=limit)
