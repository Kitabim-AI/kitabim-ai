from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import ai, books, chat
from app.core.config import settings
from app.db.mongodb import db_manager
from app.queue import enqueue_pdf_processing
from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json, request_id_var


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_langchain()
    await db_manager.connect_to_storage()

    db = db_manager.db
    if db is not None:
        try:
            logger = logging.getLogger("app.startup")
            log_json(logger, logging.INFO, "Checking for books needing resume or retrofitting")
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
                    log_json(
                        logger,
                        logging.INFO,
                        "Triggering startup task",
                        book_id=book["id"],
                        reason=reason,
                    )
                    asyncio.create_task(enqueue_pdf_processing(book["id"], reason="startup"))
        except Exception as exc:
            log_json(logger, logging.ERROR, "Startup task sweep failed", error=str(exc))

    yield

    await db_manager.close_storage()


app = FastAPI(title=settings.project_name, lifespan=lifespan)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    response = None
    logger = logging.getLogger("app.request")
    log_json(
        logger,
        logging.INFO,
        "Request started",
        method=request.method,
        path=request.url.path,
    )
    try:
        response = await call_next(request)
        return response
    finally:
        if response is not None:
            response.headers["X-Request-ID"] = request_id
            log_json(
                logger,
                logging.INFO,
                "Request completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
            )
        request_id_var.reset(token)

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
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])


@app.get("/")
async def root():
    return {"message": "Welcome to Kitabim.AI API"}


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/ready")
async def ready():
    if db_manager.client is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    try:
        await db_manager.client.admin.command("ping")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database not ready: {exc}")
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
