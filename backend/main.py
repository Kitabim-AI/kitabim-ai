from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import motor.motor_asyncio
import os
import fitz # PyMuPDF
import google.generativeai as genai
import asyncio
import hashlib
from dotenv import load_dotenv
import io
import random
import numpy as np
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from prompts import OCR_PROMPT, CHAT_SYSTEM_PROMPT

load_dotenv()

# Gemini AI Configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("WARNING: GEMINI_API_KEY not found in environment")
else:
    genai.configure(api_key=GEMINI_API_KEY)

# MongoDB Connection
MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URL)
db = client.kitabim_ai_db

# Task Locking to prevent duplicates
RUNNING_TASKS = set()

# Directory setup
UPLOADS_DIR = "uploads"
COVERS_DIR = "covers"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(COVERS_DIR, exist_ok=True)

class ExtractionResult(BaseModel):
    pageNumber: int
    text: Optional[str] = None
    status: str
    error: Optional[str] = None

class Book(BaseModel):
    id: str
    contentHash: str
    title: str
    author: str
    totalPages: int
    content: Optional[str] = None
    results: List[ExtractionResult]
    status: str
    uploadDate: datetime
    lastUpdated: Optional[datetime] = None
    coverUrl: Optional[str] = None
    processingStep: Optional[str] = "ocr" # "ocr" or "rag"
    tags: List[str] = []

class PaginatedBooks(BaseModel):
    books: List[Book]
    total: int
    page: int
    pageSize: int

def clean_uyghur_text(text: str) -> str:
    if not text:
        return ""
    import re
    
    # 1. Join words split by hyphen/dash at the end of a line
    # Handle both - and — and – and _ (sometimes OCR thinks it is an underscore)
    # Join WITHOUT space only if the hyphen is directly attached to the word (likely split)
    text = re.sub(r'(\w)[-—–_]\s*\n\s*(\w)', r'\1\2', text)
    
    # 2. Standardize hyphens/dashes at line ends (catch-all for remaining split hyphens)
    # But only if it's attached to a word character.
    text = re.sub(r'(\w)[-—–_]\s*\n\s*', r'\1', text)
    
    # 3. Clean up tatweels if they are at the end of a line (filler)
    text = re.sub(r'ـ+\s*\n\s*', '\n', text)
    
    # 4. Split by paragraphs (double newlines or more)
    paragraphs = re.split(r'\n\s*\n', text)
    cleaned_paragraphs = []
    
    for p in paragraphs:
        if not p.strip(): continue
        
        # Split into individual lines and clean them
        lines = [l.strip() for l in p.split('\n') if l.strip()]
        if not lines: continue
        
        result_para = ""
        for i in range(len(lines)):
            line = lines[i]
            if i < len(lines) - 1:
                next_line = lines[i+1]
                
                # If current line ends with sentence punctuation or quotes, keep the break
                # Uyghur enders: . ؟ ! : ؛ or quotes/brackets » " ” ) ] } ﴾ ﴿ …
                # We also check if the NEXT line starts with a bullet/dash or number, 
                # which usually indicates a new logical line even if punctuation is missing.
                is_ending = re.search(r'[.؟!:؛»"”)\]}﴾﴿…]\s*$', line)
                is_new_item = re.match(r'^\s*([-—–*•\d])', next_line)
                
                if is_ending or is_new_item:
                    result_para += line + "\n"
                else:
                    # Otherwise join with a space to flow the sentence continuously
                    result_para += line + " "
            else:
                # Last line of the block
                result_para += line
        
        cleaned_paragraphs.append(result_para.strip())
        
    return "\n\n".join(cleaned_paragraphs)

class ChatRequest(BaseModel):
    bookId: str
    question: str
    history: List[dict] = []
    currentPage: Optional[int] = None

