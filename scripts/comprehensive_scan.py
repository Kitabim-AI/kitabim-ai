
import asyncio
import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

async def main():
    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongodb_url)
    db = client.kitabim_ai_db
    
    fields_to_check = ['results', 'pages', 'previousResults', 'content', 'previousContent']
    
    print(f"Checking kitabim_ai_db.books collection (Total documents: {await db.books.count_documents({})})")
    
    for field in fields_to_check:
        count = await db.books.count_documents({field: {"$exists": True}})
        print(f"Books with '{field}': {count}")
        if count > 0:
            sample = await db.books.find_one({field: {"$exists": True}})
            val = sample.get(field)
            print(f"  Sample {field} type: {type(val)}")
            if isinstance(val, list):
                print(f"  Sample {field} length: {len(val)}")
            elif isinstance(val, str):
                print(f"  Sample {field} length: {len(val)}")

    client.close()

if __name__ == "__main__":
    asyncio.run(main())
