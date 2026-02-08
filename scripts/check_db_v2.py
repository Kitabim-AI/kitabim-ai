
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def check_db(db_name):
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongodb_url)
    db = client[db_name]
    
    print(f"\n--- Checking database: {db_name} ---")
    collections = await db.list_collection_names()
    print(f"Collections: {collections}")
    
    if 'books' in collections:
        total_books = await db.books.count_documents({})
        print(f"Total Books: {total_books}")
        
        # Count field occurrences
        results_count = await db.books.count_documents({"results": {"$exists": True}})
        pages_count = await db.books.count_documents({"pages": {"$exists": True}})
        print(f"Books with 'results': {results_count}")
        print(f"Books with 'pages': {pages_count}")
        
        sample = await db.books.find_one({})
        if sample:
            print(f"Sample Book ID: {sample.get('id')}")
            print(f"Sample Book Keys: {list(sample.keys())}")
            if 'results' in sample:
                 print(f"Results type: {type(sample['results'])}")
            if 'pages' in sample:
                 print(f"Pages type: {type(sample['pages'])}")
    else:
        print("No 'books' collection found.")
    
    client.close()

async def main():
    await check_db("kitabim_ai_db")
    await check_db("uyghur_library")

if __name__ == "__main__":
    asyncio.run(main())
