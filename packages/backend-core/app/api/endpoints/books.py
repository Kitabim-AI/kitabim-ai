from __future__ import annotations

import hashlib
import uuid
import os
import io
from datetime import datetime
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from app.core.config import settings
from app.db.mongodb import db_manager
from app.models.schemas import Book, PaginatedBooks
from app.queue import enqueue_pdf_processing
from app.services.spell_check_service import spell_check_service
from app.utils.markdown import normalize_markdown

router = APIRouter()


@router.get("/", response_model=PaginatedBooks)
async def get_books(
    page: int = 1,
    pageSize: int = 10,
    q: Optional[str] = None,
    sortBy: str = "title",
    order: int = 1,
    groupByWork: bool = False,
):
    db = db_manager.db
    skip = (page - 1) * pageSize

    query = {}
    if q:
        query = {
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"author": {"$regex": q, "$options": "i"}},
            ]
        }

    total = await db.books.count_documents(query)
    total_ready = await db.books.count_documents({"status": "ready"})

    projection = {
        "content": 0,
        "results.text": 0,
        "results.embedding": 0,
        "previousContent": 0,
        "previousResults": 0,
    }

    def parse_date(val):
        if val is None:
            return datetime.min
        if isinstance(val, datetime):
            return val.replace(tzinfo=None) if val.tzinfo else val
        if isinstance(val, str):
            try:
                parsed = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
            except Exception:
                return datetime.min
        return datetime.min

    if groupByWork and sortBy == "uploadDate":
        all_cursor = db.books.find(query, projection).sort([("uploadDate", order), ("_id", -1)])
        all_books = await all_cursor.to_list(None)

        work_groups = {}
        no_work_books = []
        work_priority = {}

        for b in all_books:
            if "_id" in b and "id" not in b:
                b["id"] = str(b["_id"])

            book_title = b.get("title")
            book_author = b.get("author") or ""
            book_date = parse_date(b.get("uploadDate"))

            if book_title:
                work_key = (book_title, book_author)
                if work_key not in work_groups:
                    work_groups[work_key] = []
                    work_priority[work_key] = book_date
                work_groups[work_key].append(b)
                current_priority = work_priority[work_key]
                if (order == -1 and book_date > current_priority) or (order == 1 and book_date < current_priority):
                    work_priority[work_key] = book_date
            else:
                no_work_books.append(b)

        for work_key in work_groups:
            work_groups[work_key].sort(key=lambda x: parse_date(x.get("uploadDate")), reverse=(order == -1))

        sortable_items = []
        for work_key, books_in_work in work_groups.items():
            sortable_items.append((work_priority[work_key], True, work_key, books_in_work))

        for book in no_work_books:
            sortable_items.append((parse_date(book.get("uploadDate")), False, None, [book]))

        sortable_items.sort(key=lambda x: x[0], reverse=(order == -1))

        ordered_books = []
        for _, _, _, books_in_group in sortable_items:
            ordered_books.extend(books_in_group)

        paginated_books = ordered_books[skip : skip + pageSize]
        return {
            "books": paginated_books,
            "total": total,
            "totalReady": total_ready,
            "page": page,
            "pageSize": pageSize,
        }

    books_cursor = (
        db.books.find(query, projection)
        .sort([(sortBy, order), ("_id", -1)])
        .skip(skip)
        .limit(pageSize)
    )
    books_list = await books_cursor.to_list(pageSize)

    formatted = []
    for b in books_list:
        if "_id" in b and "id" not in b:
            b["id"] = str(b["_id"])
        formatted.append(b)

    return {
        "books": formatted,
        "total": total,
        "totalReady": total_ready,
        "page": page,
        "pageSize": pageSize,
    }


@router.get("/{book_id}", response_model=Book)
async def get_book(book_id: str):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id}, {"results.embedding": 0})
    if book:
        if "_id" in book and "id" not in book:
            book["id"] = str(book["_id"])
        return book
    raise HTTPException(status_code=404, detail="Book not found")


