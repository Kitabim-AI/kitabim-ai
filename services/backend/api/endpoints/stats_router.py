"""Statistics API endpoints"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, case, cast, Integer, desc

from app.core.pipeline import (
    PIPELINE_STEP_EMBEDDING,
    PIPELINE_STEP_OCR,
)
from app.db.session import get_session
from app.db.models import Book, Page, Chunk, PipelineEvent
from auth.dependencies import require_admin

router = APIRouter()


class BookStatusCount(BaseModel):
    status: str
    count: int


class PageStatusCount(BaseModel):
    status: str
    count: int


class PageStats(BaseModel):
    total: int
    indexed: int
    unindexed: int
    percentage_indexed: float
    error: int = 0
    pages_by_status: list[PageStatusCount] = []


class ChunkStats(BaseModel):
    total: int
    embedded: int
    pending: int
    percentage_embedded: float


class SystemStats(BaseModel):
    total_books: int
    books_by_status: list[BookStatusCount]
    page_stats: PageStats
    chunk_stats: ChunkStats


@router.get("/", response_model=SystemStats)
async def get_system_stats(
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get system-wide statistics (admin only)"""

    # Count total books
    total_books_result = await session.execute(select(func.count()).select_from(Book))
    total_books = total_books_result.scalar() or 0

    # Count books by pipeline_step (with fallback to status for legacy)
    books_by_status_result = await session.execute(
        select(func.coalesce(Book.pipeline_step, Book.status), func.count(Book.id))
        .group_by(func.coalesce(Book.pipeline_step, Book.status))
        .order_by(func.count(Book.id).desc())
    )
    # Aggregated book counts
    raw_books_by_status = {}
    for status, count in books_by_status_result.all():
        # Map legacy or technical statuses to clean ones
        status = (status or "unknown").lower()
        if status in ("ocr_processing", "ocr_done"):
            status = PIPELINE_STEP_OCR
        elif status == "indexing":
            status = PIPELINE_STEP_EMBEDDING

        raw_books_by_status[status] = raw_books_by_status.get(status, 0) + count

    books_by_status = [
        BookStatusCount(status=status, count=count)
        for status, count in raw_books_by_status.items()
    ]

    # Count total pages
    total_pages_result = await session.execute(select(func.count()).select_from(Page))
    total_pages = total_pages_result.scalar() or 0

    # Count indexed pages (terminal state)
    indexed_pages_result = await session.execute(
        select(func.count()).select_from(Page).where(Page.is_indexed.is_(True))
    )
    indexed_pages = indexed_pages_result.scalar() or 0

    # Count error pages
    error_pages_result = await session.execute(
        select(func.count())
        .select_from(Page)
        .where(
            or_(
                Page.ocr_milestone.in_(["failed", "error"]),
                Page.chunking_milestone.in_(["failed", "error"]),
                Page.embedding_milestone.in_(["failed", "error"]),
                Page.spell_check_milestone.in_(["failed", "error"]),
            )
        )
    )
    error_pages = error_pages_result.scalar() or 0

    # Pages by pipeline state summary - derived from decoupled milestones
    current_status_expr = case(
        (Page.ocr_milestone != "succeeded", func.concat("ocr:", Page.ocr_milestone)),
        (
            Page.chunking_milestone != "succeeded",
            func.concat("chunking:", Page.chunking_milestone),
        ),
        (
            Page.embedding_milestone != "succeeded",
            func.concat("embedding:", Page.embedding_milestone),
        ),
        (
            Page.spell_check_milestone.notin_(["idle", "succeeded"]),
            func.concat("spell_check:", Page.spell_check_milestone),
        ),
        else_="indexed",
    )

    pages_by_status_result = await session.execute(
        select(current_status_expr, func.count(Page.id))
        .where(Page.is_indexed.is_(False))
        .group_by(current_status_expr)
        .order_by(func.count(Page.id).desc())
    )

    pages_by_status = [
        PageStatusCount(status=status, count=count)
        for status, count in pages_by_status_result.all()
        if status != "indexed"
    ]

    unindexed_pages = total_pages - indexed_pages
    percentage_indexed = (indexed_pages / total_pages * 100) if total_pages > 0 else 0.0

    # Chunk stats
    total_chunks_result = await session.execute(select(func.count()).select_from(Chunk))
    total_chunks = total_chunks_result.scalar() or 0

    embedded_chunks_result = await session.execute(
        select(func.count()).select_from(Chunk).where(Chunk.embedding.is_not(None))
    )
    embedded_chunks = embedded_chunks_result.scalar() or 0
    pending_chunks = total_chunks - embedded_chunks
    percentage_embedded = (
        (embedded_chunks / total_chunks * 100) if total_chunks > 0 else 0.0
    )

    return {
        "total_books": total_books,
        "books_by_status": books_by_status,
        "page_stats": {
            "total": total_pages,
            "indexed": indexed_pages,
            "unindexed": unindexed_pages,
            "percentage_indexed": round(percentage_indexed, 2),
            "error": error_pages,
            "pages_by_status": pages_by_status,
        },
        "chunk_stats": {
            "total": total_chunks,
            "embedded": embedded_chunks,
            "pending": pending_chunks,
            "percentage_embedded": round(percentage_embedded, 2),
        },
    }


