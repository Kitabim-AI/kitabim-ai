"""Check how many pages in the database are not indexed"""
import asyncio
from sqlalchemy import select, func
from app.db import session as db_session
from app.db.models import Page, Book


async def count_unindexed():
    # Initialize database
    await db_session.init_db()

    try:
        async with db_session.async_session_factory() as session:
            # Count total pages
            total_stmt = select(func.count()).select_from(Page)
            total_result = await session.execute(total_stmt)
            total = total_result.scalar()

            # Count unindexed pages
            unindexed_stmt = select(func.count()).select_from(Page).where(Page.is_indexed == False)
            unindexed_result = await session.execute(unindexed_stmt)
            unindexed = unindexed_result.scalar()

            # Count indexed pages
            indexed = total - unindexed

            print(f"\n=== Page Indexing Status ===")
            print(f"Total pages:      {total:,}")
            print(f"Indexed pages:    {indexed:,}")
            print(f"Unindexed pages:  {unindexed:,}")
            if total > 0:
                print(f"Percentage indexed: {(indexed/total*100):.2f}%")
            print()

            # Find books with unindexed pages
            if unindexed > 0:
                print("=== Books with Unindexed Pages ===")

                # Group by book_id and count unindexed pages per book
                stmt = (
                    select(
                        Page.book_id,
                        Book.title,
                        Book.status,
                        func.count(Page.id).label('unindexed_count')
                    )
                    .join(Book, Page.book_id == Book.id)
                    .where(Page.is_indexed == False)
                    .group_by(Page.book_id, Book.title, Book.status)
                    .order_by(func.count(Page.id).desc())
                )

                result = await session.execute(stmt)
                books_with_unindexed = result.all()

                print(f"\nFound {len(books_with_unindexed)} books with unindexed pages:\n")
                print(f"{'Book ID':<40} {'Title':<50} {'Status':<12} {'Unindexed'}")
                print("-" * 120)

                for book_id, title, status, count in books_with_unindexed:
                    title_truncated = (title[:47] + '...') if title and len(title) > 50 else (title or 'Untitled')
                    print(f"{book_id:<40} {title_truncated:<50} {status:<12} {count:>8}")

                print()
    finally:
        await db_session.close_db()


if __name__ == "__main__":
    asyncio.run(count_unindexed())
