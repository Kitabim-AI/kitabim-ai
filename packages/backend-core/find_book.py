import asyncio
import os
import sys
from app.db.mongodb import db_manager

async def find_book(title):
    await db_manager.connect_to_storage()
    db = db_manager.db
    # Try exact match first
    book = await db.books.find_one({"title": title})
    if not book:
        # Try regex
        book = await db.books.find_one({"title": {"$regex": title}})
    
    if book:
        print(f"FOUND:{book['id']}")
    else:
        # List some books to help debug
        print("NOT_FOUND")
        books = await db.books.find().limit(5).to_list(5)
        print("Available books:")
        for b in books:
            print(f"- {b.get('title')}")
            
    await db_manager.close_storage()

if __name__ == "__main__":
    title = sys.argv[1]
    asyncio.run(find_book(title))
