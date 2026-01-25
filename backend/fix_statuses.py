import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def fix_books():
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
    db = client.kitabim_ai_db
    
    # Change books with "error" status back to "ready"
    # This will let the lifespan logic re-trigger cover extraction if needed
    result = await db.books.update_many(
        {"status": "error"},
        {"$set": {"status": "ready"}}
    )
    print(f"Updated {result.modified_count} books from 'error' to 'ready'")
    
    # Also check if any are 'pending' and set them to 'ready' if they have content?
    # No, 'ready' is better.
    
    client.close()

if __name__ == "__main__":
    asyncio.run(fix_books())
