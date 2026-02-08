import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def search_similar():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("kitabim_ai_db")
    
    print("Searching for tokens containing 'ئۆن'...")
    cursor = db.ocr_vocabulary.find({"token": {"$regex": "ئۆن"}})
    count = 0
    async for doc in cursor:
        print(f"Token: {doc.get('token')} | Status: {doc.get('status')} | Freq: {doc.get('frequency')}")
        count += 1
    
    if count == 0:
        print("No matches found with regex. Checking for the specific word again...")
        doc = await db.ocr_vocabulary.find_one({"token": "ئۆنىكتىن"})
        print(f"Direct lookup 'ئۆنىكتىن': {doc}")

if __name__ == "__main__":
    asyncio.run(search_similar())
