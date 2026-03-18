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

from app.core.config import settings
from app.db import session as db_session
from app.db.models import Book, Page, PipelineEvent
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.ocr_service import ocr_page_with_gemini
from app.services.storage_service import storage
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json
from sqlalchemy import select, update, func

logger = logging.getLogger("app.worker.ocr_job")


async def ocr_job(ctx, book_id: str, page_ids: List[int]) -> None:
    log_json(logger, logging.INFO, "OCR job started",
             book_id=book_id, page_count=len(page_ids))

    # Fetch OCR model from system_configs (no fallback — must be configured in DB)
    async with db_session.async_session_factory() as session:
        config_repo = SystemConfigsRepository(session)
        gemini_ocr_model = await config_repo.get_value("gemini_ocr_model")
        if not gemini_ocr_model:
            raise RuntimeError("system_config 'gemini_ocr_model' is not set")

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
        book_row = (await session.execute(select(Book).where(Book.id == book_id))).scalar_one_or_none()
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
        log_json(logger, logging.ERROR, "OCR job: failed to obtain PDF",
                 book_id=book_id, error=str(exc))
        # Mark all claimed pages as failed so the driver can retry them
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Page)
                .where(Page.id.in_(page_ids))
                .values(
                    ocr_milestone="failed",
                    retry_count=Page.retry_count + 1,
                    last_updated=func.now(),
                )
            )
            # Create events for failure
            for pid in page_ids:
                session.add(PipelineEvent(
                    page_id=pid,
                    event_type="ocr_failed",
                    payload='{"error": "Failed to obtain PDF"}'
                ))
            await session.commit()
        return

    # Load page records
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(Page).where(Page.id.in_(page_ids)))
        pages = list(result.scalars().all())

    sem = asyncio.Semaphore(settings.max_parallel_pages)

    async def process_page(page: Page) -> None:
        async with sem:
            try:
                fitz_page = doc.load_page(page.page_number - 1)  # fitz is 0-indexed
                text = await ocr_page_with_gemini(fitz_page, gemini_ocr_model)

                async with db_session.async_session_factory() as session:
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(
                            text=text,
                            ocr_milestone="succeeded",
                            last_updated=func.now(),
                        )
                    )
                    # Emit event for chunking and word index to pick up
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="ocr_succeeded"
                    ))
                    await session.commit()

                log_json(logger, logging.DEBUG, "OCR page succeeded",
                         book_id=book_id, page=page.page_number)

            except Exception as exc:
                async with db_session.async_session_factory() as session:
                    error_msg = str(exc)[:500]
                    await session.execute(
                        update(Page)
                        .where(Page.id == page.id)
                        .values(
                            ocr_milestone="failed",
                            retry_count=Page.retry_count + 1,
                            error=error_msg,
                            last_updated=func.now(),
                        )
                    )
                    session.add(PipelineEvent(
                        page_id=page.id,
                        event_type="ocr_failed",
                        payload=f'{{"error": "{error_msg}"}}'
                    ))
                    await session.commit()

                log_json(logger, logging.WARNING, "OCR page failed",
                         book_id=book_id, page=page.page_number, error=str(exc))

    try:
        await asyncio.gather(*[process_page(p) for p in pages])
    finally:
        doc.close()

    # Update book-level OCR milestone after processing batch
    async with db_session.async_session_factory() as session:
        await BookMilestoneService.update_book_milestone_for_step(session, book_id, 'ocr')
        await session.commit()

    log_json(logger, logging.INFO, "OCR job completed",
             book_id=book_id, page_count=len(page_ids))
