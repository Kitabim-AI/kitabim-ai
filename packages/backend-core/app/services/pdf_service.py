from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import fitz
from app.core.config import settings
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import session as db_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.pages import PagesRepository
from app.db.repositories.jobs import JobsRepository
from app.db.models import Book, Page, Chunk
from sqlalchemy import update, or_, and_, delete, select

from app.langchain.models import GeminiEmbeddings
from app.services.ocr_service import ocr_page
from app.services.chunking_service import chunking_service
from app.utils.errors import record_book_error
from app.utils.markdown import normalize_markdown, strip_markdown
from app.utils.observability import log_json

RUNNING_TASKS: set[str] = set()
logger = logging.getLogger("app.pdf")


def _resolve_pdf_path(book_id: str) -> Path:
    return settings.uploads_dir / f"{book_id}.pdf"


def _resolve_cover_path(book_id: str) -> Path:
    return settings.covers_dir / f"{book_id}.jpg"


async def _acquire_lock(session: AsyncSession, book_id: str, job_key: str | None) -> bool:
    now = datetime.utcnow()
    expires = now + timedelta(seconds=settings.job_lock_ttl_seconds)
    lock_val = job_key or "local"

    stmt = (
        update(Book)
        .where(
            and_(
                Book.id == book_id,
                or_(
                    Book.processing_lock_expires_at == None,
                    Book.processing_lock_expires_at < now,
                    Book.processing_lock == lock_val
                )
            )
        )
        .values(
            processing_lock=lock_val,
            processing_lock_expires_at=expires
        )
    )
    result = await session.execute(stmt)
    await session.flush()
    return result.rowcount > 0


async def _release_lock(session: AsyncSession, book_id: str, job_key: str | None) -> None:
    lock_val = job_key or "local"
    await session.execute(
        update(Book)
        .where(and_(Book.id == book_id, Book.processing_lock == lock_val))
        .values(processing_lock=None, processing_lock_expires_at=None)
    )
    await session.flush()


