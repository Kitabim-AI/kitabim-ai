#!/usr/bin/env python3
"""Inspect jobs for pending books"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select, and_
from app.db.models import Job, Book
from app.core.config import settings

async def inspect_jobs():
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        # Get pending books
        result = await session.execute(
            select(Book.id, Book.title)
            .where(Book.status == "pending")
            .limit(10)
        )
        pending_books = result.all()

        print("=" * 80)
        print("🔍 CHECKING JOBS FOR PENDING BOOKS")
        print("=" * 80)

        for book_id, title in pending_books:
            job_key = f"process_pdf:{book_id}"

            # Check if job exists
            result = await session.execute(
                select(Job).where(Job.job_key == job_key)
            )
            job = result.scalar_one_or_none()

            print(f"\n📖 {title[:50]}")
            print(f"   Book ID:  {book_id}")
            print(f"   Job Key:  {job_key}")

            if job:
                print(f"   ✅ Job exists:")
                print(f"      Status:      {job.status}")
                print(f"      Created:     {job.created_at}")
                print(f"      Attempts:    {job.attempts}")
                if job.error:
                    print(f"      Error:       {job.error[:200]}")
                if job.last_error:
                    print(f"      Last Error:  {job.last_error[:200]}")
            else:
                print(f"   ❌ No job found in database")
                print(f"      → Job may have been deleted or never created")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(inspect_jobs())
