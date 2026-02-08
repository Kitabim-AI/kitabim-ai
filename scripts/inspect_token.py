import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def inspect_token(token_str):
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("kitabim_ai_db")
    
    doc = await db.ocr_vocabulary.find_one({"token": token_str})
    if not doc:
        print(f"Token '{token_str}' not found.")
        return

    print(f"Token: {doc.get('token')}")
    print(f"Status: {doc.get('status')}")
    print(f"Frequency: {doc.get('frequency')}")
    print(f"Book Span: {doc.get('bookSpan')}")
    print(f"Book IDs Count: {len(doc.get('bookIds', []))}")

if __name__ == "__main__":
    import sys
    token = sys.argv[1] if len(sys.argv) > 1 else "ئىككى"
    asyncio.run(inspect_token(token))
