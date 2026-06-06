"""
Shared ARQ worker lifecycle hooks.

Imported by services/worker/worker/worker.py.
All job functions live in services/worker/worker/ (scanners and jobs).
"""
from __future__ import annotations

import logging

import asyncio
import socket
import os
import uuid

from app.core.config import settings
from app.db import session as db_session
from app.db.session import init_db, close_db
from app.langchain import configure_langchain
from app.utils.observability import configure_logging, log_json
from app.utils.circuit_breaker import get_redis

logger = logging.getLogger("app.queue")


async def heartbeat_loop(redis_client, worker_id):
    try:
        while True:
            await redis_client.set(f"worker:heartbeat:{worker_id}", "alive", ex=30)
            await asyncio.sleep(10)
    except asyncio.CancelledError:
        try:
            await redis_client.delete(f"worker:heartbeat:{worker_id}")
        except Exception:
            pass
        raise
    except Exception as exc:
        log_json(logger, logging.WARNING, "Error in worker heartbeat loop", error=str(exc))


async def worker_startup(ctx):
    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
    configure_logging(level=log_level)
    configure_langchain()
    await init_db(service_name="worker")

    # Initialize worker_id
    worker_id = f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    ctx["worker_id"] = worker_id
    log_json(logger, logging.INFO, "Worker started", worker_id=worker_id)

    # Start heartbeat task
    redis_client = ctx.get("redis") or get_redis()
    ctx["heartbeat_task"] = asyncio.create_task(heartbeat_loop(redis_client, worker_id))

    try:
        from app.db.seeds import seed_system_configs
        async with db_session.async_session_factory() as session:
            await seed_system_configs(session)
    except Exception as exc:
        log_json(logger, logging.ERROR, "Worker system config seeding failed", error=str(exc))


async def worker_shutdown(ctx):
    # Stop heartbeat task
    task = ctx.get("heartbeat_task")
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Delete heartbeat key
    worker_id = ctx.get("worker_id")
    if worker_id:
        try:
            redis_client = ctx.get("redis") or get_redis()
            await redis_client.delete(f"worker:heartbeat:{worker_id}")
        except Exception as exc:
            log_json(logger, logging.WARNING, "Failed to delete worker heartbeat key", error=str(exc))

    await close_db()
