import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

async def main():
    uri = os.environ.get("MONGODB_URL")
    if not uri:
        # Fallback for inside container or local
        uri = "mongodb://mongodb:27017"
        
    db_name = os.environ.get("MONGODB_DATABASE", "kitabim_ai_db")
        
    print(f"Connecting to {uri}...")
    client = AsyncIOMotorClient(uri)
    db = client[db_name] 
    print(f"Using database: {db_name}")

    print("Unsetting 'content' field from all books...")
    result = await db.books.update_many(
        {}, 
        {"$unset": {"content": ""}}
    )
    
    print(f"Modified {result.modified_count} books.")
    
    # Verify
    count = await db.books.count_documents({"content": {"$exists": True}})
    print(f"Remaining books with content field: {count}")

if __name__ == "__main__":
    asyncio.run(main())