async def process_pdf_task(book_id: str):
    if book_id in RUNNING_TASKS:
        print(f"⏩ Task for {book_id} is already running. Skipping duplicate call.")
        return
        
    RUNNING_TASKS.add(book_id)
    try:
        file_path = os.path.join(UPLOADS_DIR, f"{book_id}.pdf")
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
        cover_path = os.path.join(COVERS_DIR, f"{book_id}.jpg")
        if not os.path.exists(cover_path) and total_pages > 0:
            try:
                first_page = doc.load_page(0)
                pix = first_page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5)) # Low res for thumbnail
                pix.save(cover_path)
                await db.books.update_one(
                    {"id": book_id},
                    {"$set": {"coverUrl": f"/api/covers/{book_id}.jpg"}}
                )
            except Exception as e:
                print(f"Failed to extract cover for {book_id}: {e}")

        missing_embeddings = any(r.get("status") == "completed" and "embedding" not in r for r in results)
        pages_to_process = [r["pageNumber"] for r in results if r["status"] != "completed" or (r.get("status") == "completed" and "embedding" not in r)]
        
        if not pages_to_process:
            await db.books.update_one({"id": book_id}, {"$set": {"status": "ready"}})
            return

        print(f"📦 Starting Parallel Process for Book {book_id}: {len(pages_to_process)} tasks (Interrupted or RAG Retrofit).")
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        model = genai.GenerativeModel(model_name)
        
        # PARALLEL CONFIG
        max_parallel = int(os.getenv("MAX_PARALLEL_PAGES", "1"))
        semaphore = asyncio.Semaphore(max_parallel)
        
        async def process_page(page_num):
            async with semaphore:
                await asyncio.sleep(random.uniform(0.1, 0.5))
                
                try:
                    # 1. Check if OCR was already done (for retrofitting)
                    current_book = await db.books.find_one({"id": book_id})
                    page_record = next((r for r in current_book["results"] if r["pageNumber"] == page_num), None)
                    
                    existing_text = page_record.get("text", "") if page_record else ""
                    # 1. OPTIMIZATION: If text is very short (<40 chars), it might be an incomplete OCR. 
                    # We treat it as NOT done so it gets a second chance.
                    already_ocr = (page_record.get("status") == "completed" and len(existing_text) > 40) if page_record else False

                    # 2. Mark as processing
                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": page_num},
                        {"$set": {"results.$.status": "processing"}}
                    )

                    success = already_ocr
                    page_text = existing_text

                    if not already_ocr:
                        # Full OCR via AI needed
                        page = doc.load_page(page_num - 1)
                        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5)) # Optimized resolution
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
            
        # 4. OPTIMIZATION: BATCH EMBEDDINGS (RAG SPEEDUP)
        print(f"🧬 Generating Batch Embeddings for Book {book_id}...")
        await db.books.update_one({"id": book_id}, {"$set": {"processingStep": "rag"}})
        
        updated_book = await db.books.find_one({"id": book_id})
        pages_to_embed = [r for r in updated_book["results"] if r.get("status") == "completed" and "embedding" not in r]
        
        if pages_to_embed:
            # Gemini supports batch embedding calls
            text_batch = [r["text"][:2000] for r in pages_to_embed] # Limit text length for embedding safety
            try:
                embedding_results = genai.embed_content(
                    model="models/embedding-001",
                    content=text_batch,
                    task_type="retrieval_document"
                )
                
                # Bulk update MongoDB
                for idx, r in enumerate(pages_to_embed):
                    await db.books.update_one(
                        {"id": book_id, "results.pageNumber": r["pageNumber"]},
                        {"$set": {"results.$.embedding": embedding_results['embedding'][idx]}}
                    )
                print(f"✅ Batch Embeddings Complete ({len(pages_to_embed)} pages).")
            except Exception as e:
                print(f"❌ Batch Embedding failed: {e}")

        # Finalize full content
        updated_book = await db.books.find_one({"id": book_id})
        sorted_results = sorted(updated_book["results"], key=lambda x: x["pageNumber"])
        # Combine pages into a single stream with single newlines to allow clean_uyghur_text to handle joins
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

