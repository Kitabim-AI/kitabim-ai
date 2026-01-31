from __future__ import annotations

import asyncio

from app.db.mongodb import db_manager
from app.services.pdf_service import process_pdf_task


async def main() -> None:
    await db_manager.connect_to_storage()
    db = db_manager.db
    if db is None:
        print("Database connection failed.")
        return

    books = await db.books.find().to_list(None)
    print(f"Found {len(books)} books")

    for idx, book in enumerate(books, start=1):
        book_id = book.get("id")
        if not book_id and book.get("_id"):
            book_id = str(book.get("_id"))
            await db.books.update_one({"_id": book.get("_id")}, {"$set": {"id": book_id}})

        results = book.get("results") or []
        cleaned = []
        changed = False
        for r in results:
            if "embedding" in r:
                r = {k: v for k, v in r.items() if k != "embedding"}
                changed = True
            cleaned.append(r)

        if changed:
            await db.books.update_one(
                {"id": book_id},
                {"$set": {"results": cleaned, "status": "processing", "processingStep": "rag"}},
            )

        print(f"[{idx}/{len(books)}] Reprocessing {book_id}...")
        await process_pdf_task(book_id)

    await db_manager.close_storage()


if __name__ == "__main__":
    asyncio.run(main())