@router.get("/hash/{content_hash}", response_model=Book)
async def get_book_by_hash(content_hash: str):
    db = db_manager.db
    book = await db.books.find_one({"contentHash": content_hash})
    if book:
        return book
    raise HTTPException(status_code=404, detail="Book not found")


@router.post("/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    db = db_manager.db
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    temp_path = settings.uploads_dir / f".upload_{uuid.uuid4().hex}.pdf"
    hasher = hashlib.sha256()

    try:
        with open(temp_path, "wb") as handle:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                hasher.update(chunk)
                handle.write(chunk)

        content_hash = hasher.hexdigest()
        existing = await db.books.find_one({"contentHash": content_hash})
        if existing:
            temp_path.unlink(missing_ok=True)
            return {"bookId": existing.get("id"), "status": "existing"}

        book_id = hashlib.md5(f"{file.filename}{datetime.utcnow()}".encode()).hexdigest()[:12]
        file_path = settings.uploads_dir / f"{book_id}.pdf"
        os.replace(temp_path, file_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise

    now = datetime.utcnow()
    new_book = {
        "id": book_id,
        "contentHash": content_hash,
        "title": file.filename.replace(".pdf", ""),
        "author": "Unknown Author",
        "volume": None,
        "totalPages": 0,
        "content": "",
        "results": [],
        "status": "pending",
        "uploadDate": now,
        "lastUpdated": now,
        "categories": [],
        "processingStep": "ocr",
        "ocrProvider": None,
        "previousContent": None,
        "previousResults": None,
        "previousVersionAt": None,
    }

    await db.books.insert_one(new_book)

    return {"bookId": book_id, "status": "uploaded"}


@router.post("/{book_id}/start-ocr")
async def start_ocr(book_id: str, payload: dict, background_tasks: BackgroundTasks):
    db = db_manager.db
    provider = (payload.get("provider") or "").lower()
    if provider not in {"local", "gemini"}:
        raise HTTPException(status_code=400, detail="Invalid OCR provider")

    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("status") == "processing":
        return {"status": "already_processing"}

    update_fields = {
        "status": "processing",
        "processingStep": "ocr",
        "ocrProvider": provider,
        "lastUpdated": datetime.utcnow(),
    }

    if book.get("status") != "pending" and (book.get("content") or book.get("results")):
        update_fields["previousContent"] = book.get("content") or ""
        update_fields["previousResults"] = book.get("results") or []
        update_fields["previousVersionAt"] = datetime.utcnow()

    if book.get("status") != "pending" and book.get("totalPages", 0) > 0:
        reset_results = []
        for page_num in range(1, int(book.get("totalPages", 0)) + 1):
            reset_results.append(
                {
                    "pageNumber": page_num,
                    "text": "",
                    "status": "pending",
                    "isVerified": False,
                    "error": None,
                }
            )
        update_fields["results"] = reset_results
        update_fields["content"] = ""

    await db.books.update_one({"id": book_id}, {"$set": update_fields})
    await enqueue_pdf_processing(book_id, reason=f"start_{provider}", background_tasks=background_tasks)
    return {"status": "started", "provider": provider}


@router.post("/{book_id}/retry-ocr")
async def retry_failed_ocr(
    book_id: str,
    background_tasks: BackgroundTasks,
    payload: Optional[dict] = None,
):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("status") == "processing":
        return {"status": "already_processing"}

    provider = (payload or {}).get("provider") if payload else None
    if provider:
        provider = provider.lower()
        if provider not in {"local", "gemini"}:
            raise HTTPException(status_code=400, detail="Invalid OCR provider")

    provider = provider or (book.get("ocrProvider") or settings.ocr_provider)
    if provider not in {"local", "gemini"}:
        raise HTTPException(status_code=400, detail="Invalid OCR provider")

    failed_pages = [
        r.get("pageNumber")
        for r in (book.get("results") or [])
        if r.get("status") == "error"
    ]
    if not failed_pages:
        return {"status": "no_failed_pages"}

    await db.books.update_one(
        {"id": book_id},
        {
            "$set": {
                "status": "processing",
                "processingStep": "ocr",
                "ocrProvider": provider,
                "lastUpdated": datetime.utcnow(),
            }
        },
    )
    for page_num in failed_pages:
        await db.books.update_one(
            {"id": book_id, "results.pageNumber": page_num},
            {
                "$set": {
                    "results.$.status": "pending",
                    "results.$.text": "",
                    "results.$.error": None,
                    "results.$.isVerified": False,
                }
            },
        )
    await enqueue_pdf_processing(book_id, reason="retry_failed", background_tasks=background_tasks)
    return {"status": "retry_started", "provider": provider, "failedPages": failed_pages}


@router.post("/{book_id}/revert")
async def revert_book(book_id: str, background_tasks: BackgroundTasks):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    previous_content = book.get("previousContent")
    previous_results = book.get("previousResults")
    if not previous_content and not previous_results:
        raise HTTPException(status_code=400, detail="No previous version available")

    restored_results = []
    for res in (previous_results or []):
        r = dict(res)
        r.pop("embedding", None)
        r["isVerified"] = True
        if r.get("text"):
            r["status"] = "completed"
        restored_results.append(r)

    await db.books.update_one(
        {"id": book_id},
        {
            "$set": {
                "content": previous_content or "",
                "results": restored_results,
                "status": "processing",
                "processingStep": "rag",
                "lastUpdated": datetime.utcnow(),
            },
            "$unset": {
                "previousContent": "",
                "previousResults": "",
                "previousVersionAt": "",
            },
        },
    )
    await enqueue_pdf_processing(book_id, reason="revert", background_tasks=background_tasks)
    return {"status": "reverted"}


@router.post("/{book_id}/reprocess")
async def reprocess_book(book_id: str, background_tasks: BackgroundTasks):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if book.get("status") == "processing":
        return {"status": "already_processing"}

    await db.books.update_one(
        {"id": book_id},
        {"$set": {"status": "processing", "lastUpdated": datetime.utcnow()}},
    )
    await enqueue_pdf_processing(book_id, reason="reprocess", background_tasks=background_tasks)
    return {"status": "reprocessing_started"}


@router.post("/{book_id}/pages/{page_num}/reset")
async def reset_page(book_id: str, page_num: int, background_tasks: BackgroundTasks):
    db = db_manager.db
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {
            "$set": {
                "results.$.status": "pending",
                "results.$.text": "",
                "results.$.isVerified": False,
            }
        },
    )
    await db.books.update_one(
        {"id": book_id},
        {"$set": {"status": "processing", "lastUpdated": datetime.utcnow()}},
    )
    await enqueue_pdf_processing(book_id, reason="page_reset", background_tasks=background_tasks)
    return {"status": "page_reset_started"}


@router.post("/{book_id}/pages/{page_num}/update")
async def update_page_text(book_id: str, page_num: int, payload: dict, background_tasks: BackgroundTasks):
    db = db_manager.db
    new_text = normalize_markdown(payload.get("text", ""))
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {
            "$set": {
                "results.$.text": new_text,
                "results.$.status": "completed",
                "results.$.isVerified": True,
            },
            "$unset": {"results.$.embedding": ""},
        },
    )
    await db.books.update_one({"id": book_id}, {"$set": {"lastUpdated": datetime.utcnow()}})
    await enqueue_pdf_processing(book_id, reason="page_update", background_tasks=background_tasks)
    return {"status": "page_updated", "requires_rag": True}


