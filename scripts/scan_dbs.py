
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongodb_url)
    
    dbs = await client.list_database_names()
    print(f"Databases: {dbs}")
    
    for db_name in dbs:
        if db_name in ['admin', 'local', 'config']: continue
        db = client[db_name]
        cols = await db.list_collection_names()
        print(f"\nDatabase: {db_name}, Collections: {cols}")
        if 'books' in cols:
            total = await db.books.count_documents({})
            with_res = await db.books.count_documents({"results": {"$exists": True}})
            with_pages = await db.books.count_documents({"pages": {"$exists": True}})
            print(f"  Total books: {total}")
            print(f"  Books with 'results': {with_res}")
            print(f"  Books with 'pages': {with_pages}")
            sample = await db.books.find_one({})
            if sample:
                print(f"  Sample fields: {list(sample.keys())}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
