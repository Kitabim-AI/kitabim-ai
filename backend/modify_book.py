"""
Script to manually modify a book record in MongoDB.
Usage: python modify_book.py
"""
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv
from bson import ObjectId

load_dotenv()

async def list_books():
    """List all books with their IDs for reference."""
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    books = await db.books.find().to_list(100)
    print(f"\n📚 Found {len(books)} books:\n")
    
    for i, b in enumerate(books):
        book_id = b.get('id') or str(b.get('_id'))
        title = b.get('title', 'Untitled')
        status = b.get('overallStatus', 'N/A')
        print(f"  {i+1}. [{status}] {title}")
        print(f"      id: {book_id}")
    
    client.close()
    return books

async def get_book(book_id: str):
    """Get a single book by ID."""
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    # Try to find by 'id' field first, then by _id
    book = await db.books.find_one({"id": book_id})
    if not book:
        try:
            book = await db.books.find_one({"_id": ObjectId(book_id)})
        except:
            pass
    
    client.close()
    return book

async def update_book(book_id: str, updates: dict):
    """Update a book with the given changes."""
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    # Try to find by 'id' field first
    result = await db.books.update_one({"id": book_id}, {"$set": updates})
    
    if result.matched_count == 0:
        # Try by _id
        try:
            result = await db.books.update_one({"_id": ObjectId(book_id)}, {"$set": updates})
        except:
            pass
    
    client.close()
    
    if result.matched_count > 0:
        print(f"✅ Updated {result.modified_count} document(s)")
        return True
    else:
        print(f"❌ No book found with id: {book_id}")
        return False

async def reset_ocr_status(book_id: str):
    """Reset OCR status for a book to reprocess."""
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    # Reset overall status and page results
    updates = {
        "overallStatus": "pending",
    }
    
    # Also reset all page results to pending
    book = await get_book(book_id)
    if book:
        results = book.get("results", [])
        for r in results:
            r["status"] = "pending"
            r.pop("ocrText", None)
            r.pop("embedding", None)
        updates["results"] = results
    
    await update_book(book_id, updates)
    print(f"🔄 Reset OCR status for book: {book_id}")
    
    client.close()

# Example usage - modify as needed
if __name__ == "__main__":
    print("=" * 50)
    print("MongoDB Book Modifier")
    print("=" * 50)
    
    # List all books
    asyncio.run(list_books())
    
    # Fix the problematic book - add missing fields
    from datetime import datetime
    
    book_id = "efb8b34926ba"
    book = asyncio.run(get_book(book_id))
    
    if book:
        print(f"\n📖 Current book fields:")
        print(f"  uploadDate: {book.get('uploadDate')}")
        print(f"  status: {book.get('status')}")
        
        # Add missing required fields
        updates = {}
        
        if not book.get('uploadDate'):
            updates['uploadDate'] = datetime.now()
            print("  → Adding uploadDate")
            
        if not book.get('lastUpdated'):
            updates['lastUpdated'] = datetime.now()
            print("  → Adding lastUpdated")
            
        if not book.get('status'):
            updates['status'] = 'ready'
            print("  → Adding status = ready")
        
        if updates:
            asyncio.run(update_book(book_id, updates))
            print(f"\n✅ Fixed book with updates: {list(updates.keys())}")
        else:
            print("\n✅ Book already has all required fields")
    else:
        print(f"❌ Book {book_id} not found!")
