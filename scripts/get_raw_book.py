import asyncio
from app.db.mongodb import db_manager
import json
from bson import json_util

async def get_raw_book():
    await db_manager.connect_to_storage()
    db = db_manager.db
    book = await db.books.find_one({"title": {"$regex": "سەمەندەر"}})
    print(json.dumps(book, default=json_util.default, ensure_ascii=False, indent=2))
    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(get_raw_book())
