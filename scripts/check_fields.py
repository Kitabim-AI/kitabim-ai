
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("MONGODB_DATABASE", "kitabim_ai_db")
    
    client = AsyncIOMotorClient(mongodb_url)
    db = client[database_name]
    
    print(f"Checking database: {database_name}")
    
    # Check books collection
    res_count = await db.books.count_documents({"results": {"$exists": True}})
    pages_count = await db.books.count_documents({"pages": {"$exists": True}})
    total_books = await db.books.count_documents({})
    
    print(f"Total Books: {total_books}")
    print(f"Books with 'results' field: {res_count}")
    print(f"Books with 'pages' field: {pages_count}")
    
    # Check one sample book
    sample = await db.books.find_one({})
    if sample:
        print("\nSample Book structure:")
        print(f"ID: {sample.get('id')}")
        print(f"Fields: {list(sample.keys())}")
        if 'results' in sample:
            print(f"'results' type: {type(sample['results'])}")
            if isinstance(sample['results'], list):
                print(f"'results' length: {len(sample['results'])}")
        if 'pages' in sample:
            print(f"'pages' type: {type(sample['pages'])}")
            if isinstance(sample['pages'], list):
                print(f"'pages' length: {len(sample['pages'])}")
                
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
