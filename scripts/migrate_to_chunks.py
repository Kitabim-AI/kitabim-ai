import asyncio
import sys
import os
from datetime import datetime
from pymongo import UpdateOne, MongoClient

from dotenv import load_dotenv

# Ensure 'app' is in python path
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages/backend-core"))

# Load env variables explicitly
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages/backend-core/.env"))

from app.core.config import settings
from app.services.chunking_service import chunking_service
from app.langchain.models import GeminiEmbeddings

async def migrate_chunks():
    # Direct Mongo Connection to avoid app dependency complexity if possible, 
    # but we need GeminiEmbeddings from app which handles API keys.
    
    print(f"Connecting to MongoDB: {settings.mongodb_url}")
    client = MongoClient(settings.mongodb_url)
    db = client[settings.database_name]
    
    # ensure indexes on chunks
    print("Ensuring indexes on 'chunks' collection...")
    db.chunks.create_index([("bookId", 1), ("pageNumber", 1)])
    db.chunks.create_index([("bookId", 1)])

    # Find pages that need processing
    # We look for completed pages that are NOT yet marked as 'isIndexed: True'
    query = {
        "status": "completed",
        "isIndexed": {"$ne": True}
    }
    
    total_docs = db.pages.count_documents(query)
    print(f"Found {total_docs} pages to migrate/chunk.")
    
    embedder = GeminiEmbeddings()
    
    # Decrease batch size to avoid Rate Limits (429)
    # Gemini Free Tier limit is often 15 RPM (Requests Per Minute).
    # Processing 50 pages at once might create too many chunks if each chunk was a request, 
    # but aembed_documents batches them. 
    # However, creating embeddings for ~200 chunks at once might hit some payload/token limits or QPM.
    batch_size = 5
    processed_count = 0
    
    # Re-setup for sync cursor iteration
    cursor = db.pages.find(query)
    
    batch_pages = []
    
    import time

    for page in cursor:
        batch_pages.append(page)
        
        if len(batch_pages) >= batch_size:
            while True:
                try:
                    await process_batch(db, batch_pages, embedder)
                    processed_count += len(batch_pages)
                    print(f"Processed {processed_count}/{total_docs} pages...")
                    break
                except Exception as e:
                    print(f"Error processing batch ({len(batch_pages)} pages): {e}")
                    print("Sleeping 60s for rate limit/circuit breaker recovery...")
                    time.sleep(60.0)
            
            batch_pages = []
            # Sleep to respect rate limits (Gemini is sensitive)
            time.sleep(4.0)

    if batch_pages:
        while True:
            try:
                await process_batch(db, batch_pages, embedder)
                processed_count += len(batch_pages)
                print(f"Processed {processed_count}/{total_docs} pages.")
                break
            except Exception as e:
                print(f"Error processing final batch: {e}")
                print("Sleeping 60s...")
                time.sleep(60.0)

    print("Migration complete.")
    client.close()

async def process_batch(db, pages, embedder):
    # Prepare text for embedding
    pairs = []
    for p in pages:
        text = p.get("text", "").strip()
        if text:
            pairs.append((p, text))
            
    if not pairs:
        # Mark empty pages as indexed
        ids = [p["_id"] for p in pages]
        db.pages.update_many({"_id": {"$in": ids}}, {"$set": {"isIndexed": True}})
        return

    # 1. Split Text
    all_chunks_text = []
    page_chunk_counts = []
    
    for p, text in pairs:
        chunks = chunking_service.split_text(text)
        if not chunks:
            chunks = [text]
        all_chunks_text.extend(chunks)
        page_chunk_counts.append(len(chunks))
        
    # 2. Embed
    # raise exception to let main loop handle retry
    embeddings = await embedder.aembed_documents(all_chunks_text)

    # 3. Save Chunks
    current_algo_idx = 0
    ops_chunks = []
    ops_pages = []
    
    for i, (p, _) in enumerate(pairs):
        count = page_chunk_counts[i]
        page_chunks = all_chunks_text[current_algo_idx : current_algo_idx + count]
        page_vectors = embeddings[current_algo_idx : current_algo_idx + count]
        current_algo_idx += count
        
        # Delete old chunks for safety
        db.chunks.delete_many({"bookId": p["bookId"], "pageNumber": p["pageNumber"]})
        
        for idx, (txt, vec) in enumerate(zip(page_chunks, page_vectors)):
            ops_chunks.append({
                "bookId": p["bookId"],
                "pageNumber": p["pageNumber"],
                "chunkIndex": idx,
                "text": txt,
                "embedding": vec,
                "createdAt": datetime.utcnow()
            })
            
        # Update page to isIndexed=True and REMOVE status=embedding to save space
        ops_pages.append(UpdateOne(
            {"_id": p["_id"]},
            {"$set": {"isIndexed": True}, "$unset": {"embedding": ""}}
        ))

    if ops_chunks:
        db.chunks.insert_many(ops_chunks)
        
    if ops_pages:
        db.pages.bulk_write(ops_pages)
        
    # Handle pages that had no text but were in the batch
    processed_ids = set(p["_id"] for p, _ in pairs)
    skipped_ids = [p["_id"] for p in pages if p["_id"] not in processed_ids]
    if skipped_ids:
        db.pages.update_many({"_id": {"$in": skipped_ids}}, {"$set": {"isIndexed": True}})

if __name__ == "__main__":
    asyncio.run(migrate_chunks())
