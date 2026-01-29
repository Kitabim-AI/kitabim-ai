from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File, Form
from typing import List, Optional
from datetime import datetime
import hashlib
import os
from bson import ObjectId
from app.models.schemas import Book, PaginatedBooks
from app.db.mongodb import db_manager
from app.core.config import settings
from app.services.pdf_service import process_pdf_task
from app.services.spell_check_service import spell_check_service

router = APIRouter()

@router.get("/", response_model=PaginatedBooks)
async def get_books(
    page: int = 1, 
    pageSize: int = 10, 
    q: Optional[str] = None,
    sortBy: str = "title",
    order: int = 1, # 1 for asc, -1 for desc
    groupByWork: bool = False  # When true, keeps books with same title+author together
):
    db = db_manager.db
    skip = (page - 1) * pageSize
    
    query = {}
    if q:
        query = {
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"author": {"$regex": q, "$options": "i"}}
            ]
        }
    
    total = await db.books.count_documents(query)
    totalReady = await db.books.count_documents({"status": "ready"})
    
    projection = {
        "content": 0,
        "results.text": 0,
        "results.embedding": 0
    }
    
    # Helper to safely get a datetime from potentially string or datetime value
    # Returns naive datetime for consistent comparison
    def parse_date(val):
        if val is None:
            return datetime.min
        if isinstance(val, datetime):
            # Strip timezone info for consistent comparison
            if val.tzinfo is not None:
                return val.replace(tzinfo=None)
            return val
        if isinstance(val, str):
            try:
                # Try ISO format first
                parsed = datetime.fromisoformat(val.replace('Z', '+00:00'))
                # Strip timezone info for consistent comparison
                if parsed.tzinfo is not None:
                    return parsed.replace(tzinfo=None)
                return parsed
            except:
                return datetime.min
        return datetime.min
    
    # Work-aware sorting: group books by title+author, order groups by most recent uploadDate
    if groupByWork and sortBy == "uploadDate":
        # Fetch all matching books (we need all to properly group by work)
        all_cursor = db.books.find(query, projection).sort([("uploadDate", order), ("_id", -1)])
        all_books = await all_cursor.to_list(None)
        
        # Build work -> books mapping and track latest uploadDate per work
        work_groups = {}  # (title, author) -> list of books
        no_work_books = []  # Books without title
        work_priority = {}  # (title, author) -> latest uploadDate (as datetime)
        
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
                # Update priority to the most recent uploadDate in the group
                current_priority = work_priority[work_key]
                if (order == -1 and book_date > current_priority) or \
                   (order == 1 and book_date < current_priority):
                    work_priority[work_key] = book_date
            else:
                no_work_books.append(b)
        
        # Sort books within each work by uploadDate
        for work_key in work_groups:
            work_groups[work_key].sort(
                key=lambda x: parse_date(x.get("uploadDate")),
                reverse=(order == -1)
            )
        
        # Create list of (priority_date, is_work, work_key_or_book)
        # For work groups, use the work priority date
        # For individual books, use their own uploadDate
        sortable_items = []
        for work_key, books_in_work in work_groups.items():
            priority_date = work_priority[work_key]
            sortable_items.append((priority_date, True, work_key, books_in_work))
        
        for book in no_work_books:
            priority_date = parse_date(book.get("uploadDate"))
            sortable_items.append((priority_date, False, None, [book]))
        
        # Sort groups by priority date
        sortable_items.sort(key=lambda x: x[0], reverse=(order == -1))
        
        # Flatten into final ordered list
        ordered_books = []
        for _, _, _, books_in_group in sortable_items:
            ordered_books.extend(books_in_group)
        
        # Apply pagination
        paginated_books = ordered_books[skip:skip + pageSize]
        
        return {
            "books": paginated_books,
            "total": total,
            "totalReady": totalReady,
            "page": page,
            "pageSize": pageSize
        }
    
    # Standard sorting (no work grouping)
    books_cursor = db.books.find(query, projection).sort([(sortBy, order), ("_id", -1)]).skip(skip).limit(pageSize)
    books_list = await books_cursor.to_list(pageSize)
    
    formatted_books = []
    for b in books_list:
        if "_id" in b and "id" not in b:
            b["id"] = str(b["_id"])
        formatted_books.append(b)

    return {
        "books": formatted_books,
        "total": total,
        "totalReady": totalReady,
        "page": page,
        "pageSize": pageSize
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
    
    pdf_bytes = await file.read()
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    existing = await db.books.find_one({"contentHash": content_hash})
    if existing:
        return {"bookId": existing["id"], "status": "existing"}
        
    book_id = hashlib.md5(f"{file.filename}{datetime.now()}".encode()).hexdigest()[:12]
    
    file_path = os.path.join(settings.UPLOADS_DIR, f"{book_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    now = datetime.now()
    new_book = {
        "id": book_id,
        "contentHash": content_hash,
        "title": file.filename.replace(".pdf", ""),
        "author": "Unknown Author",
        "volume": None,
        "totalPages": 0,
        "content": "",
        "results": [],
        "status": "processing",
        "uploadDate": now,
        "lastUpdated": now,
        "categories": []
    }
    
    await db.books.insert_one(new_book)
    background_tasks.add_task(process_pdf_task, book_id)
    
    return {"bookId": book_id, "status": "started"}

@router.post("/{book_id}/reprocess")
async def reprocess_book(book_id: str, background_tasks: BackgroundTasks):
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if book["status"] == "processing":
        return {"status": "already_processing"}

    await db.books.update_one({"id": book_id}, {"$set": {"status": "processing", "lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "reprocessing_started"}

@router.post("/{book_id}/pages/{page_num}/reset")
async def reset_page(book_id: str, page_num: int, background_tasks: BackgroundTasks):
    db = db_manager.db
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {"$set": {"results.$.status": "pending", "results.$.text": "", "results.$.isVerified": False}}
    )
    await db.books.update_one({"id": book_id}, {"$set": {"status": "processing", "lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "page_reset_started"}

@router.post("/{book_id}/pages/{page_num}/update")
async def update_page_text(book_id: str, page_num: int, payload: dict, background_tasks: BackgroundTasks):
    db = db_manager.db
    new_text = payload.get("text", "")
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {
            "$set": {
                "results.$.text": new_text,
                "results.$.status": "completed",
                "results.$.isVerified": True
            },
            "$unset": {
                "results.$.embedding": ""
            }
        }
    )
    await db.books.update_one({"id": book_id}, {"$set": {"lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "page_updated", "requires_rag": True}

@router.post("/")
async def create_book(book: Book, background_tasks: BackgroundTasks):
    db = db_manager.db
    # Protect uploadDate and isVerified from being overwritten in bulk
    book_dict = book.dict()
    book_dict.pop("uploadDate", None)
    
    await db.books.update_one(
        {"id": book.id},
        {"$set": book_dict},
        upsert=True
    )
    background_tasks.add_task(process_pdf_task, book.id)
    return {"status": "success"}

@router.put("/{book_id}")
async def update_book_details(book_id: str, book_update: dict):
    db = db_manager.db
    # Protect uploadDate from being overwritten
    book_update.pop("uploadDate", None)
    
    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except:
            pass
            
    result = await db.books.update_one(query, {"$set": book_update})
    if result.matched_count:
        return {"status": "updated", "modified": result.modified_count > 0}
    raise HTTPException(status_code=404, detail="Book not found")

@router.delete("/{book_id}")
async def delete_book(book_id: str):
    db = db_manager.db
    file_path = os.path.join(settings.UPLOADS_DIR, f"{book_id}.pdf")
    if os.path.exists(file_path):
        os.remove(file_path)

    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except:
            pass

    result = await db.books.delete_one(query)
    if result.deleted_count:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Book not found")

@router.post("/upload-cover")
async def upload_cover(
    title: str = Form(...),
    file: UploadFile = File(...)
):
    """
    Upload a cover image for a book by its title.
    Accepts image files (PNG, JPG, JPEG, WebP) and converts to JPG.
    """
    from PIL import Image
    import io
    
    db = db_manager.db
    
    # Find book by title (case-insensitive partial match)
    book = await db.books.find_one({"title": {"$regex": title, "$options": "i"}})
    if not book:
        raise HTTPException(status_code=404, detail=f"Book with title '{title}' not found")
    
    book_id = book.get("id") or str(book.get("_id"))
    
    # Validate file type
    allowed_types = ["image/png", "image/jpeg", "image/jpg", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Allowed: {allowed_types}")
    
    # Read and convert image to JPG
    try:
        image_data = await file.read()
        img = Image.open(io.BytesIO(image_data))
        
        # Convert to RGB if necessary (for PNG with alpha, etc.)
        if img.mode in ('RGBA', 'P', 'LA'):
            img = img.convert('RGB')
        
        # Save as JPG
        cover_path = os.path.join(settings.COVERS_DIR, f"{book_id}.jpg")
        img.save(cover_path, 'JPEG', quality=90)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")
    
    # Update book record
    cover_url = f"/api/covers/{book_id}.jpg"
    await db.books.update_one(
        {"id": book_id},
        {"$set": {"coverUrl": cover_url, "lastUpdated": datetime.now()}}
    )
    
    return {
        "status": "success",
        "bookId": book_id,
        "title": book.get("title"),
        "coverUrl": cover_url
    }

@router.post("/{book_id}/spell-check")
async def check_book_spelling(book_id: str):
    """
    Check all pages of a book for spelling and OCR errors.
    Returns a dictionary mapping page numbers to their spell check results.
    """
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
                    "checkedAt": check.checkedAt
                }
                for page_num, check in results.items()
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {str(e)}")

@router.post("/{book_id}/pages/{page_num}/spell-check")
async def check_page_spelling(book_id: str, page_num: int):
    """
    Check a single page for spelling and OCR errors.
    """
    db = db_manager.db
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Find the page
    page_result = None
    for page in book.get("results", []):
        if page.get("pageNumber") == page_num:
            page_result = page
            break
    
    if not page_result:
        raise HTTPException(status_code=404, detail=f"Page {page_num} not found")
    
    page_text = page_result.get("text", "")
    if not page_text:
        return {
            "bookId": book_id,
            "pageNumber": page_num,
            "corrections": [],
            "totalIssues": 0,
            "message": "Page has no text to check"
        }
    
    try:
        spell_check = await spell_check_service.check_page_text(page_text, page_num)
        return {
            "bookId": book_id,
            "pageNumber": spell_check.pageNumber,
            "corrections": [c.dict() for c in spell_check.corrections],
            "totalIssues": spell_check.totalIssues,
            "checkedAt": spell_check.checkedAt
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Spell check failed: {str(e)}")

@router.post("/{book_id}/pages/{page_num}/apply-corrections")
async def apply_spelling_corrections(
    book_id: str, 
    page_num: int, 
    payload: dict,
    background_tasks: BackgroundTasks
):
    """
    Apply approved spelling corrections to a page.
    Expects payload: { "corrections": [...] }
    """
    db = db_manager.db
    corrections = payload.get("corrections", [])
    
    if not corrections:
        raise HTTPException(status_code=400, detail="No corrections provided")
    
    try:
        success = await spell_check_service.apply_corrections(
            book_id, 
            page_num, 
            corrections, 
            db
        )
        
        if success:
            # Trigger embedding regeneration for the updated page
            background_tasks.add_task(process_pdf_task, book_id)
            return {
                "status": "success",
                "bookId": book_id,
                "pageNumber": page_num,
                "correctionsApplied": len(corrections),
                "message": "Corrections applied successfully. Embeddings will be regenerated."
            }
        else:
            raise HTTPException(status_code=404, detail="Book or page not found")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to apply corrections: {str(e)}")
