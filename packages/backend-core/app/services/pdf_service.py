from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
import fitz
from pymongo import ReturnDocument

from app.core.config import settings
from app.db.mongodb import db_manager
from app.jobs import increment_attempts, update_job_status
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


async def _acquire_lock(db, book_id: str, job_key: str | None) -> bool:
    now = datetime.utcnow()
    expires = now + timedelta(seconds=settings.job_lock_ttl_seconds)
    result = await db.books.find_one_and_update(
        {
            "id": book_id,
            "$or": [
                {"processingLockExpiresAt": {"$exists": False}},
                {"processingLockExpiresAt": {"$lt": now}},
            ],
        },
        {
            "$set": {
                "processingLock": job_key or "local",
                "processingLockExpiresAt": expires,
            }
        },
        return_document=ReturnDocument.AFTER,
    )
    return result is not None and result.get("processingLock") in {job_key, "local"}


async def _release_lock(db, book_id: str, job_key: str | None) -> None:
    await db.books.update_one(
        {"id": book_id, "processingLock": job_key or "local"},
        {"$unset": {"processingLock": "", "processingLockExpiresAt": ""}},
    )


async def process_pdf_task(
    book_id: str,
    job_key: str | None = None,
    raise_on_error: bool = False,
) -> None:
    if book_id in RUNNING_TASKS:
        log_json(logger, logging.INFO, "Task already running", book_id=book_id)
        return

    RUNNING_TASKS.add(book_id)
    db = db_manager.db

    try:
        if job_key:
            await increment_attempts(db, job_key)
            await update_job_status(db, job_key, "running")

        lock_acquired = await _acquire_lock(db, book_id, job_key)
        if not lock_acquired:
            log_json(logger, logging.WARNING, "Processing lock busy", book_id=book_id)
            if job_key:
                await update_job_status(db, job_key, "skipped", "Lock busy")
            return

        file_path = _resolve_pdf_path(book_id)
        if not file_path.exists():
            log_json(logger, logging.ERROR, "PDF file missing", book_id=book_id, path=str(file_path))
            await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
            await record_book_error(db, book_id, "processing", "PDF file missing", {"path": str(file_path)})
            if job_key:
                await update_job_status(db, job_key, "failed", "PDF file missing")
            return

        doc = fitz.open(file_path)
        total_pages = doc.page_count

        book = await db.books.find_one({"id": book_id})
        if not book:
            return

        if total_pages > 0:
            objs = []
            for page_num in range(1, total_pages + 1):
                objs.append(
                    {
                        "bookId": book_id,
                        "pageNumber": page_num,
                        "status": "pending",
                        "isVerified": False,
                        "text": "",
                        "lastUpdated": datetime.utcnow(),
                    }
                )
            # Use upsert to avoid duplicates if re-running
            for obj in objs:
                await db.pages.update_one(
                    {"bookId": book_id, "pageNumber": obj["pageNumber"]},
                    {"$setOnInsert": obj},
                    upsert=True
                )

            await db.books.update_one(
                {"id": book_id},
                {
                    "$set": {
                        "totalPages": total_pages,
                        "status": "processing",
                        "lastUpdated": datetime.utcnow(),
                    }
                },
            )

        cover_path = _resolve_cover_path(book_id)
        if not cover_path.exists() and total_pages > 0:
            try:
                first_page = doc.load_page(0)
                pix = first_page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5))
                pix.save(str(cover_path))
                await db.books.update_one(
                    {"id": book_id},
                    {"$set": {"coverUrl": f"/api/covers/{book_id}.jpg"}},
                )
            except Exception as exc:
                log_json(logger, logging.WARNING, "Cover extraction failed", book_id=book_id, error=str(exc))
                await record_book_error(db, book_id, "cover", str(exc))

        # Find pages that need processing
        pages_to_process_recs = await db.pages.find(
            {
                "bookId": book_id,
                "$or": [
                    {"status": {"$ne": "completed"}},
                    {"isIndexed": {"$ne": True}}
                ]
            }
        ).to_list(None)
        
        pages_to_process = [r["pageNumber"] for r in pages_to_process_recs]

        if not pages_to_process:
            await db.books.update_one({"id": book_id}, {"$set": {"status": "ready"}})
            return

        semaphore = asyncio.Semaphore(settings.max_parallel_pages)

        async def process_page(page_num: int) -> None:
            async with semaphore:
                try:
                    page_record = await db.pages.find_one({"bookId": book_id, "pageNumber": page_num})
                    existing_text = page_record.get("text", "") if page_record else ""
                    is_verified = page_record.get("isVerified", False) if page_record else False
                    already_ocr = is_verified or (
                        page_record and page_record.get("status") == "completed" and len(existing_text) > 40
                    )

                    if not already_ocr:
                        await db.pages.update_one(
                            {"bookId": book_id, "pageNumber": page_num},
                            {"$set": {"status": "processing"}},
                        )

                    success = already_ocr
                    page_text = existing_text
                    page_error: str | None = None

                    if not already_ocr:
                        page = doc.load_page(page_num - 1)
                        try:
                            page_text = await ocr_page(
                                page,
                                book.get("title", "Unknown"),
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
                                db,
                                book_id,
                                "ocr",
                                str(exc),
                                {"page_num": page_num},
                            )

                    if success:
                        page_text = normalize_markdown(page_text)

                    update_fields = {
                        "text": page_text,
                        "status": "completed" if success else "error",
                        "error": page_error,
                        "lastUpdated": datetime.utcnow(),
                        "isIndexed": False
                    }
                    await db.pages.update_one(
                        {"bookId": book_id, "pageNumber": page_num},
                        {"$set": update_fields},
                    )
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
                        db,
                        book_id,
                        "ocr",
                        str(exc),
                        {"page_num": page_num},
                    )

        await asyncio.gather(*[process_page(p) for p in pages_to_process])

        await db.books.update_one({"id": book_id}, {"$set": {"processingStep": "rag"}})

        pages_to_embed = await db.pages.find(
            {"bookId": book_id, "status": "completed", "isIndexed": {"$ne": True}}
        ).to_list(None)

        if pages_to_embed:
            embedder = GeminiEmbeddings()
            batch_size = 100
            for start in range(0, len(pages_to_embed), batch_size):
                batch = pages_to_embed[start : start + batch_size]
                pairs = []
                for r in batch:
                    text = strip_markdown(r.get("text") or "").strip()
                    if text:
                        pairs.append((r, text))
                if not pairs:
                    continue

                try:
                    # Flatten all chunks from the batch
                    all_chunks_text = []
                    page_chunk_counts = [] # Keep track of how many chunks each page has

                    for r, text in pairs:
                        chunks = chunking_service.split_text(text)
                        if not chunks:
                            chunks = [text] if text else []
                        
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
                            # Just mark indexed?
                            await db.pages.update_one(
                                {"bookId": book_id, "pageNumber": r.get("pageNumber")},
                                {"$set": {"isIndexed": True}}
                            )
                            continue

                        page_chunks = all_chunks_text[current_embed_idx : current_embed_idx + count]
                        page_vectors = all_embeddings[current_embed_idx : current_embed_idx + count]
                        current_embed_idx += count

                        chunk_docs = []
                        for chunk_idx, (txt, vec) in enumerate(zip(page_chunks, page_vectors)):
                            chunk_docs.append({
                                "bookId": book_id,
                                "pageNumber": r.get("pageNumber"),
                                "chunkIndex": chunk_idx,
                                "text": txt,
                                "embedding": vec,
                                "createdAt": datetime.utcnow()
                            })

                        # Clean up old chunks for this page
                        await db.chunks.delete_many({"bookId": book_id, "pageNumber": r.get("pageNumber")})
                        
                        # Insert new chunks
                        if chunk_docs:
                            await db.chunks.insert_many(chunk_docs)

                        # Update page status
                        await db.pages.update_one(
                            {"bookId": book_id, "pageNumber": r.get("pageNumber")},
                            {"$set": {"isIndexed": True}}
                        )
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
                        db,
                        book_id,
                        "embedding",
                        str(exc),
                        {"batch_start": start, "batch_end": start + len(batch) - 1},
                    )

        completed_count = len([r for r in all_pages if r.get("status") == "completed"])
        final_status = "ready" if completed_count == total_pages else "error"

        await db.books.update_one(
            {"id": book_id},
            {
                "$set": {
                    "status": final_status,
                    "lastUpdated": datetime.utcnow(),
                }
            },
        )
        log_json(logger, logging.INFO, "Book processing finished", book_id=book_id, status=final_status)
        if job_key:
            if final_status == "ready":
                await update_job_status(db, job_key, "succeeded")
            else:
                await update_job_status(db, job_key, "failed", f"Final status: {final_status}")

    except Exception as exc:
        log_json(logger, logging.ERROR, "Processing task failed", book_id=book_id, error=str(exc))
        await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
        await record_book_error(db, book_id, "processing", str(exc))
        if job_key:
            await update_job_status(db, job_key, "failed", str(exc))
        if raise_on_error:
            raise
    finally:
        RUNNING_TASKS.discard(book_id)
        await _release_lock(db, book_id, job_key)
        if "doc" in locals():
            doc.close()
