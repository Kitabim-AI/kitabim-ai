import logging
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.db import session as db_session
from app.db.repositories.books import BooksRepository
from app.db.repositories.jobs import JobsRepository
from app.queue import enqueue_pdf_processing

logger = logging.getLogger("arq.worker")

async def rescue_stale_jobs(ctx):
    """
    CRON Task: Find books stuck in 'processing' or 'pending' state for longer than the timeout
    and re-queue them.
    """
    logger.info("🕵️ Watchdog: Checking for stale jobs...")

    # Timeout logic: If a book has been "processing" for longer than (TIMEOUT + 5 mins), it's stale.
    # We add a buffer to ensure we don't race with a legitimate long-running job that is about to finish.
    timeout_seconds = settings.queue_job_timeout
    buffer_seconds = 300
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=timeout_seconds + buffer_seconds)

    async with db_session.async_session_factory() as session:
        books_repo = BooksRepository(session)
        jobs_repo = JobsRepository(session)

        # Find stale "processing" books
        stale_processing = await books_repo.find_stale_processing_books(cutoff_time)

        # Find stale "pending" books (e.g., skipped due to circuit breaker)
        # Use a shorter timeout for pending books (30 minutes)
        pending_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        stale_pending = await books_repo.find_stale_pending_books(pending_cutoff)

        stale_books = stale_processing + stale_pending

        if not stale_books:
            logger.info("✅ Watchdog: No stale jobs found.")
            return

        logger.warning(f"⚠️ Watchdog: Found {len(stale_books)} stale books ({len(stale_processing)} processing, {len(stale_pending)} pending). Checking job status...")

        enqueued_count = 0
        skipped_count = 0

        for book in stale_books:
            job_key = f"process_pdf:{book.id}"

            # Check if there's an existing job for this book
            existing_job = await jobs_repo.get_by_key(job_key)

            if existing_job:
                # Calculate how long ago the job was created
                job_age_minutes = (datetime.now(timezone.utc) - existing_job.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60

                # If job is recently created (< 5 minutes), don't re-enqueue yet
                # This prevents spamming the queue with duplicate jobs
                if job_age_minutes < 5 and existing_job.status in ("queued", "in_progress"):
                    logger.info(
                        f"⏸️  Skipping book {book.id}: Job recently created ({job_age_minutes:.1f}m ago) "
                        f"with status '{existing_job.status}'. Waiting for it to be picked up."
                    )
                    skipped_count += 1
                    continue

                # If job is "skipped" due to circuit breaker, check how old it is
                # Only retry after circuit breaker recovery period (30s) + buffer
                if existing_job.status == "skipped":
                    if job_age_minutes < 5:
                        logger.info(
                            f"⏸️  Skipping book {book.id}: Job was skipped recently ({job_age_minutes:.1f}m ago). "
                            f"Waiting for circuit breaker recovery before retry."
                        )
                        skipped_count += 1
                        continue
                    else:
                        # Job was skipped a while ago, circuit breaker likely recovered
                        logger.info(
                            f"🔄 Book {book.id}: Job skipped {job_age_minutes:.1f}m ago. "
                            f"Circuit breaker likely recovered. Will re-enqueue."
                        )

                # If job is in a terminal state (completed, failed), it's safe to retry
                elif existing_job.status in ("completed", "failed"):
                    logger.info(
                        f"🔄 Book {book.id} has {existing_job.status} job. Safe to re-enqueue."
                    )

            # No job exists, or previous job is in terminal state - safe to enqueue
            logger.info(f"🚑 Rescuing book {book.id} (status={book.status}, stuck since {book.last_updated})...")

            try:
                # Re-queue the book for processing
                # This will create a new job in Redis and reset the job status in DB
                await enqueue_pdf_processing(book.id, reason="watchdog_rescue")
                logger.info(f"✅ Book {book.id} successfully re-queued.")
                enqueued_count += 1
            except Exception as e:
                logger.error(f"❌ Failed to rescue book {book.id}: {e}")

        logger.info(
            f"📊 Watchdog summary: {enqueued_count} books re-queued, "
            f"{skipped_count} skipped (waiting for existing job to complete)"
        )
