import asyncio
import os
import sys
from app.db.mongodb import db_manager

async def check_ids(ids):
    await db_manager.connect_to_storage()
    db = db_manager.db
    
    for i in ids:
        print(f"\nChecking ID/Fragment: {i}")
        books = await db.books.find({
            "$or": [
                {"id": {"$regex": i}},
                {"title": {"$regex": i}},
                {"author": {"$regex": i}}
            ]
        }).to_list(10)
        
        if not books:
            print("  NOT FOUND")
        else:
            for b in books:
                print(f"  - Book Found: {b.get('title')} (ID: {b.get('id')})")

    await db_manager.close_storage()

if __name__ == "__main__":
    ids = sys.argv[1:] if len(sys.argv) > 1 else ["55f64b4d08fa", "720f243f74d2", "4d67117e9a0", "94d67117e9a0", "c222d08e949d"]
    asyncio.run(check_ids(ids))
