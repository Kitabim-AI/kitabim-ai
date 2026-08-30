from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncSession
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from api.endpoints import (
    ai_router,
    auth_router,
    books_router,
    chat_router,
    users_router,
    system_configs_router,
    stats_router,
    contact_router,
    spell_check_router,
    auto_correct_rules_router,
    dictionary_router,
    words_router,
    synonyms_router,
    history_dictionary_router,
    names_dictionary_router,
    english_uyghur_router,
    share_router,
    cache_router,
    questions_router,
    proverbs_router,
    quran_router,
    graph_admin_router,
    admin_history_dictionary_router,
)
from app.core.config import settings
from app.db.session import (
    init_db,
    close_db,
    get_session,
)  # SQLAlchemy session management
from app.core.i18n import I18n, set_current_lang, t

from app.utils.observability import configure_logging, log_json, request_id_var
from auth.jwt_handler import validate_jwt_secret

from app.services.storage_service import storage
from fastapi.responses import RedirectResponse, FileResponse, JSONResponse

import os as _os

# Locales live next to main.py in services/backend/, not in packages/backend-core
I18n._locales_dir = _os.path.join(_os.path.dirname(__file__), "locales")


async def redis_pubsub_listener():
    """Background task to listen to Redis Pub/Sub invalidation channel."""
    import asyncio
    from app.services.cache_service import cache_service
    from auth.dependencies import user_lru_cache

    logger = logging.getLogger("app.pubsub")
    logger.info("Starting Redis Pub/Sub user invalidation listener...")

    while True:
        try:
            client = await cache_service.get_client()
            if not client:
                await asyncio.sleep(5)
                continue

            pubsub = client.pubsub()
            await pubsub.subscribe("user_invalidation")

            async for message in pubsub.listen():
                if message and message.get("type") == "message":
                    try:
                        data = message["data"]
                        user_id = (
                            data.decode("utf-8")
                            if isinstance(data, bytes)
                            else str(data)
                        )
                        logger.info(
                            f"Received user invalidation event for user_id: {user_id}"
                        )
                        if user_id == "__ALL__":
                            user_lru_cache.clear()
                            logger.info("Cleared entire local user LRU cache")
                        else:
                            evicted = user_lru_cache.delete(user_id)
                            logger.info(
                                f"Evicted user_id {user_id} from local user LRU cache: {evicted}"
                            )
                    except Exception as ex:
                        logger.error(f"Error processing pubsub message: {ex}")
        except asyncio.CancelledError:
            logger.info("Redis Pub/Sub listener task cancelled.")
            break
        except Exception as e:
            logger.error(f"Redis Pub/Sub listener error: {e}. Retrying in 5 seconds...")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    I18n.load_translations()

    # Validate JWT secret key at startup (fail fast in production)
    logger = logging.getLogger("app.startup")
    try:
        validate_jwt_secret()
    except ValueError as e:
        log_json(logger, logging.ERROR, "JWT secret validation failed", error=str(e))
        if settings.environment == "production":
            raise RuntimeError(
                f"Cannot start in production without valid JWT secret: {e}"
            )
        else:
            log_json(
                logger,
                logging.WARNING,
                "Authentication features will not work properly",
            )

    # Initialize SQLAlchemy (replaces db_manager.connect_to_storage())
    await init_db()

    # Seed system configurations & load runtime log_level
    try:
        from app.db.seeds import seed_system_configs
        from app.db import session as db_session
        from app.db.repositories.system_configs_repository import (
            SystemConfigsRepository,
        )

        async with db_session.async_session_factory() as session:
            await seed_system_configs(session)
            repo = SystemConfigsRepository(session)
            log_level_val = await repo.get_value("sys_log_level", settings.log_level)
            if log_level_val:
                new_level = getattr(logging, log_level_val.upper(), logging.INFO)
                logging.getLogger().setLevel(new_level)
                log_json(
                    logger,
                    logging.INFO,
                    f"Applied system_configs log_level: {log_level_val.upper()}",
                )
    except Exception as exc:
        logger = logging.getLogger("app.startup")
        log_json(logger, logging.ERROR, "System config seeding failed", error=str(exc))

    # Initialize ADK DatabaseSessionService for conversation persistence
    try:
        from google.adk.sessions import DatabaseSessionService
        from app.db.session import engine

        adk_session_service = DatabaseSessionService(db_engine=engine)
        await adk_session_service.prepare_tables()
        app.state.adk_session_service = adk_session_service
        log_json(
            logger, logging.INFO, "ADK DatabaseSessionService initialized successfully"
        )
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "ADK DatabaseSessionService initialization skipped/failed",
            error=str(exc),
        )
        app.state.adk_session_service = None

    # Start Redis Pub/Sub background listener task
    import asyncio

    listener_task = asyncio.create_task(redis_pubsub_listener())

    yield

    # Cancel listener task on shutdown
    listener_task.cancel()
    try:
        await listener_task
    except asyncio.CancelledError:
        pass

    # Cleanup SQLAlchemy engine
    await close_db()


