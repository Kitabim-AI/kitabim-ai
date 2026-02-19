#!/usr/bin/env python3
"""Inspect a specific book to see why it's stuck"""
import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import select
from app.db.models import Book, Page
from app.core.config import settings
import json

async def inspect(book_id: str):
    # Create engine
    db_url = settings.database_url
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(db_url)
    async_session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_factory() as session:
        # Get book
        result = await session.execute(select(Book).where(Book.id == book_id))
        book = result.scalar_one_or_none()

        if not book:
            print(f"Book {book_id} not found")
            return

        print("=" * 80)
        print(f"📖 BOOK: {book.title}")
        print("=" * 80)
        print(f"ID:              {book.id}")
        print(f"Status:          {book.status}")
        print(f"Processing Step: {book.processing_step}")
        print(f"Created:         {book.upload_date}")
        print(f"Last Updated:    {book.last_updated}")
        print(f"Source:          {book.source}")
        print(f"Filename:        {book.file_name}")
        print(f"Total Pages:     {book.total_pages}")

        if book.last_error:
            print(f"\n❌ LAST ERROR:")
            if isinstance(book.last_error, str):
                try:
                    error_obj = json.loads(book.last_error)
                    print(json.dumps(error_obj, indent=2))
                except:
                    print(book.last_error)
            else:
                print(json.dumps(book.last_error, indent=2))

        # Get pages
        result = await session.execute(
            select(Page.status, Page.page_number, Page.error)
            .where(Page.book_id == book_id)
            .order_by(Page.page_number)
        )
        pages = result.all()

        if pages:
            print(f"\n📄 PAGES: {len(pages)} total")
            page_status = {}
            for status, _, _ in pages:
                page_status[status] = page_status.get(status, 0) + 1

            for status, count in page_status.items():
                print(f"  {status}: {count}")

            # Show errors if any
            errors = [(num, err) for _, num, err in pages if err]
            if errors:
                print(f"\n❌ PAGE ERRORS:")
                for num, err in errors[:5]:
                    print(f"  Page {num}: {err[:100]}...")
        else:
            print("\n📄 PAGES: None created yet")
            print("  → This explains why it's pending!")
            print("  → The PDF has not been processed by the worker")

    await engine.dispose()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python inspect_book.py <book_id>")
        sys.exit(1)

    asyncio.run(inspect(sys.argv[1]))
