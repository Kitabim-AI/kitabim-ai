from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import books, chat
from app.core.config import settings
from app.db.mongodb import db_manager
from app.services.pdf_service import process_pdf_task


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db_manager.connect_to_storage()

    db = db_manager.db
    if db is not None:
        try:
            print("🔍 Checking for books needing resume or retrofitting...")
            all_books = await db.books.find().to_list(2000)
            for book in all_books:
                if "id" not in book:
                    book_id = str(book.get("_id"))
                    await db.books.update_one({"_id": book.get("_id")}, {"$set": {"id": book_id}})
                    book["id"] = book_id

                needs_resume = book.get("status") == "processing"
                cover_file = settings.covers_dir / f"{book['id']}.jpg"
                needs_cover = (
                    book.get("status") == "ready"
                    and (not book.get("coverUrl") or not cover_file.exists())
                )
                needs_rag = (
                    book.get("status") == "ready"
                    and any(
                        r.get("status") == "completed" and "embedding" not in r
                        for r in book.get("results", [])
                    )
                )
                needs_results = book.get("totalPages", 0) == 0 and (settings.uploads_dir / f"{book['id']}.pdf").exists()

                if needs_resume or needs_cover or needs_rag or needs_results:
                    reason = "Resume" if needs_resume else "Cover Retrofit" if needs_cover else "RAG Retrofit" if needs_rag else "Results Retrofit"
                    print(f"♻️ Triggering task for Book {book['id']} ({reason})")
                    asyncio.create_task(process_pdf_task(book["id"]))
        except Exception as exc:
            print(f"Error during startup tasks: {exc}")

    yield

    await db_manager.close_storage()


app = FastAPI(title=settings.project_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/api/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")

app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])


@app.get("/")
async def root():
    return {"message": "Welcome to Kitabim.AI API"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
