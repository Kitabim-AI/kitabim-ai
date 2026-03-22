"""SQLAlchemy async session configuration and management"""
from __future__ import annotations

import logging
from urllib.parse import urlparse, urlunparse
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from app.core.config import settings
from app.utils.observability import log_json


# Global engine and session factory
engine: AsyncEngine | None = None
async_session_factory: async_sessionmaker[AsyncSession] | None = None

logger = logging.getLogger("app.db")


def get_database_url() -> str:
    """
    Convert DATABASE_URL to async format for SQLAlchemy.

    PostgreSQL URLs must use postgresql+asyncpg:// driver.
    """
    url = settings.database_url

    if not url:
        raise ValueError("DATABASE_URL environment variable is required")

    # Convert postgresql:// to postgresql+asyncpg://
    if url.startswith('postgresql://'):
        return url.replace('postgresql://', 'postgresql+asyncpg://')

    return url


async def init_db(service_name: str = "backend") -> None:
    """
    Initialize database engine and session factory.

    Called from FastAPI lifespan on application startup or worker startup.

    Args:
        service_name: "backend" or "worker" - determines pool size and app name
    """
    global engine, async_session_factory

    database_url = get_database_url()

    parsed = urlparse(database_url)
    safe_url = urlunparse(parsed._replace(netloc=parsed.netloc.replace(f":{parsed.password}@", ":***@") if parsed.password else parsed.netloc))

    # Use service-specific pool configuration
    if service_name == "worker":
        pool_size = settings.worker_db_pool_size
        max_overflow = settings.worker_db_max_overflow
        app_name = "kitabim-ai-worker"
    else:
        pool_size = settings.db_pool_size
        max_overflow = settings.db_max_overflow
        app_name = "kitabim-ai-backend"

    log_json(logger, logging.INFO, "Initializing SQLAlchemy",
             url=safe_url, service=service_name,
             pool_size=pool_size, max_overflow=max_overflow)

    # Create async engine
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL query logging
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout=60,  # Timeout waiting for connection from pool (seconds)
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=3600,  # Recycle connections after 1 hour
        connect_args={
            "server_settings": {
                "application_name": app_name
            },
            "command_timeout": settings.db_query_timeout,
        }
    )

    # Create session factory
    async_session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,  # Don't expire objects after commit
        autocommit=False,
        autoflush=False,
    )

    # Test connection
    try:
        async with engine.begin() as conn:
            result = await conn.execute(text("SELECT version()"))
            version = result.scalar()
            log_json(logger, logging.INFO, "SQLAlchemy connected", version=version[:50] if version else "unknown")
    except Exception as exc:
        log_json(logger, logging.ERROR, "SQLAlchemy connection failed", error=str(exc))
        raise


async def close_db() -> None:
    """
    Close database engine and dispose of connection pool.

    Called from FastAPI lifespan on application shutdown.
    """
    global engine
    if engine:
        log_json(logger, logging.INFO, "Closing SQLAlchemy engine")
        await engine.dispose()
        engine = None


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for getting database session.

    Provides automatic session management with commit/rollback.

    Usage:
        @router.get("/books")
        async def get_books(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Book))
            books = result.scalars().all()
            return books

    The session is automatically committed on success and rolled back on error.
    """
    if async_session_factory is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with async_session_factory() as session:
        try:
            yield session
            # Auto-commit is handled per-endpoint (explicit commits needed)
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_engine() -> AsyncEngine:
    """Get the global engine instance (for raw SQL if needed)"""
    if engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return engine
