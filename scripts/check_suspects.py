import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def check_suspects():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("kitabim_ai_db")
    
    print("Top 20 suspects with candidates:")
    cursor = db.ocr_vocabulary.find({
        "status": "suspect",
        "candidates": {"$exists": True, "$ne": []}
    }).sort("frequency", -1).limit(20)
    
    async for doc in cursor:
        token = doc.get("token")
        freq = doc.get("frequency")
        span = doc.get("bookSpan")
        candidates = doc.get("candidates", [])
        top_cand = candidates[0] if candidates else None
        
        print(f"Suspect: {token} (freq: {freq}, span: {span})")
        if top_cand:
            print(f"  -> Top Candidate: {top_cand['token']} (conf: {top_cand['confidence']}, freq: {top_cand['frequency']})")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(check_suspects())
