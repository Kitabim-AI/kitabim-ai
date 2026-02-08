import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

async def get_raw():
    load_dotenv()
    mongo_uri = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    client = AsyncIOMotorClient(mongo_uri)
    db = client.get_database("kitabim_ai_db")
    page = await db.pages.find_one({"bookId": "06be05f2d848", "pageNumber": 16})
    if page:
        text = page.get("text", "")
        # Find 'ئۆنىكتىن'
        target = "ئۆنىكتىن"
        idx = text.find(target)
        if idx != -1:
            print(f"Found at {idx}")
            print(f"SURROUNDING RAW: {repr(text[max(0, idx-10):idx+len(target)+10])}")
        else:
            print("Target not found directly. Searching without space...")
            joined = "چۈشۈردىئۆنىكتىن"
            idx = text.find(joined)
            if idx != -1:
                 print(f"Found joined at {idx}")
                 print(f"SURROUNDING RAW: {repr(text[max(0, idx-10):idx+len(joined)+10])}")
            else:
                print("Could not find either.")

if __name__ == "__main__":
    asyncio.run(get_raw())
