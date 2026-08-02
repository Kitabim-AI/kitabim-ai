"""ARQ worker task for extracting and enriching history dictionary terms from books."""

from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy import select
from app.db import session as db_session
from app.db.models import Book, Page
from app.services.history_extraction_service import HistoryExtractionService

logger = logging.getLogger("app.worker.history_extraction_job")


async def get_book_details(session: Any, book_id: str) -> Dict[str, Any] | None:
    stmt = select(Book).where(Book.id == book_id)
    res = await session.execute(stmt)
    book = res.scalar_one_or_none()
    if not book:
        return None
    return {"title": book.title, "volume": book.volume}


async def get_book_pages(session: Any, book_id: str) -> list[Dict[str, Any]]:
    stmt = select(Page).where(Page.book_id == book_id).order_by(Page.page_number.asc())
    res = await session.execute(stmt)
    pages = res.scalars().all()
    return [
        {"page_number": p.page_number, "content": p.cleaned_text or p.text or ""}
        for p in pages
    ]


async def extract_book_history_terms_task(
    ctx: Dict[str, Any], book_id: str, min_significance: int = 5
) -> Dict[str, Any]:
    """ARQ background job function to run history extraction on a target book."""
    logger.info(f"Starting history dictionary extraction task for book_id: {book_id}")

    session_factory = ctx.get("db_session_factory")
    if session_factory:
        async with session_factory() as session:
            return await _run_extraction(session, book_id, min_significance)
    else:
        async with db_session.async_session_maker() as session:
            return await _run_extraction(session, book_id, min_significance)


async def _run_extraction(
    session: Any, book_id: str, min_significance: int
) -> Dict[str, Any]:
    book = await get_book_details(session, book_id)
    book_title = book.get("title", "Unknown Book") if book else "Unknown Book"
    volume = book.get("volume") if book else None

    pages_data = await get_book_pages(session, book_id)
    if not pages_data:
        logger.warning(f"No pages found for book_id: {book_id}")
        return {"status": "warning", "message": "No pages found", "stagedCount": 0}

    service = HistoryExtractionService(session)
    staged_items = await service.process_book_pages(
        book_id=book_id,
        book_title=book_title,
        volume=volume,
        pages_data=pages_data,
        min_significance=min_significance,
    )

    logger.info(
        f"Extraction task completed for book_id {book_id}: {len(staged_items)} terms staged."
    )
    return {
        "status": "success",
        "bookId": book_id,
        "stagedCount": len(staged_items),
        "stagedItems": staged_items,
    }
