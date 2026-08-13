"""
OCR Job — downloads a book's PDF, OCRs each claimed page via Gemini Vision,
and marks each page succeeded or failed.

Receives: book_id, page_ids (list of Page.id already set to in_progress by scanner).
"""

from __future__ import annotations

import asyncio
import logging
from typing import List

import fitz

import time
from app.core.config import settings
from app.db import session as db_session
from app.db.models import Book, Page, PipelineEvent
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.db.repositories.pages_repository import PagesRepository
from app.services.batch_ocr_service import submit_batch_ocr_job
from app.services.ocr_service import ocr_page_with_gemini
from app.utils.text import is_toc_page
from app.services.storage_service import storage
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json, make_pipeline_event_payload
from sqlalchemy import select, update, func

logger = logging.getLogger("app.worker.ocr_job")


async def ocr_job(ctx, book_id: str, page_ids: List[int]) -> None:
    log_json(
        logger,
        logging.INFO,
        "OCR job started",
        book_id=book_id,
        page_count=len(page_ids),
    )

    from app.utils.redis_lock import MultiPageLock
    from app.utils.circuit_breaker import get_redis

    redis_client = ctx.get("redis") or get_redis()
    lock_manager = MultiPageLock(redis_client, page_ids, prefix="ocr")
    locked_page_ids = await lock_manager.__aenter__()

    try:
        if not locked_page_ids:
            log_json(
                logger,
                logging.WARNING,
                "No page locks acquired, exiting job",
                book_id=book_id,
            )
            return

        # Update worker_id and claimed_at to current executing worker
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Page)
                .where(Page.id.in_(locked_page_ids))
                .values(
                    worker_id=ctx.get("worker_id", "unknown"),
                    claimed_at=func.now(),
                    last_updated=func.now(),
                )
            )
            await session.commit()

        # Fetch OCR settings from system_configs
        async with db_session.async_session_factory() as session:
            config_repo = SystemConfigsRepository(session)
            gemini_ocr_model = await config_repo.get_value("gemini_ocr_model")
            if not gemini_ocr_model:
                raise RuntimeError("system_config 'gemini_ocr_model' is not set")
            max_parallel_pages = int(
                await config_repo.get_value("ocr_max_parallel_pages", "4")
            )
            gemini_ocr_timeout_str = await config_repo.get_value("gemini_ocr_timeout")
            gemini_ocr_timeout = (
                float(gemini_ocr_timeout_str) if gemini_ocr_timeout_str else None
            )
            ocr_max_retry_count_str = await config_repo.get_value(
                "ocr_max_retry_count", "3"
            )
            ocr_max_retry_count = int(ocr_max_retry_count_str)
            batch_ocr_enabled_str = await config_repo.get_value(
                "gemini_batch_ocr_enabled", "false"
            )
            batch_ocr_enabled = batch_ocr_enabled_str.lower() in ("true", "1", "yes")
            batch_ocr_batch_size = int(
                await config_repo.get_value("gemini_batch_ocr_batch_size", "50")
            )

        # Mark book's active step
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Book).where(Book.id == book_id).values(pipeline_step="ocr")
            )
            await session.commit()

        # Download PDF (re-download if missing or corrupted)
        # Build candidate GCS paths: standardized name first, then original file_name as fallback.
        file_path = settings.uploads_dir / f"{book_id}.pdf"
        async with db_session.async_session_factory() as session:
            book_row = (
                await session.execute(select(Book).where(Book.id == book_id))
            ).scalar_one_or_none()
        remote_paths = [f"uploads/{book_id}.pdf"]
        if book_row and book_row.file_name and book_row.file_name != f"{book_id}.pdf":
            remote_paths.append(f"uploads/{book_row.file_name}")
        if book_row and book_row.title:
            title_path = f"uploads/{book_row.title}.pdf"
            if title_path not in remote_paths:
                remote_paths.append(title_path)

        async def _download_pdf() -> None:
            last_exc: Exception | None = None
            for rp in remote_paths:
                try:
                    await storage.download_file(rp, file_path)
                    return
                except Exception as e:
                    last_exc = e
            raise last_exc  # type: ignore[misc]

        try:
            if not file_path.exists():
                await _download_pdf()
            try:
                doc = fitz.open(file_path)
            except Exception:
                await _download_pdf()
                doc = fitz.open(file_path)
        except Exception as exc:
            log_json(
                logger,
                logging.ERROR,
                "OCR job: failed to obtain PDF",
                book_id=book_id,
                error=str(exc),
            )
            # Mark all claimed pages as failed so the driver can retry them
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(Page)
                    .where(Page.id.in_(locked_page_ids))
                    .values(
                        ocr_milestone="failed",
                        retry_count=Page.retry_count + 1,
                        last_updated=func.now(),
                    )
                )
                # Create events for failure
                for pid in locked_page_ids:
                    session.add(
                        PipelineEvent(
                            page_id=pid,
                            event_type="ocr_failed",
                            payload=make_pipeline_event_payload(
                                extra_fields={"error": "Failed to obtain PDF"}
                            ),
                        )
                    )
                await session.commit()
            async with db_session.async_session_factory() as session:
                await BookMilestoneService.update_book_milestone_for_step(
                    session, book_id, "ocr"
                )
                await session.commit()
            return

        # Load page records
        async with db_session.async_session_factory() as session:
            result = await session.execute(
                select(Page).where(Page.id.in_(locked_page_ids))
            )
            pages = list(result.scalars().all())

        if batch_ocr_enabled:
            log_json(
                logger,
                logging.INFO,
                "Delegating OCR job to Gemini Batch API",
                book_id=book_id,
                page_count=len(pages),
            )
            try:
                for i in range(0, len(pages), batch_ocr_batch_size):
                    chunk = pages[i : i + batch_ocr_batch_size]
                    try:
                        async with db_session.async_session_factory() as session:
                            await submit_batch_ocr_job(
                                session, book_id, chunk, doc, gemini_ocr_model
                            )
                    except Exception as exc:
                        log_json(
                            logger,
                            logging.ERROR,
                            "Batch OCR submission failed",
                            book_id=book_id,
                            error=str(exc),
                        )
                        async with db_session.async_session_factory() as session:
                            error_msg = str(exc)[:500]
                            await session.execute(
                                update(Page)
                                .where(Page.id.in_([p.id for p in chunk]))
                                .values(
                                    ocr_milestone="failed",
                                    retry_count=Page.retry_count + 1,
                                    error=error_msg,
                                    last_updated=func.now(),
                                )
                            )
                            for p in chunk:
                                session.add(
                                    PipelineEvent(
                                        page_id=p.id,
                                        event_type="ocr_failed",
                                        payload=make_pipeline_event_payload(
                                            extra_fields={
                                                "error": error_msg,
                                                "batch": True,
                                            }
                                        ),
                                    )
                                )
                            await session.commit()
                        async with db_session.async_session_factory() as session:
                            await BookMilestoneService.update_book_milestone_for_step(
                                session, book_id, "ocr"
                            )
                            await session.commit()
            finally:
                doc.close()
            return

        sem = asyncio.Semaphore(max_parallel_pages)

        async def process_page(page: Page) -> None:
            async with sem:
                start_time = time.perf_counter()
                try:
                    fitz_page = doc.load_page(page.page_number - 1)  # fitz is 0-indexed
                    text = await ocr_page_with_gemini(
                        fitz_page, gemini_ocr_model, timeout=gemini_ocr_timeout
                    )
                    is_toc = is_toc_page(text)
                    duration_ms = int((time.perf_counter() - start_time) * 1000)

                    async with db_session.async_session_factory() as session:
                        await session.execute(
                            update(Page)
                            .where(Page.id == page.id)
                            .values(
                                text=text,
                                is_toc=is_toc,
                                ocr_milestone="succeeded",
                                last_updated=func.now(),
                            )
                        )
                        # Emit event for chunking and word index to pick up
                        session.add(
                            PipelineEvent(
                                page_id=page.id,
                                event_type="ocr_succeeded",
                                payload=make_pipeline_event_payload(
                                    duration_ms=duration_ms
                                ),
                            )
                        )
                        await session.commit()

                    log_json(
                        logger,
                        logging.INFO,
                        "OCR page succeeded",
                        book_id=book_id,
                        page=page.page_number,
                    )

                except Exception as exc:
                    duration_ms = int((time.perf_counter() - start_time) * 1000)
                    async with db_session.async_session_factory() as session:
                        error_msg = str(exc)[:500]
                        next_retry_count = page.retry_count + 1
                        if next_retry_count >= ocr_max_retry_count:
                            await session.execute(
                                update(Page)
                                .where(Page.id == page.id)
                                .values(
                                    text="",
                                    is_toc=False,
                                    ocr_milestone="succeeded",
                                    retry_count=next_retry_count,
                                    error=f"OCR failed after {ocr_max_retry_count} retries: {error_msg}. Page skipped.",
                                    last_updated=func.now(),
                                )
                            )
                            session.add(
                                PipelineEvent(
                                    page_id=page.id,
                                    event_type="ocr_succeeded",
                                    payload=make_pipeline_event_payload(
                                        duration_ms=duration_ms,
                                        extra_fields={
                                            "skipped": True,
                                            "error": error_msg,
                                        },
                                    ),
                                )
                            )
                            log_json(
                                logger,
                                logging.WARNING,
                                "OCR page failed after retry, skipping page",
                                book_id=book_id,
                                page=page.page_number,
                                error=str(exc),
                            )
                        else:
                            await session.execute(
                                update(Page)
                                .where(Page.id == page.id)
                                .values(
                                    ocr_milestone="failed",
                                    retry_count=next_retry_count,
                                    error=error_msg,
                                    last_updated=func.now(),
                                )
                            )
                            session.add(
                                PipelineEvent(
                                    page_id=page.id,
                                    event_type="ocr_failed",
                                    payload=make_pipeline_event_payload(
                                        duration_ms=duration_ms,
                                        extra_fields={"error": error_msg},
                                    ),
                                )
                            )
                            log_json(
                                logger,
                                logging.WARNING,
                                "OCR page failed",
                                book_id=book_id,
                                page=page.page_number,
                                error=str(exc),
                            )
                        await session.commit()

        try:
            await asyncio.gather(*[process_page(p) for p in pages])
        finally:
            doc.close()

        # Update book-level OCR milestone and sync content_page_offset after processing batch
        async with db_session.async_session_factory() as session:
            await BookMilestoneService.update_book_milestone_for_step(
                session, book_id, "ocr"
            )
            pages_repo = PagesRepository(session)
            await pages_repo.sync_content_page_offset(book_id)
            await session.commit()

        log_json(
            logger,
            logging.INFO,
            "OCR job completed",
            book_id=book_id,
            page_count=len(locked_page_ids),
        )
    finally:
        await lock_manager.__aexit__(None, None, None)