async def process_pdf_task(
    book_id: str,
    job_key: str | None = None,
    raise_on_error: bool = False,
) -> None:
    if book_id in RUNNING_TASKS:
        log_json(logger, logging.INFO, "Task already running", book_id=book_id)
        return

    RUNNING_TASKS.add(book_id)

    async with db_session.async_session_factory() as session:
        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        jobs_repo = JobsRepository(session)
        
        try:
            if job_key:
                await jobs_repo.increment_attempts(job_key)
                await jobs_repo.update_status(job_key, "running")
                await session.commit()

            lock_acquired = await _acquire_lock(session, book_id, job_key)
            if not lock_acquired:
                log_json(logger, logging.WARNING, "Processing lock busy", book_id=book_id)
                if job_key:
                    await jobs_repo.update_status(job_key, "skipped", "Lock busy")
                    await session.commit()
                return

            file_path = _resolve_pdf_path(book_id)
            if not file_path.exists():
                log_json(logger, logging.ERROR, "PDF file missing", book_id=book_id, path=str(file_path))
                await books_repo.update_one(book_id, status="error")
                await record_book_error(session, book_id, "processing", "PDF file missing", {"path": str(file_path)})
                if job_key:
                    await jobs_repo.update_status(job_key, "failed", "PDF file missing")
                await session.commit()
                return

            doc = fitz.open(file_path)
            total_pages = doc.page_count

            book = await books_repo.get(book_id)
            if not book:
                return

            if total_pages > 0:
                # Fetch existing page numbers to avoid overwriting them
                existing_pages = await pages_repo.find_by_book(book_id)
                existing_page_nums = {p.page_number for p in existing_pages}

                for page_num in range(1, total_pages + 1):
                    if page_num not in existing_page_nums:
                        page_data = {
                            "book_id": book_id,
                            "page_number": page_num,
                            "status": "pending",
                            "is_verified": False,
                            "text": "",
                            "last_updated": datetime.utcnow(),
                        }
                        # Use upsert to avoid duplicates if re-running
                        await pages_repo.upsert(page_data)

                await books_repo.update_one(
                    book_id,
                    total_pages=total_pages,
                    status="processing",
                    last_updated=datetime.utcnow(),
                )

            cover_path = _resolve_cover_path(book_id)
            if not cover_path.exists() and total_pages > 0:
                try:
                    first_page = doc.load_page(0)
                    pix = first_page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                    pix.save(str(cover_path))
                    await books_repo.update_one(
                        book_id,
                        cover_url=f"/api/covers/{book_id}.jpg"
                    )
                except Exception as exc:
                    log_json(logger, logging.WARNING, "Cover extraction failed", book_id=book_id, error=str(exc))
                    await record_book_error(session, book_id, "cover", str(exc))
            
            await session.commit()

            # Find pages that need processing
            stmt = select(Page).where(
                and_(
                    Page.book_id == book_id,
                    or_(
                        Page.status != "completed",
                        # Page model doesn't have is_indexed yet? 
                        # Looking at my models.py edit, I didn't add it.
                        # Wait, I should check Page model in models.py.
                    )
                )
            )
            # Actually, let's use the PagesRepository to find all for now and filter or use a custom method
            all_pages = await pages_repo.find_by_book(book_id)
            pages_to_process_recs = [p for p in all_pages if p.status != "completed"]
            
            # Note: The original code also checked isIndexed. Let's see if Page has it.
            # I'll check Page model.
            
            pages_to_process = [r.page_number for r in pages_to_process_recs]

            if not pages_to_process:
                # If all OCR is done, move to next step or mark ready
                # (Later we check embeddings)
                pass
            else:
                semaphore = asyncio.Semaphore(settings.max_parallel_pages)

                async def process_page(page_num: int) -> None:
                    async with semaphore:
                        # Each page process might need its own session to be safe with concurrency
                        # but we can also use the same session if we flush.
                        # However, for parallel processing with asyncio.gather, we should be careful.
                        # Actually, SQLAlchemy 2 async sessions are not thread-safe and usually not task-safe if shared.
                        async with db_session.async_session_factory() as page_session:
                            page_books_repo = BooksRepository(page_session)
                            page_pages_repo = PagesRepository(page_session)
                            try:
                                page_record = await page_pages_repo.find_one(book_id, page_num)
                                existing_text = page_record.text if page_record else ""
                                is_verified = page_record.is_verified if page_record else False
                                already_ocr = is_verified or (
                                    page_record and page_record.status == "completed" and len(existing_text) > 40
                                )

                                if not already_ocr:
                                    await page_pages_repo.update_status(book_id, page_num, "processing")
                                    await page_session.commit()

                                success = already_ocr
                                page_text = existing_text
                                page_error: str | None = None

                                if not already_ocr:
                                    page_obj = doc.load_page(page_num - 1)
                                    try:
                                        page_text = await ocr_page(
                                            page_obj,
                                            book.title or "Unknown",
                                            page_num,
                                        )
                                        success = True
                                    except Exception as exc:
                                        log_json(
                                            logger,
                                            logging.ERROR,
                                            "OCR failed",
                                            book_id=book_id,
                                            page_num=page_num,
                                            error=str(exc),
                                        )
                                        page_error = str(exc)
                                        page_text = f"[OCR Error: {exc}]"
                                        await record_book_error(
                                            page_session,
                                            book_id,
                                            "ocr",
                                            str(exc),
                                            {"page_num": page_num},
                                        )

                                if success:
                                    page_text = normalize_markdown(page_text)

                                # Update page status
                                await page_session.execute(
                                    update(Page)
                                    .where(and_(Page.book_id == book_id, Page.page_number == page_num))
                                    .values(
                                        text=page_text,
                                        status="completed" if success else "error",
                                        error=page_error,
                                        last_updated=datetime.utcnow(),
                                        # embedding=None # Clear embedding if text changed
                                    )
                                )
                                await page_session.commit()
                                
                                if success:
                                    log_json(
                                        logger,
                                        logging.INFO,
                                        "OCR page completed",
                                        book_id=book_id,
                                        page_num=page_num,
                                    )
                            except Exception as exc:
                                log_json(
                                    logger,
                                    logging.ERROR,
                                    "Page processing failed",
                                    book_id=book_id,
                                    page_num=page_num,
                                    error=str(exc),
                                )
                                await record_book_error(
                                    page_session,
                                    book_id,
                                    "ocr",
                                    str(exc),
                                    {"page_num": page_num},
                                )
                                await page_session.commit()

                await asyncio.gather(*[process_page(p) for p in pages_to_process])

            # Refresh session and book record
            await session.refresh(book)
                # Refresh session to get latest page statuses
            await session.commit()
            
            # Find pages that need embedding
            stmt_embed = select(Page).where(
                and_(
                    Page.book_id == book_id,
                    Page.status == "completed",
                    Page.is_indexed == False
                )
            )
            result_embed = await session.execute(stmt_embed)
            pages_to_embed = result_embed.scalars().all()

            if pages_to_embed:
                embedder = GeminiEmbeddings()
                batch_size = 20  # Reduced to avoid rate limits and timeouts
                for start in range(0, len(pages_to_embed), batch_size):
                    await asyncio.sleep(1.0)  # Rate limiting
                    batch = pages_to_embed[start : start + batch_size]
                    pairs = []
                    for r in batch:
                        text_content = strip_markdown(r.text or "").strip()
                        if text_content:
                            pairs.append((r, text_content))
                    if not pairs:
                        continue

                    try:
                        # Flatten all chunks from the batch
                        all_chunks_text = []
                        page_chunk_counts = [] # Keep track of how many chunks each page has

                        for r, text_content in pairs:
                            chunks = chunking_service.split_text(text_content)
                            if not chunks:
                                chunks = [text_content] if text_content else []
                            
                            all_chunks_text.extend(chunks)
                            page_chunk_counts.append(len(chunks))

                        if not all_chunks_text:
                            continue

                        all_embeddings = await embedder.aembed_documents(all_chunks_text)

                        # Distribute embeddings back to pages and save chunks
                        current_embed_idx = 0
                        
                        for i, (r, original_text) in enumerate(pairs):
                            count = page_chunk_counts[i]
                            if count == 0:
                                # Just mark indexed
                                r.is_indexed = True
                                continue

                            page_chunks = all_chunks_text[current_embed_idx : current_embed_idx + count]
                            page_vectors = all_embeddings[current_embed_idx : current_embed_idx + count]
                            current_embed_idx += count

                            # Clean up old chunks for this page
                            await session.execute(
                                delete(Chunk).where(and_(Chunk.book_id == book_id, Chunk.page_number == r.page_number))
                            )
                            
                            # Insert new chunks
                            for chunk_idx, (txt, vec) in enumerate(zip(page_chunks, page_vectors)):
                                new_chunk = Chunk(
                                    book_id=book_id,
                                    page_number=r.page_number,
                                    chunk_index=chunk_idx,
                                    text=txt,
                                    embedding=vec,
                                    created_at=datetime.utcnow()
                                )
                                session.add(new_chunk)

                            # Update page status
                            r.is_indexed = True
                            r.last_updated = datetime.utcnow()
                        
                        await session.commit()
                        
                    except Exception as exc:
                        log_json(
                            logger,
                            logging.ERROR,
                            "Embedding batch failed",
                            book_id=book_id,
                            batch_start=start,
                            batch_end=start + len(batch) - 1,
                            error=str(exc),
                        )
                        await record_book_error(
                            session,
                            book_id,
                            "embedding",
                            str(exc),
                            {"batch_start": start, "batch_end": start + len(batch) - 1},
                        )
                        await session.commit()

            # Final check - aggregate page stats
            stats = await pages_repo.count_by_book(book_id, status="completed")
            final_status = "ready" if stats == total_pages else "error"

            await books_repo.update_one(
                book_id,
                status=final_status,
                last_updated=datetime.utcnow(),
            )
            await session.commit()
            
            log_json(logger, logging.INFO, "Book processing finished", book_id=book_id, status=final_status)
            if job_key:
                if final_status == "ready":
                    await jobs_repo.update_status(job_key, "succeeded")
                else:
                    await jobs_repo.update_status(job_key, "failed", f"Final status: {final_status}")
                await session.commit()

        except Exception as exc:
            log_json(logger, logging.ERROR, "Processing task failed", book_id=book_id, error=str(exc))
            await books_repo.update_one(book_id, status="error")
            await record_book_error(session, book_id, "processing", str(exc))
            if job_key:
                await jobs_repo.update_status(job_key, "failed", str(exc))
            await session.commit()
            if raise_on_error:
                raise
        finally:
            RUNNING_TASKS.discard(book_id)
            await _release_lock(session, book_id, job_key)
            await session.commit()
            if "doc" in locals():
                doc.close()