@router.post("/")
async def create_book(book: Book, background_tasks: BackgroundTasks):
    db = db_manager.db
    book_dict = book.dict()
    book_dict.pop("uploadDate", None)
    if "content" in book_dict:
        book_dict["content"] = normalize_markdown(book_dict.get("content") or "")
    results = book_dict.get("results") or []
    for result in results:
        if "text" in result:
            result["text"] = normalize_markdown(result.get("text") or "")

    await db.books.update_one({"id": book.id}, {"$set": book_dict}, upsert=True)
    await enqueue_pdf_processing(book.id, reason="create_book", background_tasks=background_tasks)
    return {"status": "success"}


@router.put("/{book_id}")
async def update_book_details(book_id: str, book_update: dict):
    db = db_manager.db
    book_update.pop("uploadDate", None)
    if "content" in book_update:
        book_update["content"] = normalize_markdown(book_update.get("content") or "")
    if "results" in book_update:
        for result in book_update.get("results") or []:
            if "text" in result:
                result["text"] = normalize_markdown(result.get("text") or "")

    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except Exception:
            pass

    result = await db.books.update_one(query, {"$set": book_update})
    if result.matched_count:
        return {"status": "updated", "modified": result.modified_count > 0}
    raise HTTPException(status_code=404, detail="Book not found")


