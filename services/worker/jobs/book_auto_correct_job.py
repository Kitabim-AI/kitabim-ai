"""
Book Auto-Correction Job — runs per-book high-precision OCR auto-healing
and active AutoCorrectRule replacements when triggered manually by an admin.
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import func, update

from app.core.pipeline import BOOK_MILESTONE_FAILED
from app.db import session as db_session
from app.db.models import Book
from app.services.cache_service import cache_service
from app.services.ocr_auto_heal_service import auto_heal_book_pages
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.book_auto_correct_job")


async def book_auto_correct_job(
    ctx, book_id: str, updated_by: Optional[str] = None
) -> None:
    """Execute per-book OCR auto-correction in the background worker."""
    start_time = time.perf_counter()
    log_json(
        logger,
        logging.INFO,
        "book auto-correction job started",
        book_id=book_id,
        updated_by=updated_by,
    )

    from app.utils.circuit_breaker import get_redis

    redis_client = ctx.get("redis") or get_redis()
    lock_key = f"lock:book_auto_correct:{book_id}"
    acquired = False
    if redis_client is not None:
        acquired = bool(await redis_client.set(lock_key, "1", nx=True, ex=600))
        if not acquired:
            log_json(
                logger,
                logging.WARNING,
                "book auto-correction lock already held, skipping duplicate run",
                book_id=book_id,
            )
            return

    try:
        async with db_session.async_session_factory() as session:
            result = await auto_heal_book_pages(session, book_id, updated_by=updated_by)

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        log_json(
            logger,
            logging.INFO,
            "book auto-correction job completed",
            book_id=book_id,
            pages_scanned=result.pages_scanned,
            pages_modified=result.pages_modified,
            rule_replacements=result.rule_replacements,
            ocr_heals=result.ocr_heals,
            total_replacements=result.total_replacements,
            issues_marked_corrected=result.issues_marked_corrected,
            false_positives_cleared=result.false_positives_cleared,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - start_time) * 1000)
        try:
            async with db_session.async_session_factory() as err_session:
                await err_session.execute(
                    update(Book)
                    .where(Book.id == book_id)
                    .values(
                        auto_correct_milestone=BOOK_MILESTONE_FAILED,
                        last_updated=func.now(),
                    )
                )
                await err_session.commit()
            await cache_service.delete(f"book:{book_id}")
            await cache_service.bump_namespace_version("books:list")
        except Exception:
            pass
        log_json(
            logger,
            logging.ERROR,
            "book auto-correction job failed",
            book_id=book_id,
            error=repr(exc)[:500],
            duration_ms=duration_ms,
        )
        raise
    finally:
        if acquired and redis_client is not None:
            try:
                await redis_client.delete(lock_key)
            except Exception:
                pass
