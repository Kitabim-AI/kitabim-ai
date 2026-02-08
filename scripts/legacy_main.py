
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import motor.motor_asyncio
import os

app = FastAPI()

# MongoDB Connection (Using Atlas or Local)
# Replace with your actual MongoDB URI from environment variables
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client.uyghur_library

class ExtractionResult(BaseModel):
    pageNumber: int
    text: str
    status: str
    error: Optional[str] = None

class Book(BaseModel):
    id: str
    contentHash: str
    title: str
    author: str
    totalPages: int
    content: str
    results: List[ExtractionResult]
    status: str
    uploadDate: datetime

@app.get("/api/books", response_model=List[Book])
async def get_books():
    books = await db.books.find().to_list(1000)
    return books

@app.get("/api/books/hash/{content_hash}", response_model=Book)
async def get_book_by_hash(content_hash: str):
    book = await db.books.find_one({"contentHash": content_hash})
    if book:
        return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.post("/api/books")
async def create_book(book: Book):
    # Update if exists (upsert based on hash)
    await db.books.update_one(
        {"contentHash": book.contentHash},
        {"$set": book.dict()},
        upsert=True
    )
    return {"status": "success"}

@app.put("/api/books/{book_id}")
async def update_book(book_id: str, book_update: dict):
    result = await db.books.update_one({"id": book_id}, {"$set": book_update})
    if result.modified_count:
        return {"status": "updated"}
    raise HTTPException(status_code=404, detail="Book not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
