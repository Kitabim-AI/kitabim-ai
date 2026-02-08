import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
import re
from dotenv import load_dotenv

async def check_suspects_no_punct():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("kitabim_ai_db")
    
    # Arabic punctuation characters to avoid in this specific check
    arabic_punct = r'[\u060C\u061F\u06D4]'
    
    print("Suspects with no apparent Arabic punctuation:")
    cursor = db.ocr_vocabulary.find({
        "status": "suspect",
        "token": {"$not": re.compile(arabic_punct)},
        "candidates": {"$exists": True, "$ne": []}
    }).sort("frequency", -1).limit(40)
    
    async for doc in cursor:
        token = doc.get("token")
        freq = doc.get("frequency")
        candidates = doc.get("candidates", [])
        top_cand = candidates[0] if candidates else None
        
        # Additional filter: skip if token has digits (could be years, etc)
        if any(c.isdigit() for c in token):
            continue

        print(f"Suspect: {token} (freq: {freq})")
        if top_cand:
            print(f"  -> Top Candidate: {top_cand['token']} (conf: {top_cand['confidence']}, freq: {top_cand['frequency']})")
        print("-" * 20)

if __name__ == "__main__":
    asyncio.run(check_suspects_no_punct())