app = FastAPI(title=settings.project_name, lifespan=lifespan)

# Trust X-Forwarded-For from Nginx proxy (localhost) so request.client.host
# returns the real client IP everywhere, including slowapi rate limiting.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["127.0.0.1", "::1"])


# Global exception handler to capture and log any unhandled exceptions
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import traceback
    from fastapi.responses import JSONResponse

    logger = logging.getLogger("app.error")
    log_json(
        logger,
        logging.ERROR,
        "Unhandled server exception",
        method=request.method,
        path=request.url.path,
        error=str(exc),
        traceback=traceback.format_exc(),
    )

    # Return error detail in development/editor environments
    # In production, we keep it generic to avoid leaking system info
    detail = (
        str(exc) if settings.environment != "production" else "Internal Server Error"
    )
    return JSONResponse(status_code=500, content={"detail": detail})


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def add_language_header(request: Request, call_next):
    lang = request.headers.get("Accept-Language", "ug").split(",")[0].split("-")[0]
    if lang not in ["ug", "en"]:
        lang = "ug"
    set_current_lang(lang)
    response = await call_next(request)
    return response


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Add security headers to all responses"""
    response = await call_next(request)

    # Security headers — always set for defense-in-depth
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"

    # X-XSS-Protection is deprecated and can trigger "Reduced Protections"
    # warnings in Safari 17+. Modern browsers use CSP for this purpose.
    # response.headers["X-XSS-Protection"] = "1; mode=block" (REMOVED)

    # Permissions-Policy to restrict sensitive features
    response.headers["Permissions-Policy"] = (
        "camera=(), microphone=(), geolocation=(), interest-cohort=()"
    )

    if settings.environment == "production":
        # HSTS set here for backends not behind Nginx (e.g. direct access).
        # Nginx also sets it — duplicate headers are harmless; missing it is not.
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )

    # Swagger UI loads assets from cdn.jsdelivr.net — skip strict CSP for docs paths.
    if request.url.path not in ("/docs", "/redoc", "/openapi.json"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://accounts.google.com; "
            "style-src 'self' 'unsafe-inline' https:; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https:; "
            "connect-src 'self' https://accounts.google.com https://graph.facebook.com; "
            "frame-src 'self' https://accounts.google.com; "
            "object-src 'none';"
        )
    return response


# Request context & ID middleware - REGISTERED LAST to be OUTERMOST
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
    except Exception as exc:
        import traceback

        log_json(
            logger,
            logging.ERROR,
            "Request failed with unhandled exception",
            method=request.method,
            path=request.url.path,
            error=str(exc),
            traceback=traceback.format_exc(),
        )
        raise  # Re-raise to let the global exception handler deal with it
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


# Security/Noise reduction middleware - MUST be outer than request_id to block noise
@app.middleware("http")
async def block_noisy_requests(request: Request, call_next):
    """
    Blocks common crawler/scanner paths to reduce noise in logs and save resources.
    Returns 404 for known forbidden prefixes or specific noisy paths.
    """
    path = request.url.path

    # Check prefixes
    blocked_prefixes = [
        p.strip() for p in settings.security_block_prefixes.split(",") if p.strip()
    ]
    for prefix in blocked_prefixes:
        if path.startswith(prefix):
            # We log it as a scan attempt at WARNING level, but return early
            # so the main request-id middleware doesn't log it as a normal request.
            logger = logging.getLogger("app.security")
            log_json(
                logger,
                logging.WARNING,
                "Crawler/Scanner path blocked",
                method=request.method,
                path=path,
                ip=request.client.host if request.client else "unknown",
            )
            return JSONResponse(status_code=404, content={"detail": "Not Found"})

    # Check exact paths
    blocked_paths = [
        p.strip() for p in settings.security_block_paths.split(",") if p.strip()
    ]
    if path in blocked_paths:
        logger = logging.getLogger("app.security")
        log_json(
            logger,
            logging.WARNING,
            "Crawler/Scanner path blocked",
            method=request.method,
            path=path,
            ip=request.client.host if request.client else "unknown",
        )
        return JSONResponse(status_code=404, content={"detail": "Not Found"})

    return await call_next(request)


# Enforce App Client ID for non-GET requests to ensure they come from our app
@app.middleware("http")
async def enforce_app_id(request: Request, call_next):
    """
    Enforces a shared secret header (X-Kitabim-App-Id) for all non-GET/OPTIONS API requests.
    This identifies the request as coming from our authorized application client.
    """
    # Only enforce for /api/ paths
    if not request.url.path.startswith("/api/"):
        return await call_next(request)

    # Exclude safe methods to allow browser image loading and CORS preflights
    if request.method in ("GET", "OPTIONS", "HEAD"):
        return await call_next(request)

    # Exempt auth bootstrap endpoints — they are protected by their own mechanisms
    # (refresh cookie, OAuth state) and must work before the client knows the app ID.
    exempt_paths = (
        "/api/auth/refresh",
        "/api/auth/google/",
        "/api/auth/facebook/",
        "/api/auth/twitter/",
    )
    if any(request.url.path.startswith(p) for p in exempt_paths):
        return await call_next(request)

    # Check for the Application ID header
    app_id = request.headers.get("X-Kitabim-App-Id")

    if app_id != settings.security_app_id:
        logger = logging.getLogger("app.security")
        log_json(
            logger,
            logging.WARNING,
            "Unauthorized client: Missing or invalid App ID",
            method=request.method,
            path=request.url.path,
            ip=request.client.host if request.client else "unknown",
        )
        return JSONResponse(
            status_code=403,
            content={
                "detail": "Unauthorized: Request must originate from the authorized application"
            },
        )

    return await call_next(request)


# CORS Configuration - Allow only specific origins
allowed_origins = [
    origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept-Language", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


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
            # Pass through only the cache-busting 'v' param — never forward arbitrary params
            v = request.query_params.get("v")
            if v:
                from urllib.parse import urlencode

                url += f"?{urlencode({'v': v})}"
            return RedirectResponse(url)
        else:
            await storage.download_file(remote_path, local_path)
            return FileResponse(local_path)

    raise HTTPException(status_code=404, detail=t("errors.cover_not_found"))


# Keep the mount for legacy/local if needed, but the route above takes precedence
app.mount("/api/covers", StaticFiles(directory=str(settings.covers_dir)), name="covers")

app.include_router(auth_router.router, prefix="/api/auth", tags=["auth"])
app.include_router(users_router.router, prefix="/api/users", tags=["users"])
app.include_router(books_router.router, prefix="/api/books", tags=["books"])
app.include_router(chat_router.router, prefix="/api/chat", tags=["chat"])
app.include_router(ai_router.router, prefix="/api/ai", tags=["ai"])
app.include_router(
    system_configs_router.router, prefix="/api/system-configs", tags=["system-configs"]
)
app.include_router(stats_router.router, prefix="/api/stats", tags=["stats"])
app.include_router(contact_router.router, prefix="/api/contact", tags=["contact"])
app.include_router(spell_check_router.router, prefix="/api/books", tags=["spell-check"])
app.include_router(
    auto_correct_rules_router.router, prefix="/api", tags=["spell-check"]
)
app.include_router(dictionary_router.router, prefix="/api", tags=["dictionary"])
app.include_router(words_router.router, prefix="/api", tags=["words"])
app.include_router(synonyms_router.router, prefix="/api", tags=["synonyms"])
app.include_router(
    history_dictionary_router.router, prefix="/api", tags=["history-dictionary"]
)
app.include_router(
    names_dictionary_router.router, prefix="/api", tags=["names-dictionary"]
)
app.include_router(
    english_uyghur_router.router, prefix="/api", tags=["english-uyghur-dictionary"]
)
app.include_router(share_router.router, prefix="/api/share", tags=["share"])
app.include_router(cache_router.router, prefix="/api/cache", tags=["cache"])
app.include_router(questions_router.router, prefix="/api/questions", tags=["questions"])
app.include_router(proverbs_router.router, prefix="/api", tags=["proverbs"])
app.include_router(quran_router.router, prefix="/api", tags=["quran"])
app.include_router(
    admin_history_dictionary_router.router,
    prefix="/api/admin",
    tags=["admin-history-dictionary"],
)
app.include_router(
    graph_admin_router.router, prefix="/api/admin/graph", tags=["graph-admin"]
)


@app.get("/api/config")
async def get_public_config(session: AsyncSession = Depends(get_session)):
    """Public endpoint — returns public configuration like collectionPageSize."""
    from app.db.repositories.system_configs_repository import SystemConfigsRepository

    repo = SystemConfigsRepository(session)
    collection_page_size_str = await repo.get_value("sys_collection_page_size", "40")
    try:
        collection_page_size = int(collection_page_size_str)
    except (ValueError, TypeError):
        collection_page_size = 40

    return {
        "collectionPageSize": collection_page_size,
    }


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
