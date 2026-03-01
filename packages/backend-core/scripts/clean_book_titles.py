import asyncio
import logging
from sqlalchemy import select
from app.db import session as db_session
from app.db.models import Book

# Assuming we want to apply the same character replacements done in clean_uyghur_text
def clean_title_chars(text: str) -> str:
    if not text:
        return ""
    return text.replace("ی", "ي").replace("ه", "ە").replace("\u064A\u0654", "\u0626")

async def update_book_titles():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("clean_book_titles")
    
    logger.info("Initializing database...")
    await db_session.init_db()
    
    if not db_session.async_session_factory:
        logger.error("Failed to initialize db session factory")
        return
        
    try:
        async with db_session.async_session_factory() as session:
            logger.info("Fetching all books...")
            result = await session.execute(select(Book))
            books = result.scalars().all()
            
            logger.info(f"Found {len(books)} books. Processing titles...")
            
            updated_count = 0
            for book in books:
                if not book.title:
                    continue
                    
                cleaned = clean_title_chars(book.title)
                if cleaned != book.title:
                    logger.info(f"Updating title: '{book.title}' -> '{cleaned}'")
                    book.title = cleaned
                    updated_count += 1
            
            if updated_count > 0:
                logger.info(f"Committing {updated_count} updates...")
                await session.commit()
            else:
                logger.info("No titles needed updating.")
                
    except Exception as e:
        logger.error(f"An error occurred: {e}")
    finally:
        await db_session.close_db()

if __name__ == "__main__":
    asyncio.run(update_book_titles())