# Lifecycle Management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: MongoDB Connection
    try:
        await client.admin.command('ismaster')
        print("Successfully connected to MongoDB")
        
        # Resume interrupted or retrofit books
        print("🔍 Checking for books needing resume or retrofitting...")
        all_books = await db.books.find().to_list(2000)
        for book in all_books:
            # RETROFIT: Ensure 'id' field exists
            if "id" not in book:
                book_id = str(book["_id"])
                print(f"🆔 Retrofitting missing ID for book: {book.get('title', 'Unknown')} -> {book_id}")
                await db.books.update_one({"_id": book["_id"]}, {"$set": {"id": book_id}})
                book["id"] = book_id

            needs_resume = book["status"] == "processing"
            needs_cover = book["status"] == "ready" and (not book.get("coverUrl") or not os.path.exists(os.path.join(COVERS_DIR, f"{book['id']}.jpg")))
            needs_rag = book["status"] == "ready" and any(r.get("status") == "completed" and "embedding" not in r for r in book.get("results", []))
            
            if needs_resume or needs_cover or needs_rag:
                reason = "Resume" if needs_resume else "Cover Retrofit" if needs_cover else "RAG Retrofit"
                print(f"♻️ Triggering task for Book {book['id']} ({reason})")
                asyncio.create_task(process_pdf_task(book["id"]))
                
    except Exception as e:
        print(f"Could not connect to MongoDB: {e}")
    yield
    # Shutdown: Clean up resources if needed
    client.close()

app = FastAPI(lifespan=lifespan)

# Mounts and Routes
app.mount("/api/covers", StaticFiles(directory=COVERS_DIR), name="covers")

async def get_embedding(text: str):
    try:
        if not text.strip():
            return None
        # Clean text slightly for embedding
        clean_text = text.replace("\n", " ")[:2000] 
        result = genai.embed_content(
            model="models/embedding-001",
            content=clean_text,
            task_type="retrieval_document"
        )
        return result['embedding']
    except Exception as e:
        print(f"Embedding error: {e}")
        return None

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_a = np.linalg.norm(v1)
    norm_b = np.linalg.norm(v2)
    return dot_product / (norm_a * norm_b)

@app.get("/api/books", response_model=PaginatedBooks)
async def get_books(
    page: int = 1, 
    pageSize: int = 10, 
    q: Optional[str] = None,
    sortBy: str = "title",
    order: int = 1 # 1 for asc, -1 for desc
):
    print(f"FETCH BOOKS (Light): page={page}, pageSize={pageSize}, q={q}, sortBy={sortBy}, order={order}")
    skip = (page - 1) * pageSize
    
    query = {}
    if q:
        query = {
            "$or": [
                {"title": {"$regex": q, "$options": "i"}},
                {"author": {"$regex": q, "$options": "i"}}
            ]
        }
    
    total = await db.books.count_documents(query)
    
    # EXCLUDE heavy fields: content, results.text, results.embedding
    projection = {
        "content": 0,
        "results.text": 0,
        "results.embedding": 0
    }
    
    books_cursor = db.books.find(query, projection).sort([(sortBy, order), ("_id", -1)]).skip(skip).limit(pageSize)
    books_list = await books_cursor.to_list(pageSize)
    
    formatted_books = []
    for b in books_list:
        if "_id" in b and "id" not in b:
            b["id"] = str(b["_id"])
        formatted_books.append(b)

    return {
        "books": formatted_books,
        "total": total,
        "page": page,
        "pageSize": pageSize
    }

@app.get("/api/books/{book_id}", response_model=Book)
async def get_book(book_id: str):
    book = await db.books.find_one({"id": book_id}, {"results.embedding": 0})
    if book:
        if "_id" in book and "id" not in book:
            book["id"] = str(book["_id"])
        return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.get("/api/books/hash/{content_hash}", response_model=Book)
async def get_book_by_hash(content_hash: str):
    book = await db.books.find_one({"contentHash": content_hash})
    if book:
        return book
    raise HTTPException(status_code=404, detail="Book not found")

