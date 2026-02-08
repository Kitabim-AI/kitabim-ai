
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongodb_url)
    db = client.kitabim_ai_db
    
    # Try finding the specific book cea06b495380
    book_id = "cea06b495380"
    book = await db.books.find_one({"id": book_id})
    
    if book:
        print(f"Book found: {book_id}")
        print(f"Keys: {list(book.keys())}")
        if 'results' in book:
            print(f"'results' is present in DB for this book.")
        if 'pages' in book:
            print(f"'pages' is present in DB for this book.")
    else:
        print(f"Book {book_id} not found in kitabim_ai_db.books")
        
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
