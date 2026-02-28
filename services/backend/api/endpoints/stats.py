"""Statistics API endpoints"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.db.session import get_session
from app.db.models import Book, Page, Chunk
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
    current_user = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Get system-wide statistics (admin only)"""

    # Count total books
    total_books_result = await session.execute(select(func.count()).select_from(Book))
    total_books = total_books_result.scalar() or 0

    # Count books by pipeline_step (with fallback to status for legacy)
    books_by_status_result = await session.execute(
        select(
            func.coalesce(Book.pipeline_step, Book.status), 
            func.count(Book.id)
        )
        .group_by(func.coalesce(Book.pipeline_step, Book.status))
        .order_by(func.count(Book.id).desc())
    )
    # Aggregated book counts
    raw_books_by_status = {}
    for status, count in books_by_status_result.all():
        # Map legacy or technical statuses to clean ones
        status = (status or "unknown").lower()
        if status in ('ocr_processing', 'ocr_done'):
            status = 'ocr'
        elif status == 'indexing':
            status = 'embedding'
        
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
        select(func.count()).select_from(Page).where(
            and_(
                Page.pipeline_step == "embedding",
                Page.milestone == "succeeded"
            )
        )
    )
    indexed_pages = indexed_pages_result.scalar() or 0

    # Count error pages
    error_pages_result = await session.execute(
        select(func.count()).select_from(Page).where(Page.milestone == "failed")
    )
    error_pages = error_pages_result.scalar() or 0

    # Pages by pipeline state summary - filter out redundant completed states
    pages_by_status_result = await session.execute(
        select(
            func.concat(Page.pipeline_step, ':', Page.milestone), 
            func.count(Page.id)
        )
        .where(
            and_(
                Page.pipeline_step.is_not(None),
                # Filter out terminal success states to avoid clutter
                Page.milestone.notin_(['succeeded', 'failed'])
            )
        )
        .group_by(Page.pipeline_step, Page.milestone)
        .order_by(func.count(Page.id).desc())
    )
    pages_by_status = [
        PageStatusCount(status=status, count=count)
        for status, count in pages_by_status_result.all()
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
    percentage_embedded = (embedded_chunks / total_chunks * 100) if total_chunks > 0 else 0.0

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
        "chunk_stats": {
            "total": total_chunks,
            "embedded": embedded_chunks,
            "pending": pending_chunks,
            "percentage_embedded": round(percentage_embedded, 2)
        }
    }
