import os
import fitz
import asyncio
import random
import google.generativeai as genai
from datetime import datetime
from app.core.config import settings
from app.db.mongodb import db_manager
from app.utils.text import clean_uyghur_text
from app.core.prompts import OCR_PROMPT

# Task Locking to prevent duplicates
RUNNING_TASKS = set()

async def process_pdf_task(book_id: str):
    if book_id in RUNNING_TASKS:
        print(f"⏩ Task for {book_id} is already running. Skipping duplicate call.")
        return
        
    RUNNING_TASKS.add(book_id)
    db = db_manager.db
    try:
        file_path = os.path.join(settings.UPLOADS_DIR, f"{book_id}.pdf")
        if not os.path.exists(file_path):
            print(f"File not found: {file_path}")
            await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
            return

        doc = fitz.open(file_path)
        total_pages = doc.page_count
        
        book = await db.books.find_one({"id": book_id})
        if not book: return

        results = book.get("results", [])
        if not results:
            results = [{"pageNumber": i + 1, "text": "", "status": "pending"} for i in range(total_pages)]
            await db.books.update_one(
                {"id": book_id},
                {"$set": {"totalPages": total_pages, "results": results, "status": "processing"}}
            )
        
        # Extract Cover Image (First Page)
        cover_path = os.path.join(settings.COVERS_DIR, f"{book_id}.jpg")
        if not os.path.exists(cover_path) and total_pages > 0:
            try:
                first_page = doc.load_page(0)
                pix = first_page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5)) 
                pix.save(cover_path)
                await db.books.update_one(
                    {"id": book_id},
                    {"$set": {"coverUrl": f"/api/covers/{book_id}.jpg"}}
                )
            except Exception as e:
                print(f"Failed to extract cover for {book_id}: {e}")

        pages_to_process = [r["pageNumber"] for r in results if r["status"] != "completed" or (r.get("status") == "completed" and "embedding" not in r)]
        
        if not pages_to_process:
            await db.books.update_one({"id": book_id}, {"$set": {"status": "ready"}})
            return

        print(f"📦 Starting Parallel Process for Book {book_id}: {len(pages_to_process)} tasks.")
        model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
        
        semaphore = asyncio.Semaphore(settings.MAX_PARALLEL_PAGES)
        
        async def process_page(page_num):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                try:
                    current_book = await db.books.find_one({"id": book_id})
                    page_record = next((r for r in current_book["results"] if r["pageNumber"] == page_num), None)
                    
                    existing_text = page_record.get("text", "") if page_record else ""
                    already_ocr = (page_record.get("status") == "completed" and len(existing_text) > 40) if page_record else False

                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": page_num},
                        {"$set": {"results.$.status": "processing"}}
                    )

                    success = already_ocr
                    page_text = existing_text

                    if not already_ocr:
                        page = doc.load_page(page_num - 1)
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
                        img_bytes = pix.tobytes("jpeg")
                        
                        for attempt in range(5):
                            try:
                                print(f"🚀 AI OCR Request: Book={book_id} Page={page_num} Attempt={attempt+1}")
                                response = await model.generate_content_async([
                                    {"mime_type": "image/jpeg", "data": img_bytes},
                                    {"text": OCR_PROMPT}
                                ])
                                page_text = clean_uyghur_text(response.text)
                                success = True
                                break
                            except Exception as e:
                                if ("503" in str(e) or "overloaded" in str(e).lower()) and attempt < 4:
                                    await asyncio.sleep((2 ** (attempt + 1)) + random.uniform(0, 1))
                                    continue
                                else:
                                    page_text = f"[OCR Error: {str(e)}]"
                                    break
                    
                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": page_num},
                        {"$set": {"results.$.text": page_text, "results.$.status": "completed" if success else "error"}}
                    )
                except Exception as e:
                    print(f"💥 Error on page {page_num}: {e}")

        # Run OCR phase
        tasks = [process_page(p) for p in pages_to_process]
        await asyncio.gather(*tasks)
            
        # Batch Embeddings
        print(f"🧬 Generating Batch Embeddings for Book {book_id}...")
        await db.books.update_one({"id": book_id}, {"$set": {"processingStep": "rag"}})
        
        updated_book = await db.books.find_one({"id": book_id})
        pages_to_embed = [r for r in updated_book["results"] if r.get("status") == "completed" and "embedding" not in r]
        
        if pages_to_embed:
            text_batch = [r["text"][:2000] for r in pages_to_embed]
            try:
                embedding_results = genai.embed_content(
                    model="models/embedding-001",
                    content=text_batch,
                    task_type="retrieval_document"
                )
                
                for idx, r in enumerate(pages_to_embed):
                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": r["pageNumber"]},
                        {"$set": {"results.$.embedding": embedding_results['embedding'][idx]}}
                    )
                print(f"✅ Batch Embeddings Complete ({len(pages_to_embed)} pages).")
            except Exception as e:
                print(f"❌ Batch Embedding failed: {e}")

        updated_book = await db.books.find_one({"id": book_id})
        sorted_results = sorted(updated_book["results"], key=lambda x: x["pageNumber"])
        raw_combined = "\n".join([r["text"] for r in sorted_results if r["status"] == "completed"])
        full_content = clean_uyghur_text(raw_combined)
        
        completed_count = len([r for r in updated_book["results"] if r["status"] == "completed"])
        final_status = "ready" if completed_count == total_pages else "error"
        
        await db.books.update_one({"id": book_id}, {"$set": {"content": full_content, "status": final_status, "lastUpdated": datetime.now()}})
        print(f"🏁 Book {book_id} finished. Status: {final_status}")
        
    except Exception as e:
        print(f"Parallel task failed for book {book_id}: {e}")
        await db.books.update_one({"id": book_id}, {"$set": {"status": "error"}})
    finally:
        RUNNING_TASKS.discard(book_id)
        if 'doc' in locals():
            doc.close()
