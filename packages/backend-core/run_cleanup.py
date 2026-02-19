#!/usr/bin/env python3
"""Clean up old skipped jobs from the database"""
import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Job
from app.core.config import settings

async def cleanup():
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        print("=" * 80)
        print("🧹 CLEANING UP OLD SKIPPED JOBS")
        print("=" * 80)

        cutoff = datetime.utcnow() - timedelta(days=1)

        # Show what we're about to delete
        print(f"\n📋 Jobs to be deleted (skipped and older than 1 day):\n")
        result = await session.execute(
            select(Job.job_key, Job.status, Job.created_at, Job.last_error)
            .where(Job.status == "skipped")
            .where(Job.created_at < cutoff)
            .order_by(Job.created_at)
            .limit(20)
        )
        jobs_to_delete = result.all()

        if not jobs_to_delete:
            print("   ✅ No old skipped jobs found!")
            await engine.dispose()
            return

        for job_key, status, created_at, last_error in jobs_to_delete:
            age_days = (datetime.utcnow() - created_at.replace(tzinfo=None)).days
            print(f"   • {job_key[:40]:<40} (created {age_days}d ago)")
            if last_error:
                print(f"     Error: {last_error[:60]}")

        # Count total
        count_result = await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "skipped")
            .where(Job.created_at < cutoff)
        )
        total_count = count_result.scalar()

        if len(jobs_to_delete) < total_count:
            print(f"   ... and {total_count - len(jobs_to_delete)} more")

        print(f"\n📊 Total jobs to delete: {total_count}")

        # Confirm
        response = input("\n⚠️  Delete these jobs? (yes/no): ")
        if response.lower() != "yes":
            print("❌ Cleanup cancelled")
            await engine.dispose()
            return

        # Delete them
        await session.execute(
            delete(Job)
            .where(Job.status == "skipped")
            .where(Job.created_at < cutoff)
        )
        await session.commit()

        print(f"\n✅ Deleted {total_count} old skipped jobs!")

        # Show remaining jobs
        print("\n" + "=" * 80)
        print("📊 REMAINING JOBS BY STATUS")
        print("=" * 80)
        result = await session.execute(
            select(Job.status, func.count())
            .group_by(Job.status)
            .order_by(Job.status)
        )

        for status, count in result:
            print(f"  {status or 'NULL':15s}: {count:5d}")

        print("\n" + "=" * 80)
        print("💡 NEXT STEPS")
        print("=" * 80)
        print("  1. The watchdog will create fresh jobs for pending books on next run")
        print("  2. Restart the worker to trigger the watchdog immediately")
        print("  3. Monitor logs for '⏸️  Skipping' messages (indicates fix is working)")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(cleanup())
