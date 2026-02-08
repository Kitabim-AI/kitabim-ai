import asyncio
import os
from pymongo import MongoClient, UpdateOne
from datetime import datetime

# Configuration
MONGO_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DATABASE", "kitabim_ai_db")

def migrate():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    
    print(f"Starting migration to 'pages' collection in database: {DB_NAME}")
    
    books_coll = db.books
    pages_coll = db.pages
    
    # Ensure indexes
    print("Ensuring indexes on 'pages' collection...")
    pages_coll.create_index([("bookId", 1), ("pageNumber", 1)], unique=True)
    pages_coll.create_index([("bookId", 1)])
    
    books = list(books_coll.find({}))
    total_books = len(books)
    print(f"Found {total_books} books to process.")
    
    total_migrated = 0
    
    for i, book in enumerate(books):
        book_id = book.get("id")
        title = book.get("title", "Unknown")
        results = book.get("results", [])
        
        if not book_id:
            print(f"[{i+1}/{total_books}] Skipping book without ID: {title}")
            continue
            
        if not results:
            print(f"[{i+1}/{total_books}] No results for book: {title}")
            continue
            
        print(f"[{i+1}/{total_books}] Migrating {len(results)} pages for: {title} ({book_id})")
        
        ops = []
        for r in results:
            page_num = r.get("pageNumber")
            if page_num is None:
                continue
                
            page_data = {
                "bookId": book_id,
                "pageNumber": page_num,
                "text": r.get("text", ""),
                "status": r.get("status", "pending"),
                "isVerified": r.get("isVerified", False),
                "error": r.get("error"),
                "lastUpdated": datetime.utcnow()
            }
            if "embedding" in r:
                page_data["embedding"] = r["embedding"]
                
            ops.append(UpdateOne(
                {"bookId": book_id, "pageNumber": page_num},
                {"$set": page_data},
                upsert=True
            ))
        
        if ops:
            pages_coll.bulk_write(ops)
            total_migrated += len(ops)
            
    print(f"\nMigration finished! Total pages created/updated: {total_migrated}")
    client.close()

if __name__ == "__main__":
    migrate()
