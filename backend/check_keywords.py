
import motor.motor_asyncio
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def check_keywords():
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    # regex search for Tughluq (fuzzy)
    # Tughluq: توغلۇق
    
    print("🔍 Searching for 'توغلۇق' in Tarikh-i Rashidi...")
    
    books = await db.books.find({"title": {"$regex": "رەشىدىي"}}).to_list(10)
    
    for book in books:
        print(f"Book: {book['title']}")
        hits = 0
        for r in book.get("results", []):
            text = r.get("text", "")
            if "توغلۇق" in text:
                hits += 1
                if hits <= 3:
                     print(f"  - Page {r['pageNumber']}: ...{text[text.find('توغلۇق')-20:text.find('توغلۇق')+50].replace(chr(10), ' ')}...")
        print(f"  Total hits: {hits}")

    client.close()

if __name__ == "__main__":
    asyncio.run(check_keywords())
