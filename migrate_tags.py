import motor.motor_asyncio
import asyncio

async def migrate_tags_to_series():
    client = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
    db = client.kitabim_ai_db
    collection = db.books
    
    print("Starting migration: tags -> series")
    
    count = 0
    async for book in collection.find({"tags": {"$exists": True, "$ne": []}}):
        tags = book.get("tags", [])
        existing_series = book.get("series", [])
        
        # Merge tags into series, avoiding duplicates
        new_series = list(set(existing_series + tags))
        
        await collection.update_one(
            {"_id": book["_id"]},
            {
                "$set": {"series": new_series},
                "$unset": {"tags": ""}
            }
        )
        count += 1
        print(f"Migrated book {book.get('title', 'Unknown')}: {tags} -> {new_series}")
        
    # Also unset empty tags fields just to be clean
    await collection.update_many(
        {"tags": {"$exists": True}},
        {"$unset": {"tags": ""}}
    )

    print(f"Migration completed. Updated {count} books.")

if __name__ == "__main__":
    asyncio.run(migrate_tags_to_series())
