import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def cleanup_ocr_registry():
    # Load environment variables
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB_NAME", "kitabim_ai_db")
    
    client = AsyncIOMotorClient(mongo_uri)
    db = client[db_name]
    
    collections_to_drop = [
        "ocr_vocabulary",
        "temp_raw_vocabulary",
        "ocr_correction_history",
        "ocr_correction_jobs"
    ]
    
    print(f"Connecting to database: {db_name}")
    
    for collection in collections_to_drop:
        print(f"Dropping collection: {collection}...")
        try:
            await db.drop_collection(collection)
            print(f"Successfully dropped {collection}")
        except Exception as e:
            print(f"Error dropping {collection}: {e}")
            
    print("\nCleanup complete.")
    client.close()

if __name__ == "__main__":
    asyncio.run(cleanup_ocr_registry())
