#!/usr/bin/env python3
"""Test the new watchdog behavior"""
import asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, func
from app.db.models import Book, Job
from app.core.config import settings

async def test_watchdog_logic():
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        print("=" * 80)
        print("🧪 TESTING NEW WATCHDOG LOGIC")
        print("=" * 80)

        # Get pending books with their jobs
        pending_cutoff = datetime.utcnow() - timedelta(minutes=30)

        result = await session.execute(
            select(Book.id, Book.title, Book.status, Book.last_updated)
            .where(Book.status == "pending")
            .where(Book.last_updated < pending_cutoff)
            .limit(10)
        )
        pending_books = result.all()

        print(f"\n📋 Found {len(pending_books)} stale pending books")
        print("\nSimulating watchdog decision for each book:\n")

        would_enqueue = 0
        would_skip = 0

        for book_id, title, status, last_updated in pending_books:
            job_key = f"process_pdf:{book_id}"

            # Check for existing job
            job_result = await session.execute(
                select(Job).where(Job.job_key == job_key)
            )
            job = job_result.scalar_one_or_none()

            print(f"📖 {title[:40]}")
            print(f"   ID: {book_id}")

            if job:
                job_age_minutes = (datetime.now(timezone.utc) - job.created_at.replace(tzinfo=timezone.utc)).total_seconds() / 60

                if job_age_minutes < 5 and job.status in ("queued", "in_progress"):
                    print(f"   ⏸️  SKIP: Job recently created ({job_age_minutes:.1f}m ago, status={job.status})")
                    would_skip += 1
                elif job.status == "skipped" and job_age_minutes < 5:
                    print(f"   ⏸️  SKIP: Job skipped recently ({job_age_minutes:.1f}m ago)")
                    would_skip += 1
                elif job.status == "skipped" and job_age_minutes >= 5:
                    print(f"   ✅ ENQUEUE: Job skipped {job_age_minutes:.1f}m ago (circuit breaker recovered)")
                    would_enqueue += 1
                elif job.status in ("completed", "failed"):
                    print(f"   ✅ ENQUEUE: Job in terminal state ({job.status})")
                    would_enqueue += 1
                else:
                    print(f"   ⚠️  UNKNOWN: status={job.status}, age={job_age_minutes:.1f}m")
            else:
                print(f"   ✅ ENQUEUE: No existing job")
                would_enqueue += 1

            print()

        print("=" * 80)
        print("📊 SUMMARY")
        print("=" * 80)
        print(f"  Would enqueue: {would_enqueue} books")
        print(f"  Would skip:    {would_skip} books")
        print(f"\n  Before fix: All {len(pending_books)} would be enqueued every 15 min ♾️")
        print(f"  After fix:  Only {would_enqueue} enqueued (prevents duplicates) ✅")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_watchdog_logic())
