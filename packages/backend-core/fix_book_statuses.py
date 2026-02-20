"""Fix book statuses - change 'ready' to 'completed' for books with unindexed pages"""
import asyncio
from datetime import datetime
from sqlalchemy import select, func, and_, update
from app.db import session as db_session
from app.db.models import Page, Book


async def fix_book_statuses():
    """Update books that are marked as 'ready' but have unindexed pages to 'completed'"""
    await db_session.init_db()

    try:
        async with db_session.async_session_factory() as session:
            # Find books marked as 'ready' with unindexed pages
            stmt = (
                select(
                    Book.id,
                    Book.title,
                    Book.total_pages,
                    func.count(Page.id).label('unindexed_count')
                )
                .join(Page, Page.book_id == Book.id)
                .where(
                    and_(
                        Book.status == "ready",
                        Page.is_indexed == False
                    )
                )
                .group_by(Book.id, Book.title, Book.total_pages)
            )

            result = await session.execute(stmt)
            books_to_fix = result.all()

            if not books_to_fix:
                print("\n✓ No books need status correction")
                return

            print(f"\n=== Found {len(books_to_fix)} books marked as 'ready' with unindexed pages ===\n")
            print(f"{'Book ID':<40} {'Title':<50} {'Unindexed Pages'}")
            print("-" * 110)

            for book_id, title, total_pages, unindexed_count in books_to_fix:
                title_truncated = (title[:47] + '...') if title and len(title) > 50 else (title or 'Untitled')
                print(f"{book_id:<40} {title_truncated:<50} {unindexed_count:>8}")

            print(f"\nChanging status from 'ready' → 'completed' for these books...")

            # Update all books from 'ready' to 'completed' if they have unindexed pages
            book_ids_to_update = [book_id for book_id, _, _, _ in books_to_fix]

            update_stmt = (
                update(Book)
                .where(Book.id.in_(book_ids_to_update))
                .values(status="completed", last_updated=datetime.utcnow())
            )

            result = await session.execute(update_stmt)
            await session.commit()

            print(f"\n✓ Updated {result.rowcount} books to 'completed' status\n")

    finally:
        await db_session.close_db()


if __name__ == "__main__":
    asyncio.run(fix_book_statuses())
