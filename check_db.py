import motor.motor_asyncio
import asyncio

async def run():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.kitabim_ai_db
    count = await db.books.count_documents({})
    print(f"Total books in DB: {count}")
    async for book in db.books.find():
        print(f"Title: {book.get('title')}, Status: {book.get('status')}, Hash: {book.get('contentHash')}")

if __name__ == "__main__":
    asyncio.run(run())
