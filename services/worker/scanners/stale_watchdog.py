"""
Stale Watchdog — resets pages stuck in_progress back to idle.

Handles crashed jobs or pods that were killed mid-processing.
One rule covers all pipeline steps. Runs every 30 minutes.
"""
from __future__ import annotations
 
import logging
from datetime import datetime, timedelta, timezone
 
from sqlalchemy import update, func, select
 
from app.db import session as db_session
from app.db.models import Book, Page
from app.services.book_milestone_service import BookMilestoneService
from app.utils.observability import log_json
from app.utils.circuit_breaker import get_redis
 
logger = logging.getLogger("app.worker.stale_watchdog")
 
STALE_THRESHOLD_MINUTES = 30
 
 
async def run_stale_watchdog(ctx) -> None:
    now_utc = datetime.now(timezone.utc)
    dead_worker_threshold = now_utc - timedelta(minutes=2)
    max_duration_threshold = now_utc - timedelta(minutes=STALE_THRESHOLD_MINUTES)
    now = func.now()
 
    async with db_session.async_session_factory() as session:
        from sqlalchemy import or_, case
        
        # Build conditions and update values dynamically based on feature flags
        where_conditions = [
            Page.ocr_milestone == "in_progress",
            Page.chunking_milestone == "in_progress",
            Page.embedding_milestone == "in_progress",
            Page.spell_check_milestone == "in_progress",
            Page.milestone == "in_progress"  # Legacy support
        ]
        
        # Load in-progress pages
        stmt = (
            select(Page.id, Page.book_id, Page.worker_id, Page.claimed_at)
            .where(or_(*where_conditions))
        )
        result = await session.execute(stmt)
        rows = result.fetchall()
        
        # Fetch active worker heartbeats from Redis
        redis = ctx.get("redis") or get_redis()
        keys = []
        cursor = 0
        while True:
            cursor, match_keys = await redis.scan(cursor, match="worker:heartbeat:*", count=100)
            keys.extend(match_keys)
            if cursor == 0:
                break
                
        active_workers = set()
        for k in keys:
            key_str = k.decode() if isinstance(k, bytes) else str(k)
            active_workers.add(key_str.split(":")[-1])
            
        stale_page_ids = []
        for pid, book_id, worker_id, claimed_at in rows:
            c_at = claimed_at
            if c_at and c_at.tzinfo is None:
                c_at = c_at.replace(tzinfo=timezone.utc)
                
            is_stale = False
            if not worker_id or worker_id == "unknown":
                if not c_at or c_at < max_duration_threshold:
                    is_stale = True
            elif worker_id not in active_workers:
                if not c_at or c_at < dead_worker_threshold:
                    is_stale = True
            else:
                if c_at and c_at < max_duration_threshold:
                    is_stale = True
                    
            if is_stale:
                stale_page_ids.append(pid)
 
        reset_ids = []
        reset_book_ids_from_pages = []
 
        if stale_page_ids:
            update_values = {
                "ocr_milestone": case((Page.ocr_milestone == "in_progress", "idle"), else_=Page.ocr_milestone),
                "chunking_milestone": case((Page.chunking_milestone == "in_progress", "idle"), else_=Page.chunking_milestone),
                "embedding_milestone": case((Page.embedding_milestone == "in_progress", "idle"), else_=Page.embedding_milestone),
                "spell_check_milestone": case((Page.spell_check_milestone == "in_progress", "idle"), else_=Page.spell_check_milestone),
                "milestone": case((Page.milestone == "in_progress", "idle"), else_=Page.milestone),
                "worker_id": None,
                "claimed_at": None,
                "last_updated": now
            }
 
            update_stmt = (
                update(Page)
                .where(Page.id.in_(stale_page_ids))
                .values(**update_values)
                .returning(Page.id, Page.book_id)
            )
            update_res = await session.execute(update_stmt)
            update_rows = update_res.fetchall()
            reset_ids = [row[0] for row in update_rows]
            reset_book_ids_from_pages = list(set(row[1] for row in update_rows))
 
        if reset_book_ids_from_pages:
            for book_id in reset_book_ids_from_pages:
                await BookMilestoneService.update_book_milestones(session, book_id)
 
        # Reset stale books stuck in graph_milestone == "in_progress" for > 1 hour
        book_threshold = datetime.now(timezone.utc) - timedelta(hours=1)
        book_stmt = (
            update(Book)
            .where(
                Book.graph_milestone == "in_progress",
                Book.last_updated < book_threshold
            )
            .values(
                graph_milestone="idle",
                last_updated=now
            )
            .returning(Book.id)
        )
        book_result = await session.execute(book_stmt)
        reset_book_ids = [row[0] for row in book_result.fetchall()]
        
        await session.commit()
 
    if reset_ids:
        log_json(logger, logging.INFO, "stale watchdog reset pages", count=len(reset_ids))
    else:
        log_json(logger, logging.DEBUG, "stale watchdog: no stale pages found")
 
    if reset_book_ids:
        log_json(logger, logging.INFO, "stale watchdog reset books graph milestone", count=len(reset_book_ids))
    else:
        log_json(logger, logging.DEBUG, "stale watchdog: no stale books found")


