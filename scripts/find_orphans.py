import asyncio
import os
from app.db.mongodb import db_manager

async def find_orphans():
    await db_manager.connect_to_storage()
    db = db_manager.db
    
    # Get all book IDs
    books = await db.books.find({}, {"id": 1}).to_list(None)
    book_ids = {b["id"] for b in books}
    
    # Get all cover files
    cover_dir = "data/covers"
    files = os.listdir(cover_dir)
    
    orphans = []
    for f in files:
        if not f.endswith(".jpg"):
            continue
        id_part = f[:-4]
        if id_part not in book_ids:
            orphans.append(f)
            
    print(f"Total orphans found: {len(orphans)}")
    for o in orphans:
        size = os.path.getsize(os.path.join(cover_dir, o))
        print(f"  - {o} ({size/1024:.1f} KB)")
        
    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(find_orphans())
