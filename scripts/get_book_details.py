import asyncio
import os
import sys
from app.db.mongodb import db_manager

async def get_details():
    await db_manager.connect_to_storage()
    db = db_manager.db
    
    # Broad search for potential matches
    patterns = ["پارلاق", "ئىستىقبال", "سەمەندەر"]
    for p in patterns:
        print(f"\nSearching for pattern: {p}")
        books = await db.books.find({
            "title": {"$regex": p, "$options": "i"}
        }).to_list(10)
        
        for book in books:
            print(f"  - Title: {book.get('title')}")
            print(f"    ID: {book.get('id')}")
            print(f"    Author: {book.get('author')}")
            print(f"    Cover URL: {book.get('coverUrl')}")
            print(f"    Status: {book.get('status')}")

    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(get_details())
