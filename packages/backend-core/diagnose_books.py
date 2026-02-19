#!/usr/bin/env python3
"""Diagnostic script to identify books being re-queued by the watchdog"""
import asyncio
import sys
from datetime import datetime, timedelta
from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Book
from app.core.config import settings

async def diagnose():
    # Create engine directly with asyncpg driver
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        print("=" * 80)
        print("📊 BOOK STATUS OVERVIEW")
        print("=" * 80)

        # Overall status distribution
        stmt = select(Book.status, func.count()).group_by(Book.status)
        result = await session.execute(stmt)
        total = 0
        for status, count in result:
            print(f"  {status:15s}: {count:5d}")
            total += count
        print(f"  {'TOTAL':15s}: {total:5d}")

        print("\n" + "=" * 80)
        print("🔍 STALE BOOKS (candidates for watchdog rescue)")
        print("=" * 80)

        # Stale pending books (>30 min old)
        pending_cutoff = datetime.utcnow() - timedelta(minutes=30)
        stmt_pending = select(Book).where(
            and_(
                Book.status == "pending",
                Book.last_updated < pending_cutoff
            )
        ).order_by(Book.last_updated)

        result_pending = await session.execute(stmt_pending)
        pending_books = result_pending.scalars().all()

        print(f"\n📋 Pending books (>30 min old): {len(pending_books)}")
        if pending_books:
            print("\n  Book ID      | Last Updated        | Title")
            print("  " + "-" * 76)
            for book in pending_books[:10]:  # Show first 10
                title = (book.title or "Untitled")[:40]
                print(f"  {book.id:12s} | {book.last_updated} | {title}")
            if len(pending_books) > 10:
                print(f"  ... and {len(pending_books) - 10} more")

        # Stale processing books (>2h + 5min old)
        timeout_seconds = settings.queue_job_timeout  # 7200 = 2 hours
        buffer_seconds = 300  # 5 minutes
        processing_cutoff = datetime.utcnow() - timedelta(seconds=timeout_seconds + buffer_seconds)

        stmt_processing = select(Book).where(
            and_(
                Book.status == "processing",
                Book.last_updated < processing_cutoff
            )
        ).order_by(Book.last_updated)

        result_processing = await session.execute(stmt_processing)
        processing_books = result_processing.scalars().all()

        print(f"\n⚙️  Processing books (>2h old): {len(processing_books)}")
        if processing_books:
            print("\n  Book ID      | Last Updated        | Processing Step | Title")
            print("  " + "-" * 76)
            for book in processing_books[:10]:  # Show first 10
                title = (book.title or "Untitled")[:30]
                step = (book.processing_step or "unknown")[:12]
                print(f"  {book.id:12s} | {book.last_updated} | {step:15s} | {title}")
            if len(processing_books) > 10:
                print(f"  ... and {len(processing_books) - 10} more")

        print("\n" + "=" * 80)
        print("📈 SUMMARY")
        print("=" * 80)
        total_stale = len(pending_books) + len(processing_books)
        print(f"  Total stale books that will be re-queued: {total_stale}")
        print(f"  Worker concurrency (max_jobs):            {settings.queue_max_jobs}")

        if total_stale > settings.queue_max_jobs:
            queue_time = (total_stale / settings.queue_max_jobs) * 2  # Rough estimate at 2s per job
            print(f"  Estimated time to process all:            ~{queue_time:.0f} seconds")

        print("\n" + "=" * 80)
        print("💡 RECOMMENDATIONS")
        print("=" * 80)

        if total_stale > 20:
            print("  ⚠️  You have many stale books!")
            print("  Consider:")
            print("    1. Increase QUEUE_MAX_JOBS from 2 to 8-10")
            print("    2. Clean up pending books that don't need processing:")
            print("       UPDATE books SET status='error' WHERE status='pending' AND last_updated < NOW() - INTERVAL '1 day';")

        if pending_books and len(pending_books) > 5:
            print(f"\n  📋 {len(pending_books)} pending books will be re-queued every 15 minutes")
            print("     Check why they're stuck in pending (circuit breaker? missing dependencies?)")

        if processing_books and len(processing_books) > 0:
            print(f"\n  ⚙️  {len(processing_books)} books stuck in processing")
            print("     These likely represent interrupted/failed jobs")

    await engine.dispose()

if __name__ == "__main__":
    try:
        asyncio.run(diagnose())
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
