
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
    bc = await db.books.count_documents({})
    pc = await db.pages.count_documents({})
    cc = await db.chunks.count_documents({})
    print(f"Database: {database_name}")
    print(f"Books: {bc}")
    print(f"Pages: {pc}")
    print(f"Chunks: {cc}")
    client.close()

if __name__ == "__main__":
    asyncio.run(main())
