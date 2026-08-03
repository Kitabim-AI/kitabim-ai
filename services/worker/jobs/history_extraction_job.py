"""ARQ worker task for extracting and enriching history dictionary terms from books."""

from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy import select
from app.db import session as db_session
from app.db.models import Book, Page
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.history_extraction_service import HistoryExtractionService
from app.services.batch_history_extraction_service import (
    submit_batch_history_extraction_job,
)

from app.utils.observability import log_json

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
    log_json(
        logger,
        logging.INFO,
        "Starting history dictionary extraction task",
        book_id=book_id,
    )

    try:
        session_factory = ctx.get("db_session_factory")
        if session_factory:
            async with session_factory() as session:
                return await _run_extraction(session, book_id, min_significance)
        else:
            async with db_session.async_session_factory() as session:
                return await _run_extraction(session, book_id, min_significance)
    except Exception as exc:
        log_json(
            logger,
            logging.ERROR,
            "History dictionary extraction task failed",
            book_id=book_id,
            error=str(exc)[:500],
        )
        raise


async def _run_extraction(
    session: Any, book_id: str, min_significance: int
) -> Dict[str, Any]:
    config_repo = SystemConfigsRepository(session)
    batch_enabled = await config_repo.get_value(
        "gemini_batch_history_extraction_enabled", "false"
    )

    if batch_enabled.strip().lower() == "true":
        log_json(
            logger,
            logging.INFO,
            "Gemini Batch API enabled for history extraction, submitting batch job",
            book_id=book_id,
        )
        batch_job = await submit_batch_history_extraction_job(
            session=session, book_id=book_id, min_significance=min_significance
        )
        return {
            "status": "queued_batch",
            "bookId": book_id,
            "batchJobId": batch_job.id,
            "geminiBatchId": batch_job.gemini_batch_id,
        }

    book = await get_book_details(session, book_id)
    book_title = book.get("title", "Unknown Book") if book else "Unknown Book"
    volume = book.get("volume") if book else None

    pages_data = await get_book_pages(session, book_id)
    if not pages_data:
        log_json(
            logger,
            logging.WARNING,
            "No pages found for book during history extraction",
            book_id=book_id,
        )
        return {"status": "warning", "message": "No pages found", "stagedCount": 0}

    service = HistoryExtractionService(session)
    staged_items = await service.process_book_pages(
        book_id=book_id,
        book_title=book_title,
        volume=volume,
        pages_data=pages_data,
        min_significance=min_significance,
    )

    log_json(
        logger,
        logging.INFO,
        "History extraction task completed",
        book_id=book_id,
        staged_count=len(staged_items),
    )
    return {
        "status": "success",
        "bookId": book_id,
        "stagedCount": len(staged_items),
        "stagedItems": staged_items,
    }
