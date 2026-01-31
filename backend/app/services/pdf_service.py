from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
import fitz

from app.core.config import settings
from app.db.mongodb import db_manager
from app.langchain.models import GeminiEmbeddings
from app.services.ocr_service import ocr_page
from app.utils.text import clean_uyghur_text

RUNNING_TASKS: set[str] = set()


def _resolve_pdf_path(book_id: str) -> Path:
    return settings.uploads_dir / f"{book_id}.pdf"


def _resolve_cover_path(book_id: str) -> Path:
    return settings.covers_dir / f"{book_id}.jpg"


async def process_pdf_task(book_id: str) -> None:
    if book_id in RUNNING_TASKS:
        print(f"⏩ Task for {book_id} already running.")
        return

    RUNNING_TASKS.add(book_id)
    db = db_manager.db

    try:
        file_path = _resolve_pdf_path(book_id)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
            return

        doc = fitz.open(file_path)
        total_pages = doc.page_count

        book = await db.books.find_one({"id": book_id})
        if not book:
            return

        results = book.get("results", []) or []
        existing_by_page = {r.get("pageNumber"): r for r in results if r.get("pageNumber")}

        if not results or len(results) != total_pages:
            results = []
            for page_num in range(1, total_pages + 1):
                existing = existing_by_page.get(page_num, {})
                results.append(
                    {
                        "pageNumber": page_num,
                        "text": existing.get("text", ""),
                        "status": existing.get("status", "pending"),
                        "isVerified": existing.get("isVerified", False),
                        "error": existing.get("error"),
                        **({"embedding": existing.get("embedding")} if existing.get("embedding") else {}),
                    }
                )

            await db.books.update_one(
                {"id": book_id},
                {
                    "$set": {
                        "totalPages": total_pages,
                        "results": results,
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
                print(f"Failed to extract cover for {book_id}: {exc}")

        pages_to_process = [
            r["pageNumber"]
            for r in results
            if r.get("status") != "completed" or (r.get("status") == "completed" and "embedding" not in r)
        ]

        if not pages_to_process:
            await db.books.update_one({"id": book_id}, {"$set": {"status": "ready"}})
            return

        semaphore = asyncio.Semaphore(settings.max_parallel_pages)

        async def process_page(page_num: int) -> None:
            async with semaphore:
                try:
                    current_book = await db.books.find_one({"id": book_id})
                    page_record = next(
                        (r for r in current_book.get("results", []) if r.get("pageNumber") == page_num),
                        None,
                    )
                    existing_text = page_record.get("text", "") if page_record else ""
                    is_verified = page_record.get("isVerified", False) if page_record else False
                    already_ocr = is_verified or (
                        page_record and page_record.get("status") == "completed" and len(existing_text) > 40
                    )

                    if not already_ocr:
                        await db.books.update_one(
                            {"id": book_id, "results.pageNumber": page_num},
                            {"$set": {"results.$.status": "processing"}},
                        )

                    success = already_ocr
                    page_text = existing_text

                    if not already_ocr:
                        page = doc.load_page(page_num - 1)
                        try:
                            page_text = await ocr_page(
                                page,
                                current_book.get("title", "Unknown"),
                                page_num,
                            )
                            success = True
                        except Exception as exc:
                            print(f"OCR failed for {book_id} p{page_num}: {exc}")
                            page_text = f"[OCR Error: {exc}]"

                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": page_num},
                        {
                            "$set": {
                                "results.$.text": page_text,
                                "results.$.status": "completed" if success else "error",
                            }
                        },
                    )
                except Exception as exc:
                    print(f"Error processing page {page_num}: {exc}")

        await asyncio.gather(*[process_page(p) for p in pages_to_process])

        await db.books.update_one({"id": book_id}, {"$set": {"processingStep": "rag"}})

        updated_book = await db.books.find_one({"id": book_id})
        pages_to_embed = [
            r for r in updated_book.get("results", []) if r.get("status") == "completed" and "embedding" not in r
        ]

        if pages_to_embed:
            embedder = GeminiEmbeddings()
            batch_size = 100
            for start in range(0, len(pages_to_embed), batch_size):
                batch = pages_to_embed[start : start + batch_size]
                text_batch = [r.get("text", "")[:2000] for r in batch]
                try:
                    embeddings = await embedder.aembed_documents(text_batch)
                    for idx, r in enumerate(batch):
                        if idx >= len(embeddings):
                            break
                        await db.books.update_one(
                            {"id": book_id, "results.pageNumber": r.get("pageNumber")},
                            {"$set": {"results.$.embedding": embeddings[idx]}},
                        )
                except Exception as exc:
                    print(f"Embedding batch failed for {book_id} (batch {start}-{start+len(batch)-1}): {exc}")

        updated_book = await db.books.find_one({"id": book_id})
        sorted_results = sorted(updated_book.get("results", []), key=lambda x: x.get("pageNumber", 0))
        raw_combined = "\n".join([r.get("text", "") for r in sorted_results if r.get("status") == "completed"])
        full_content = clean_uyghur_text(raw_combined)

        completed_count = len([r for r in updated_book.get("results", []) if r.get("status") == "completed"])
        final_status = "ready" if completed_count == total_pages else "error"

        await db.books.update_one(
            {"id": book_id},
            {
                "$set": {
                    "content": full_content,
                    "status": final_status,
                    "lastUpdated": datetime.utcnow(),
                }
            },
        )
        print(f"Book {book_id} finished with status {final_status}.")

    except Exception as exc:
        print(f"Processing task failed for {book_id}: {exc}")
        await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
    finally:
        RUNNING_TASKS.discard(book_id)
        if "doc" in locals():
            doc.close()
