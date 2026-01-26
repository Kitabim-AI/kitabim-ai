from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import os

from app.api.endpoints import books, chat
from app.core.config import settings
from app.db.mongodb import db_manager
from app.services.pdf_service import process_pdf_task

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: MongoDB Connection
    await db_manager.connect_to_storage()
    
    # Resume interrupted or retrofit books
    db = db_manager.db
    if db is not None:
        try:
            print("🔍 Checking for books needing resume or retrofitting...")
            all_books = await db.books.find().to_list(2000)
            for book in all_books:
                # RETROFIT: Ensure 'id' field exists
                if "id" not in book:
                    book_id = str(book["_id"])
                    print(f"🆔 Retrofitting missing ID for book: {book.get('title', 'Unknown')} -> {book_id}")
                    await db.books.update_one({"_id": book["_id"]}, {"$set": {"id": book_id}})
                    book["id"] = book_id

                needs_resume = book["status"] == "processing"
                needs_cover = book["status"] == "ready" and (not book.get("coverUrl") or not os.path.exists(os.path.join(settings.COVERS_DIR, f"{book['id']}.jpg")))
                needs_rag = book["status"] == "ready" and any(r.get("status") == "completed" and "embedding" not in r for r in book.get("results", []))
                
                if needs_resume or needs_cover or needs_rag:
                    reason = "Resume" if needs_resume else "Cover Retrofit" if needs_cover else "RAG Retrofit"
                    print(f"♻️ Triggering task for Book {book['id']} ({reason})")
                    asyncio.create_task(process_pdf_task(book["id"]))
        except Exception as e:
            print(f"Error during startup tasks: {e}")
            
    yield
    # Shutdown
    await db_manager.close_storage()

app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Mounts
app.mount("/api/covers", StaticFiles(directory=settings.COVERS_DIR), name="covers")

# Routers
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])

@app.get("/")
async def root():
    return {"message": "Welcome to Kitabim.AI API"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
