from fastapi import APIRouter, HTTPException
import asyncio
import google.generativeai as genai
from app.models.schemas import ChatRequest, ChatResponse
from app.db.mongodb import db_manager
from app.services.ai_service import cosine_similarity
from app.core.config import settings
from app.core.prompts import CHAT_SYSTEM_PROMPT

router = APIRouter()

@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(req: ChatRequest):
    db = db_manager.db
    try:
        pages_to_search = []
        is_global = req.bookId == "global"
        
        if is_global:
            # 1. Identify relevant category
            all_categories = await db.books.distinct("categories")
            relevant_categories = []
            
            if all_categories:
                try:
                    cat_model = genai.GenerativeModel(settings.GEMINI_CATEGORIZATION_MODEL)
                    cat_prompt = f"""
                    You are a librarian efficiently categorizing a user's question to find the right section of the library.
                    
                    Available Categories: {all_categories}
                    
                    User's Question: "{req.question}"
                    
                    Task: Identify which of the available categories are most relevant to this question.
                    Return ONLY a JSON array of strings, e.g. ["History", "Literature"].
                    If the question is general or doesn't fit any specific category, return [].
                    """
                    cat_result = await cat_model.generate_content_async(cat_prompt)
                    import json
                    text = cat_result.text.strip()
                    if text.startswith("```json"):
                        text = text[7:-3]
                    relevant_categories = json.loads(text)
                except Exception as e:
                    print(f"⚠️ Categorization failed: {e}")
            
            query = {}
            if relevant_categories and isinstance(relevant_categories, list) and len(relevant_categories) > 0:
                 query = {"categories": {"$in": relevant_categories}}
            
            all_books = await db.books.find(query).to_list(2000)
            
            if not all_books and relevant_categories:
                 # Fallback to all books if category filtering was too strict
                 all_books = await db.books.find().to_list(200)

            for b in all_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b["title"]
                        pages_to_search.append(r)
        else:
            book = await db.books.find_one({"id": req.bookId})
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
            
            related_books = [book]
            series = book.get("series", [])
            
            if series:
                siblings = await db.books.find({
                    "series": {"$in": series},
                    "id": {"$ne": req.bookId}
                }).to_list(100)
                
                if siblings:
                    related_books.extend(siblings)

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
        
        if not is_global and req.currentPage:
            page_rec = next((r for r in pages_to_search if r["pageNumber"] == req.currentPage), None)
            if page_rec and page_rec.get("text"):
                current_page_context = f"CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - Book: {page_rec['bookTitle']}, Page {req.currentPage}:\n{page_rec['text']}"

        keywords = req.question.split()
        
        for r in pages_to_search:
            score = 0.0
            if query_vector and r.get("embedding"):
                score = cosine_similarity(query_vector, r["embedding"])
            
            txt = r.get("text", "")
            match_count = 0
            for k in keywords:
                if len(k) > 2 and k in txt:
                    match_count += 1
            
            if match_count > 0:
                score += (match_count * 0.15)
            
            if score > 0.45: # Increased threshold for stricter relevance
                 scored_results.append({ "text": r["text"], "score": score, "page": r["pageNumber"], "title": r["bookTitle"] })
        
        top_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[:7]
        
        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)
            
        for r in top_results:
            if is_global or r['page'] != req.currentPage:
                context_parts.append(f"Book: {r['title']}, Page {r['page']}:\n{r['text']}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        if not context and is_global:
             return {"answer": "I could not find any relevant information in the library matching your question. Please try asking about a different topic or rephrasing your query."}

        # 3. Generate Answer with Gemini
        model = genai.GenerativeModel(settings.GEMINI_MODEL_NAME)
        
        chat_history = []
        if req.history:
            for h in req.history[-6:]:
                role = "user" if h.get("role") == "user" else "model"
                chat_history.append({"role": role, "parts": [h.get("text")]})
        
        chat = model.start_chat(history=chat_history)
        
        rag_prompt = f"""
[CONTEXT START]
{context}
[CONTEXT END]

Instructions:
1. Answer the user's question based ONLY on the provided context above. 
2. If the context does not contain the answer, state clearly that you cannot find the information in the available books.
3. Do NOT make up facts or use outside knowledge to answer the specific question if it's not in the context.
4. cite the book title and page number if possible.

Question: {req.question}
"""
        response = await chat.send_message_async(rag_prompt)
        return {"answer": response.text}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {str(e)}")
