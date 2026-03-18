"""RAG evaluations repository"""
from __future__ import annotations

from typing import List, Optional
from datetime import datetime, UTC

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import RAGEvaluation
from app.db.repositories.base import BaseRepository


class RAGEvaluationsRepository(BaseRepository[RAGEvaluation]):
    """Repository for RAG evaluation metrics and analytics"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, RAGEvaluation)

    async def create_evaluation(
        self,
        book_id: Optional[str],
        is_global: bool,
        question: str,
        current_page: Optional[int],
        retrieved_count: int,
        context_chars: int,
        scores: Optional[List[float]],
        category_filter: List[str],
        latency_ms: int,
        answer_chars: int,
        user_id: Optional[str] = None,
    ) -> RAGEvaluation:
        """Create a new RAG evaluation record"""
        evaluation = await self.create(
            book_id=book_id,
            is_global=is_global,
            question=question,
            current_page=current_page,
            retrieved_count=retrieved_count,
            context_chars=context_chars,
            scores=scores,
            category_filter=category_filter,
            latency_ms=latency_ms,
            answer_chars=answer_chars,
            user_id=user_id,
            ts=datetime.now(UTC),
        )
        return evaluation

    async def get_recent_evaluations(
        self,
        limit: int = 100,
        book_id: Optional[str] = None
    ) -> List[RAGEvaluation]:
        """Get recent evaluations, optionally filtered by book"""
        stmt = select(RAGEvaluation).order_by(RAGEvaluation.ts.desc()).limit(limit)

        if book_id:
            stmt = stmt.where(RAGEvaluation.book_id == book_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_average_latency(
        self,
        since: Optional[datetime] = None,
        book_id: Optional[str] = None
    ) -> float:
        """Calculate average latency for RAG queries"""
        stmt = select(func.avg(RAGEvaluation.latency_ms))

        conditions = []
        if since:
            conditions.append(RAGEvaluation.ts >= since)
        if book_id:
            conditions.append(RAGEvaluation.book_id == book_id)

        if conditions:
            from sqlalchemy import and_
            stmt = stmt.where(and_(*conditions))

        result = await self.session.execute(stmt)
        avg = result.scalar_one_or_none()
        return float(avg) if avg is not None else 0.0

    async def get_stats_summary(
        self,
        since: Optional[datetime] = None
    ) -> dict:
        """
        Get summary statistics for RAG evaluations.

        Returns metrics like average latency, retrieval count, context size, etc.
        """
        stmt = select(
            func.count().label("total_queries"),
            func.avg(RAGEvaluation.latency_ms).label("avg_latency_ms"),
            func.avg(RAGEvaluation.retrieved_count).label("avg_retrieved"),
            func.avg(RAGEvaluation.context_chars).label("avg_context_chars"),
            func.avg(RAGEvaluation.answer_chars).label("avg_answer_chars"),
        )

        if since:
            stmt = stmt.where(RAGEvaluation.ts >= since)

        result = await self.session.execute(stmt)
        row = result.fetchone()

        return {
            "total_queries": row.total_queries or 0,
            "avg_latency_ms": float(row.avg_latency_ms or 0),
            "avg_retrieved": float(row.avg_retrieved or 0),
            "avg_context_chars": float(row.avg_context_chars or 0),
            "avg_answer_chars": float(row.avg_answer_chars or 0),
        }


def get_rag_evaluations_repository(session: AsyncSession) -> RAGEvaluationsRepository:
    """Factory function for dependency injection"""
    return RAGEvaluationsRepository(session)
