import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db import session as db_session
from app.db.repositories.books import BooksRepository
from app.queue import enqueue_pdf_processing

logger = logging.getLogger("arq.worker")

async def rescue_stale_jobs(ctx):
    """
    CRON Task: Find books stuck in 'processing' state for longer than the timeout
    and re-queue them.
    """
    logger.info("🕵️ Watchdog: Checking for stale jobs...")
    
    # Timeout logic: If a book has been "processing" for longer than (TIMEOUT + 5 mins), it's stale.
    # We add a buffer to ensure we don't race with a legitimate long-running job that is about to finish.
    timeout_seconds = settings.queue_job_timeout
    buffer_seconds = 300 
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds + buffer_seconds)
    
    # Provide timezone-naive datetime if DB expects it (SQLAlchemy usually deals with naive UTC or timezone-aware depending on config)
    # Assuming the DB stores timestamps as timezone-naive UTC (common in this codebase based on previous files)
    cutoff_time_naive = cutoff_time.replace(tzinfo=None)

    async with db_session.async_session_factory() as session:
        repo = BooksRepository(session)
        # Use the naive time for query comparison
        stale_books = await repo.find_stale_processing_books(cutoff_time_naive)
        
        if not stale_books:
            logger.info("✅ Watchdog: No stale jobs found.")
            return

        logger.warning(f"⚠️ Watchdog: Found {len(stale_books)} stale books stuck in processing. Attempting rescue...")
        
        for book in stale_books:
            logger.info(f"🚑 Rescuing book {book.id} (stuck since {book.last_updated})...")
            
            try:
                # Re-queue the book for processing
                # This will create a new job in Redis and reset the job status in DB
                await enqueue_pdf_processing(book.id, reason="watchdog_rescue")
                logger.info(f"✅ Book {book.id} successfully re-queued.")
            except Exception as e:
                logger.error(f"❌ Failed to rescue book {book.id}: {e}")
