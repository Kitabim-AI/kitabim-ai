"""Admin and public API endpoints for RAG evaluation questions"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository
from app.models.schemas import (
    ChatCostInfo,
    FeaturedQuestionAnswerResponse,
    FeaturedQuestionItem,
    RagQuestionsPage,
    RagQuestionAdmin,
    RagQuestionToggle,
    RagQuestionToggleResponse,
)
from app.utils.citation_fixer import fix_malformed_citations
from auth.dependencies import require_admin

router = APIRouter()


@router.get("/admin/questions", response_model=RagQuestionsPage)
async def get_admin_questions(
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
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


@router.get("/featured", response_model=List[FeaturedQuestionItem])
async def get_featured_questions(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
):
    """
    Return questions flagged for home-page display (show_on_homepage=True).

    Public endpoint — no auth required.
    """
    repo = RAGEvaluationsRepository(session)
    rows = await repo.get_featured_question_items(limit=limit)
    return [FeaturedQuestionItem.model_validate(row) for row in rows]


@router.get("/featured/answer", response_model=FeaturedQuestionAnswerResponse)
async def get_featured_question_answer(
    question: str = Query(..., min_length=1, max_length=500),
    eval_id: Optional[int] = Query(None),
    session: AsyncSession = Depends(get_session),
):
    """
    Return the stored answer for a homepage sample question if all evaluation
    scores are >= 80%.

    Public endpoint — only inspects rows with show_on_homepage=True.
    """
    repo = RAGEvaluationsRepository(session)
    cached_eval = await repo.get_qualifying_sample_evaluation(
        question=question,
        eval_id=eval_id,
    )
    if cached_eval is None or not cached_eval.answer:
        return FeaturedQuestionAnswerResponse(cached=False, question=question)

    used_book_ids = await repo.resolve_sample_used_book_ids(cached_eval)
    return FeaturedQuestionAnswerResponse(
        cached=True,
        eval_id=cached_eval.id,
        question=cached_eval.question,
        answer=fix_malformed_citations(cached_eval.answer),
        used_book_ids=used_book_ids,
        cost=ChatCostInfo(
            input_tokens=int(cached_eval.input_tokens or 0),
            output_tokens=int(cached_eval.output_tokens or 0),
            cost_usd=(
                float(cached_eval.cost_usd) if cached_eval.cost_usd is not None else 0.0
            ),
        ),
    )
