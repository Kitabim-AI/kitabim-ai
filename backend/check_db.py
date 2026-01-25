import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def check_db():
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    books = await db.books.find().to_list(100)
    print(f"Total books: {len(books)}")
    
    for b in books:
        results = b.get("results", [])
        total_pages = b.get("totalPages", 0)
        completed = [r for r in results if r.get("status") == "completed"]
        with_embeddings = [r for r in completed if "embedding" in r]
        
        print(f"Book: {b.get('title')} ({b.get('id')})")
        print(f"  Pages: {total_pages}, Completed OCR: {len(completed)}, With Embeddings: {len(with_embeddings)}")
        
        if len(with_embeddings) == 0 and len(completed) > 0:
            print("  ⚠️ NO EMBEDDINGS FOUND for this book!")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(check_db())
