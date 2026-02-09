
import asyncio
import os
import sys
import re
from motor.motor_asyncio import AsyncIOMotorClient

# Add project root and backend-core to PYTHONPATH
ROOT_DIR = "/Users/Omarjan/Projects/kitabim-ai"
BACKEND_DIR = os.path.join(ROOT_DIR, "packages/backend-core")
sys.path.append(ROOT_DIR)
sys.path.append(BACKEND_DIR)

async def extract_proverbs():
    try:
        from app.core.config import settings
        client = AsyncIOMotorClient(settings.mongodb_url)
        db = client[settings.database_name]
        
        # Configuration for volumes and ranges
        ranges = [
            {"bookId": "4943b97e8e60", "volume": 1, "start": 56, "end": 716},
            {"bookId": "1d31742dc6ec", "volume": 2, "start": 9, "end": 691},
            {"bookId": "e8250ea5e646", "volume": 3, "start": 9, "end": 670},
        ]
        
        proverbs_to_insert = []
        total_extracted = 0

        for r in ranges:
            book_id = r["bookId"]
            start_page = r["start"]
            end_page = r["end"]
            volume = r["volume"]
            
            print(f"Processing Volume {volume} (Book ID: {book_id}) from page {start_page} to {end_page}...")
            
            # Fetch all pages in range
            cursor = db.pages.find({
                "bookId": book_id,
                "pageNumber": {"$gte": start_page, "$lte": end_page}
            }).sort("pageNumber", 1)
            
            async for page in cursor:
                text = page.get("text", "")
                page_num = page.get("pageNumber")
                
                # Split text into lines
                lines = text.split("\n")
                
                for line in lines:
                    line = line.strip()
                    
                    # Filtering criteria
                    if not line:
                        continue
                    
                    # Ignore standard [Header] and [Footer] tags
                    if line.startswith("[Header]") or line.startswith("[Footer]"):
                        continue
                    
                    # Ignore lines that are just numbers (even if OCR missed the [Footer] tag)
                    if line.isdigit():
                        continue
                    
                    # Ignore Markdown headers (like category titles # ئا)
                    if line.startswith("#"):
                        continue
                        
                    # Also common page number artifacts from OCR if they appear as standalone lines
                    if re.match(r"^\d+$", line):
                        continue

                    # If it passed all checks, it's a proverb line
                    proverbs_to_insert.append({
                        "text": line,
                        "bookId": book_id,
                        "volume": volume,
                        "pageNumber": page_num,
                        "type": "proverb"
                    })
                    total_extracted += 1
            
            print(f"Extracted {total_extracted} lines so far.")

        if proverbs_to_insert:
            # Clear existing proverbs if necessary or just insert
            # The user didn't say to clear, but "create a new table" suggests a fresh start
            print(f"Inserting {len(proverbs_to_insert)} records into 'proverbs' collection...")
            
            # Optional: Drop the collection first to ensure a clean start as requested
            await db.proverbs.drop()
            
            # Bulk insert (batching for large volumes if needed, but here we can do it in chunks)
            chunk_size = 1000
            for i in range(0, len(proverbs_to_insert), chunk_size):
                await db.proverbs.insert_many(proverbs_to_insert[i:i + chunk_size])
            
            print("Extraction and insertion complete.")
        else:
            print("No proverbs found to extract.")

    except Exception as e:
        print(f"Error during extraction: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(extract_proverbs())
