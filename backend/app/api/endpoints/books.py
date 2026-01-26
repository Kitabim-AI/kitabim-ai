from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from typing import List, Optional
from datetime import datetime
import hashlib
import os
from bson import ObjectId
from app.models.schemas import Book, PaginatedBooks
from app.db.mongodb import db_manager
from app.core.config import settings
from app.services.pdf_service import process_pdf_task

router = APIRouter()

@router.get("/", response_model=PaginatedBooks)
async def get_books(
    page: int = 1, 
    pageSize: int = 10, 
    q: Optional[str] = None,
    sortBy: str = "title",
    order: int = 1 # 1 for asc, -1 for desc
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
        "totalPages": 0,
        "content": "",
        "results": [],
        "status": "processing",
        "uploadDate": now,
        "lastUpdated": now,
        "series": [],
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
        {"$set": {"results.$.status": "pending", "results.$.text": ""}}
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
                "results.$.status": "completed"
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
    await db.books.update_one(
        {"id": book.id},
        {"$set": book.dict()},
        upsert=True
    )
    background_tasks.add_task(process_pdf_task, book.id)
    return {"status": "success"}

@router.put("/{book_id}")
async def update_book_details(book_id: str, book_update: dict):
    db = db_manager.db
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
