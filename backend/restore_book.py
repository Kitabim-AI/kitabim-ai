import asyncio
from app.db.mongodb import db_manager
from app.services.pdf_service import process_pdf_task

async def restore_and_reprocess(book_id: str):
    await db_manager.connect_to_storage()
    db = db_manager.db
    
    print(f"Resetting book {book_id} for reprocessing...")
    
    # Reset the book record to clear my "word-split" update
    await db.books.update_one(
        {"id": book_id},
        {
            "$set": {
                "content": "",
                "results": [],
                "status": "processing"
            }
        }
    )
    
    print(f"Triggering OCR reprocessing for {book_id}...")
    # This will re-run the OCR using Gemini on the original PDF
    await process_pdf_task(book_id)
    
    print(f"✅ Reprocessing triggered for {book_id}. Check server logs for progress.")
    await db_manager.close_storage()

if __name__ == "__main__":
    asyncio.run(restore_and_reprocess("df1b002d28bd"))