@app.post("/api/books/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    pdf_bytes = await file.read()
    content_hash = hashlib.sha256(pdf_bytes).hexdigest()
    
    # Check if exists
    existing = await db.books.find_one({"contentHash": content_hash})
    if existing:
        return {"bookId": existing["id"], "status": "existing"}
        
    book_id = hashlib.md5(f"{file.filename}{datetime.now()}".encode()).hexdigest()[:12]
    
    # Save file to disk
    file_path = os.path.join(UPLOADS_DIR, f"{book_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(pdf_bytes)

    now = datetime.now()
    new_book = {
        "id": book_id,
        "contentHash": content_hash,
        "title": file.filename.replace(".pdf", ""),
        "author": "Unknown Author",
        "totalPages": 0,
        "content": "",
        "results": [],
        "status": "processing",
        "uploadDate": now,
        "lastUpdated": now
    }
    
    await db.books.insert_one(new_book)
    background_tasks.add_task(process_pdf_task, book_id)
    
    return {"bookId": book_id, "status": "started"}

@app.post("/api/books/{book_id}/reprocess")
async def reprocess_book(book_id: str, background_tasks: BackgroundTasks):
    book = await db.books.find_one({"id": book_id})
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")
    
    if book["status"] == "processing":
        return {"status": "already_processing"}

    await db.books.update_one({"id": book_id}, {"$set": {"status": "processing", "lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "reprocessing_started"}

@app.post("/api/books/{book_id}/pages/{page_num}/reset")
async def reset_page(book_id: str, page_num: int, background_tasks: BackgroundTasks):
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {"$set": {"results.$.status": "pending", "results.$.text": ""}}
    )
    await db.books.update_one({"id": book_id}, {"$set": {"status": "processing", "lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "page_reset_started"}

@app.post("/api/books/{book_id}/pages/{page_num}/update")
async def update_page_text(book_id: str, page_num: int, payload: dict, background_tasks: BackgroundTasks):
    new_text = payload.get("text", "")
    # Update text and INVALIDATE embedding (forcing RAG regeneration)
    await db.books.update_one(
        {"id": book_id, "results.pageNumber": page_num},
        {
            "$set": {
                "results.$.text": new_text,
                "results.$.status": "completed"
            },
            "$unset": {
                "results.$.embedding": ""
            }
        }
    )
    # Trigger RAG refresh task
    await db.books.update_one({"id": book_id}, {"$set": {"lastUpdated": datetime.now()}})
    background_tasks.add_task(process_pdf_task, book_id)
    return {"status": "page_updated", "requires_rag": True}

@app.post("/api/chat")
async def chat_with_book_api(req: ChatRequest):
    try:
        pages_to_search = []
        is_global = req.bookId == "global"
        
        if is_global:
            print(f"🌍 Global Chat Request: Question='{req.question[:50]}...'")
            all_books = await db.books.find().to_list(2000)
            for b in all_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b["title"]
                        pages_to_search.append(r)
        else:
            book = await db.books.find_one({"id": req.bookId})
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
            
            # SERIES EXPANSION: Check for tags
            related_books = [book]
            tags = book.get("tags", [])
            
            if tags:
                print(f"� Book has tags {tags}. Expanding search to related books...")
                # Find all other books that share AT LEAST ONE of these tags
                siblings = await db.books.find({
                    "tags": {"$in": tags},
                    "id": {"$ne": req.bookId} # Exclude current book to avoid duplication
                }).to_list(100)
                
                if siblings:
                    print(f"   found {len(siblings)} sibling books: {[b['title'] for b in siblings]}")
                    related_books.extend(siblings)

            print(f"�💬 Chat Request: Book={req.bookId} (Scope: {len(related_books)} books), Question='{req.question[:50]}...'")
            
            pages_to_search = []
            for b in related_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b["title"]
                        pages_to_search.append(r)

        # 1. Get embedding for the question
        try:
            query_result = await asyncio.to_thread(
                genai.embed_content,
                model="models/embedding-001",
                content=req.question,
                task_type="retrieval_query"
            )
            query_vector = query_result['embedding']
        except Exception as e:
            print(f"⚠️ Embedding failed: {e}")
            query_vector = None
        
        # 2. Search for relevant context
        scored_results = []
        current_page_context = ""
        
        # Pre-process Current Page (Only if not global)
        if not is_global and req.currentPage:
            page_rec = next((r for r in pages_to_search if r["pageNumber"] == req.currentPage), None)
            if page_rec and page_rec.get("text"):
                current_page_context = f"CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - Book: {page_rec['bookTitle']}, Page {req.currentPage}:\n{page_rec['text']}"

        # HYBRID SEARCH: Combine Semantic + Keyword
        keywords = req.question.split() # Simple split for now
        
        for r in pages_to_search:
            score = 0.0
            
            # 1. Semantic Score
            if query_vector and r.get("embedding"):
                # Cosine similarity usually returns 0.0-1.0. 
                # We expect values around 0.7-0.8 for "meh" matches and >0.85 for good ones with this model.
                score = cosine_similarity(query_vector, r["embedding"])
            
            # 2. Keyword Boosting
            # Boosting ensures that if the specific named entity is found, this page rockets to the top
            # even if the semantic embedding is fuzzy.
            txt = r.get("text", "")
            match_count = 0
            for k in keywords:
                if len(k) > 2 and k in txt: # Ignore tiny words
                    match_count += 1
            
            if match_count > 0:
                score += (match_count * 0.15) # +0.15 per keyword match is significant
            
            # Only keep results that have some relevance
            if score > 0.0:
                 scored_results.append({ "text": r["text"], "score": score, "page": r["pageNumber"], "title": r["bookTitle"] })
        
        # Sort and take top 7 most relevant pages (More context for global)
        top_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[:7]
        
        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)
            
        for r in top_results:
            # Avoid duplicate current page
            if is_global or r['page'] != req.currentPage:
                context_parts.append(f"Book: {r['title']}, Page {r['page']}:\n{r['text']}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        # 3. Generate Answer with Gemini
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        model = genai.GenerativeModel(model_name)
        
        # Prepare history for context
        chat_history = []
        if req.history:
             # Limit to last 6 messages to keep context window manageable
            for h in req.history[-6:]:
                role = "user" if h.get("role") == "user" else "model"
                chat_history.append({"role": role, "parts": [h.get("text")]})
        
        # Start chat with system instruction
        chat = model.start_chat(history=chat_history)
        
        # We inject the RAG context into the USER's prompt invisibly so the model knows what to answer from.
        # This is better than putting it in system prompt because it changes per-turn.
        rag_prompt = f"""
[CONTEXT START]
{context}
[CONTEXT END]

Based on the context above (if relevant), answer the user's question.
Question: {req.question}
"""
        response = await chat.send_message_async(rag_prompt)
        return {"answer": response.text}
        
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {str(e)}")

@app.post("/api/books")
async def create_book(book: Book, background_tasks: BackgroundTasks):
    await db.books.update_one(
        {"id": book.id},
        {"$set": book.dict()},
        upsert=True
    )
    # Trigger RAG/Retrofit just in case text changed
    background_tasks.add_task(process_pdf_task, book.id)
    return {"status": "success"}

from bson import ObjectId

@app.put("/api/books/{book_id}")
async def update_book(book_id: str, book_update: dict):
    # Try both custom id and MongoDB _id
    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except:
            pass
            
    result = await db.books.update_one(query, {"$set": book_update})
    if result.matched_count:
        return {"status": "updated", "modified": result.modified_count > 0}
    raise HTTPException(status_code=404, detail="Book not found")

@app.delete("/api/books/{book_id}")
async def delete_book(book_id: str):
    # Remove file from disk
    file_path = os.path.join(UPLOADS_DIR, f"{book_id}.pdf")
    if os.path.exists(file_path):
        os.remove(file_path)

    query = {"$or": [{"id": book_id}]}
    if len(book_id) == 24:
        try:
            query["$or"].append({"_id": ObjectId(book_id)})
        except:
            pass

    result = await db.books.delete_one(query)
    if result.deleted_count:
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Book not found")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
