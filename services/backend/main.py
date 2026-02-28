from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.endpoints import ai, auth, books, chat, users, system_configs, stats, contact
from app.core.config import settings
from app.db.session import init_db, close_db  # SQLAlchemy session management
from app.core.i18n import I18n, set_current_lang

from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json, request_id_var
from auth.jwt_handler import validate_jwt_secret

import os as _os
# Locales live next to main.py in services/backend/, not in packages/backend-core
I18n._locales_dir = _os.path.join(_os.path.dirname(__file__), "locales")


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    configure_langchain()
    I18n.load_translations()
    
    # Validate JWT secret key at startup
    logger = logging.getLogger("app.startup")
    try:
        validate_jwt_secret()
    except ValueError as e:
        log_json(logger, logging.WARNING, "JWT secret validation warning", error=str(e))
        log_json(logger, logging.WARNING, "Authentication features will not work properly")

    # Initialize SQLAlchemy (replaces db_manager.connect_to_storage())
    await init_db()

    # Seed system configurations
    try:
        from app.db.seeds import seed_system_configs
        from app.db import session as db_session
        async with db_session.async_session_factory() as session:
            await seed_system_configs(session)
    except Exception as exc:
        logger = logging.getLogger("app.startup")
        log_json(logger, logging.ERROR, "System config seeding failed", error=str(exc))
    
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

@app.middleware("http")
async def add_language_header(request: Request, call_next):
    lang = request.headers.get("Accept-Language", "ug").split(",")[0].split("-")[0]
    if lang not in ["ug", "en"]:
        lang = "ug"
    set_current_lang(lang)
    response = await call_next(request)
    return response

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
async def get_cover(book_id: str, request: Request):
    local_path = settings.covers_dir / f"{book_id}.jpg"
    if local_path.exists():
        return FileResponse(local_path)
    
    # Try storage
    remote_path = f"covers/{book_id}.jpg"
    if storage.exists(remote_path):
        # We can either download and serve, or redirect to GCS
        if settings.storage_backend == "gcs":
            url = storage.get_public_url(remote_path)
            # Pass through query parameters (like ?v=...) to bypass GCS/browser cache
            if request.query_params:
                url += f"?{request.query_params}"
            return RedirectResponse(url)
        else:
            await storage.download_file(remote_path, local_path)
            return FileResponse(local_path)
    
    raise HTTPException(status_code=404, detail=t("errors.cover_not_found"))

# Keep the mount for legacy/local if needed, but the route above takes precedence
app.mount("/api/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(books.router, prefix="/api/books", tags=["books"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(ai.router, prefix="/api/ai", tags=["ai"])
app.include_router(system_configs.router, prefix="/api/system-configs", tags=["system-configs"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(contact.router, prefix="/api/contact", tags=["contact"])


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
