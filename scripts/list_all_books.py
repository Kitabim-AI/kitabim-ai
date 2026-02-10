import asyncio
from app.db.mongodb import db_manager

async def list_all():
    await db_manager.connect_to_storage()
    db = db_manager.db
    books = await db.books.find({}, {"title": 1, "id": 1, "coverUrl": 1}).to_list(None)
    for b in books:
        print(f"{b.get('id')} | {b.get('title')} | {b.get('coverUrl')}")
    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(list_all())
