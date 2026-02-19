#!/usr/bin/env python3
"""Clean up all queued jobs from database and Redis"""
import asyncio
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db.models import Job
from app.core.config import settings
from arq import create_pool
from arq.connections import RedisSettings

async def cleanup_queued():
    # Setup database connection
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    print("=" * 80)
    print("🧹 CLEANING UP QUEUED JOBS")
    print("=" * 80)

    async with async_session_factory() as session:
        # Show current job status
        print("\n📊 Current Job Status:")
        result = await session.execute(
            select(Job.status, func.count())
            .group_by(Job.status)
            .order_by(Job.status)
        )
        for status, count in result:
            print(f"  {status or 'NULL':15s}: {count:5d}")

        # Count queued jobs
        count_result = await session.execute(
            select(func.count())
            .select_from(Job)
            .where(Job.status == "queued")
        )
        queued_count = count_result.scalar()

        if queued_count == 0:
            print("\n✅ No queued jobs in database")
        else:
            print(f"\n⚠️  Found {queued_count} queued jobs in database")

            # Show some examples
            result = await session.execute(
                select(Job.job_key, Job.created_at)
                .where(Job.status == "queued")
                .order_by(Job.created_at.desc())
                .limit(10)
            )
            jobs = result.all()

            print("\n📋 Sample queued jobs:")
            for job_key, created_at in jobs:
                print(f"  • {job_key} (created {created_at})")

            if queued_count > 10:
                print(f"  ... and {queued_count - 10} more")

            # Confirm deletion
            response = input(f"\n⚠️  Delete all {queued_count} queued jobs from database? (yes/no): ")
            if response.lower() == "yes":
                await session.execute(
                    delete(Job).where(Job.status == "queued")
                )
                await session.commit()
                print(f"✅ Deleted {queued_count} queued jobs from database")
            else:
                print("❌ Database cleanup cancelled")

    # Clean Redis queue
    print("\n" + "=" * 80)
    print("🧹 CHECKING REDIS QUEUE")
    print("=" * 80)

    try:
        redis_settings = RedisSettings.from_dsn(settings.redis_url)
        redis = await create_pool(redis_settings)

        # Get queue length
        queue_length = await redis.llen("arq:queue")
        print(f"\n📊 Redis queue length: {queue_length}")

        if queue_length > 0:
            response = input(f"\n⚠️  Flush entire Redis queue ({queue_length} jobs)? (yes/no): ")
            if response.lower() == "yes":
                # Delete the queue
                await redis.delete("arq:queue")
                print(f"✅ Flushed Redis queue ({queue_length} jobs removed)")
            else:
                print("❌ Redis cleanup cancelled")
        else:
            print("✅ Redis queue is empty")

        await redis.close()
    except Exception as e:
        print(f"⚠️  Could not connect to Redis: {e}")

    await engine.dispose()

    print("\n" + "=" * 80)
    print("✅ CLEANUP COMPLETE")
    print("=" * 80)
    print("\n💡 Next steps:")
    print("  1. Books in 'pending' status will be picked up by watchdog")
    print("  2. Watchdog runs at startup and every 15 minutes")
    print("  3. Fresh jobs will be created as needed")
    print("\n  Run 'python3 diagnose_books.py' to check current state")

if __name__ == "__main__":
    asyncio.run(cleanup_queued())
