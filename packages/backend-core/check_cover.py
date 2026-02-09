import asyncio
from app.db.mongodb import db_manager

async def check():
    await db_manager.connect_to_storage()
    b = await db_manager.db.books.find_one({'id': 'c0583da70862'})
    print(f"TITLE: {b.get('title')}")
    print(f"COVER: {b.get('coverUrl')}")
    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(check())