class RAGQualityStats(BaseModel):
    total_evaluations: int
    graded_evaluations: int
    thumbs_up_count: int
    thumbs_down_count: int
    avg_faithfulness: float | None = None
    avg_answer_relevance: float | None = None
    avg_context_precision: float | None = None


@router.get("/rag", response_model=RAGQualityStats)
async def get_rag_quality_stats(
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get RAG user feedback and quality statistics (admin only)."""
    from sqlalchemy import case
    from app.db.models import RAGEvaluation

    is_positive = RAGEvaluation.user_feedback == "positive"
    is_negative = RAGEvaluation.user_feedback == "negative"

    result = await session.execute(
        select(
            func.count().label("total"),
            func.count(case((is_positive, 1))).label("thumbs_up"),
            func.count(case((is_negative, 1))).label("thumbs_down"),
            func.avg(RAGEvaluation.faithfulness_score).label("avg_faithfulness"),
            func.avg(RAGEvaluation.answer_relevance_score).label(
                "avg_answer_relevance"
            ),
            func.avg(RAGEvaluation.context_precision_score).label(
                "avg_context_precision"
            ),
        ).select_from(RAGEvaluation)
    )
    row = result.fetchone()

    total = row.total if row else 0
    thumbs_up = row.thumbs_up if row else 0
    thumbs_down = row.thumbs_down if row else 0
    graded = thumbs_up + thumbs_down

    return {
        "total_evaluations": total,
        "graded_evaluations": graded,
        "thumbs_up_count": thumbs_up,
        "thumbs_down_count": thumbs_down,
        "avg_faithfulness": float(row.avg_faithfulness)
        if row and row.avg_faithfulness is not None
        else None,
        "avg_answer_relevance": float(row.avg_answer_relevance)
        if row and row.avg_answer_relevance is not None
        else None,
        "avg_context_precision": float(row.avg_context_precision)
        if row and row.avg_context_precision is not None
        else None,
    }


class PipelineStageStats(BaseModel):
    stage: str
    avg_duration_ms: float
    p95_duration_ms: float | None
    max_duration_ms: int | None
    total_events: int


class PipelinePerformanceStats(BaseModel):
    stages: list[PipelineStageStats]


@router.get("/pipeline", response_model=PipelinePerformanceStats)
async def get_pipeline_performance_stats(
    current_user=Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get pipeline stage performance metrics from PipelineEvent duration_ms (admin only).

    Aggregates avg / p95 / max processing duration per event_type
    using the JSON payload stored in each PipelineEvent row.
    """
    duration_expr = cast(PipelineEvent.payload["duration_ms"].as_integer(), Integer)

    stmt = (
        select(
            PipelineEvent.event_type,
            func.avg(duration_expr).label("avg_duration"),
            func.percentile_cont(0.95)
            .within_group(duration_expr)
            .label("p95_duration"),
            func.max(duration_expr).label("max_duration"),
            func.count().label("count"),
        )
        .where(PipelineEvent.payload["duration_ms"].is_not(None))
        .group_by(PipelineEvent.event_type)
        .order_by(desc("count"))
    )

    result = await session.execute(stmt)
    rows = result.all()

    return {
        "stages": [
            PipelineStageStats(
                stage=row.event_type,
                avg_duration_ms=round(float(row.avg_duration or 0), 1),
                p95_duration_ms=round(float(row.p95_duration), 1)
                if row.p95_duration is not None
                else None,
                max_duration_ms=int(row.max_duration)
                if row.max_duration is not None
                else None,
                total_events=row.count,
            )
            for row in rows
        ]
    }