@router.delete("/{book_id}")
async def delete_book(book_id: str):
    db = db_manager.db
    file_path = settings.uploads_dir / f"{book_id}.pdf"
    if file_path.exists():
        os.remove(file_path)

    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except Exception:
            pass

    result = await db.books.delete_one(query)
    if result.deleted_count:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Book not found")


@router.post("/upload-cover")
async def upload_cover(title: str = Form(...), file: UploadFile = File(...)):
    from PIL import Image

    db = db_manager.db
    book = await db.books.find_one({"title": {"$regex": title, "$options": "i"}})
    if not book:
        raise HTTPException(status_code=404, detail=f"Book with title '{title}' not found")

    book_id = book.get("id") or str(book.get("_id"))

    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {allowed_types}")

    try:
        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        cover_path = settings.covers_dir / f"{book_id}.jpg"
        img.save(cover_path, "JPEG", quality=90)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {exc}")

    cover_url = f"/api/covers/{book_id}.jpg"
    await db.books.update_one(
        {"id": book_id},
        {"$set": {"coverUrl": cover_url, "lastUpdated": datetime.utcnow()}},
    )

    return {
        "status": "success",
        "bookId": book_id,
        "title": book.get("title"),
        "coverUrl": cover_url,
    }


@router.post("/{book_id}/spell-check")
async def check_book_spelling(book_id: str):
    db = db_manager.db
    try:
        results = await spell_check_service.check_book(book_id, db)
        return {
            "bookId": book_id,
            "status": "success",
            "totalPagesWithIssues": len(results),
            "results": {
                str(page_num): {
                    "pageNumber": check.pageNumber,
                    "corrections": [c.dict() for c in check.corrections],
                    "totalIssues": check.totalIssues,
                    "checkedAt": check.checkedAt,
                }
                for page_num, check in results.items()
            },
        }
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {exc}")


@router.post("/{book_id}/pages/{page_num}/spell-check")
async def check_page_spelling(book_id: str, page_num: int):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    page_result = next((page for page in book.get("results", []) if page.get("pageNumber") == page_num), None)
    if not page_result:
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")

    page_text = page_result.get("text", "")
    if not page_text:
        return {
            "bookId": book_id,
            "pageNumber": page_num,
            "corrections": [],
            "totalIssues": 0,
            "message": "Page has no text to check",
        }

    try:
        spell_check = await spell_check_service.check_page_text(page_text, page_num)
        return {
            "bookId": book_id,
            "pageNumber": spell_check.pageNumber,
            "corrections": [c.dict() for c in spell_check.corrections],
            "totalIssues": spell_check.totalIssues,
            "checkedAt": spell_check.checkedAt,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {exc}")


@router.post("/{book_id}/pages/{page_num}/apply-corrections")
async def apply_spelling_corrections(
    book_id: str,
    page_num: int,
    payload: dict,
    background_tasks: BackgroundTasks,
):
    db = db_manager.db
    corrections = payload.get("corrections", [])
    if not corrections:
        raise HTTPException(status_code=400, detail="No corrections provided")

    try:
        success = await spell_check_service.apply_corrections(book_id, page_num, corrections, db)
        if success:
            await enqueue_pdf_processing(book_id, reason="spell_apply", background_tasks=background_tasks)
            return {
                "status": "success",
                "bookId": book_id,
                "pageNumber": page_num,
                "correctionsApplied": len(corrections),
                "message": "Corrections applied successfully. Embeddings will be regenerated.",
            }
        raise HTTPException(status_code=404, detail="Book or page not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to apply corrections: {exc}")
