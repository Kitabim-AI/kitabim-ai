from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import logging
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.endpoints import ai, auth, books, chat, users
from app.core.config import settings
from app.db.session import init_db, close_db  # SQLAlchemy session management

from app.queue import enqueue_pdf_processing
from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json, request_id_var
from app.auth.jwt_handler import validate_jwt_secret


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_langchain()
    
    # Validate JWT secret key at startup
    logger = logging.getLogger("app.startup")
    try:
        validate_jwt_secret()
    except ValueError as e:
        log_json(logger, logging.WARNING, "JWT secret validation warning", error=str(e))
        log_json(logger, logging.WARNING, "Authentication features will not work properly")

    # Initialize SQLAlchemy (replaces db_manager.connect_to_storage())
    await init_db()

    # SQLAlchemy is already initialized above with await init_db()
    
    # Run startup tasks using SQLAlchemy
    try:
        logger = logging.getLogger("app.startup")
        log_json(logger, logging.INFO, "Checking for books needing resume or retrofitting")

        from app.db import session as db_session
        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.models import Page
        from sqlalchemy import select, func, and_

        async with db_session.async_session_factory() as session:
            books_repo = BooksRepository(session)
            pages_repo = PagesRepository(session)

            # Get all books (using SQLAlchemy model)
            all_books = await books_repo.get_all(limit=2000)

            for book in all_books:
                needs_resume = book.status == "processing"
                cover_file = settings.covers_dir / f"{book.id}.jpg"
                needs_cover = (
                    book.status == "ready"
                    and (not book.cover_url or not cover_file.exists())
                )

                # Check pages needing RAG (embeddings)
                has_missing_embeddings = False
                if book.status == "ready":
                    stmt = select(func.count(Page.id)).where(
                        and_(
                            Page.book_id == book.id,
                            Page.status == 'completed',
                            Page.is_indexed == False
                        )
                    )
                    res = await session.execute(stmt)
                    missing_emb_count = res.scalar()
                    has_missing_embeddings = missing_emb_count > 0

                needs_rag = (
                    book.status == "ready"
                    and has_missing_embeddings
                )
                needs_pages = (
                    book.status != "pending"
                    and book.total_pages == 0
                    and (settings.uploads_dir / f"{book.id}.pdf").exists()
                )

                if needs_resume or needs_cover or needs_rag or needs_pages:
                    reason = "Resume" if needs_resume else "Cover Retrofit" if needs_cover else "RAG Retrofit" if needs_rag else "Pages Retrofit"
                    log_json(
                        logger,
                        logging.INFO,
                        "Triggering startup task",
                        book_id=book.id,
                        reason=reason,
                    )
                    asyncio.create_task(enqueue_pdf_processing(book.id, reason="startup"))
    except Exception as exc:
        log_json(logger, logging.ERROR, "Startup task sweep failed", error=str(exc))

    yield

    # Cleanup SQLAlchemy engine
    await close_db()


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

from app.services.storage_service import storage
from fastapi.responses import RedirectResponse, FileResponse

@app.get("/api/covers/{book_id}.jpg")
async def get_cover(book_id: str):
    local_path = settings.covers_dir / f"{book_id}.jpg"
    if local_path.exists():
        return FileResponse(local_path)
    
    # Try storage
    remote_path = f"covers/{book_id}.jpg"
    if storage.exists(remote_path):
        # We can either download and serve, or redirect to GCS
        if settings.storage_backend == "gcs":
            return RedirectResponse(storage.get_public_url(remote_path))
        else:
            await storage.download_file(remote_path, local_path)
            return FileResponse(local_path)
    
    raise HTTPException(status_code=404, detail="Cover not found")

# Keep the mount for legacy/local if needed, but the route above takes precedence
app.mount("/api/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
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
    from app.db.session import get_engine
    from sqlalchemy import text
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Database not ready: {exc}")
    return {"status": "ready"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
