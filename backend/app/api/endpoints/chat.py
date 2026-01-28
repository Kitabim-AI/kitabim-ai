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
                    # Feed the last few messages for context to handle follow-up questions
                    history_context = ""
                    if req.history:
                        history_context = "\nRecent Conversation:\n" + "\n".join([f"{h.get('role')}: {h.get('text')}" for h in req.history[-3:]])

                    cat_prompt = f"""
                    You are a librarian efficiently categorizing a user's question to find the right section of the library.
                    {history_context}
                    
                    Available Categories: {all_categories}
                    
                    User's New Question: "{req.question}"
                    
                    Task: Identify which of the available categories are most relevant to this *New Question*.
                    If the question is a follow-up (e.g., "who are his parents?"), use the conversation history to determine the right category.
                    Return ONLY a JSON array of strings, e.g. ["History", "Literature"].
                    If the question is completely general or doesn't fit any category even with context, return [].
                    """
                    print(f"🤖 Calling Gemini Categorization Model: {settings.GEMINI_CATEGORIZATION_MODEL}")
                    print(f"   Query: {req.question}")
                    cat_model = genai.GenerativeModel(settings.GEMINI_CATEGORIZATION_MODEL)
                    cat_result = await cat_model.generate_content_async(cat_prompt)
                    import json
                    text = cat_result.text.strip()
                    if text.startswith("```json"):
                        text = text[7:-3]
                    relevant_categories = json.loads(text)
                    
                    # 🔄 Fallback: If current question yields no categories, try categorizing the previous user question
                    if not relevant_categories and req.history:
                        last_user_msg = next((h.get('text') for h in reversed(req.history) if h.get('role') == 'user'), None)
                        if last_user_msg and last_user_msg != req.question:
                            print(f"   🔄 Empty result. Re-trying with previous question: '{last_user_msg[:40]}...'")
                            fallback_prompt = f"""
                            Available Categories: {all_categories}
                            Previous Question: "{last_user_msg}"
                            Identify the relevant categories for this previous question.
                            Return ONLY a JSON array of strings.
                            """
                            fb_result = await cat_model.generate_content_async(fallback_prompt)
                            fb_text = fb_result.text.strip()
                            if fb_text.startswith("```json"): fb_text = fb_text[7:-3]
                            relevant_categories = json.loads(fb_text)

                    print(f"   💡 Final Categories identified: {relevant_categories}")
                except Exception as e:
                    print(f"⚠️ Categorization failed: {e}")
            
            query = {}
            if relevant_categories and isinstance(relevant_categories, list) and len(relevant_categories) > 0:
                 # Use categories as a broad filter first
                 query = {"categories": {"$in": relevant_categories}}
            
            # Fetch books based on identified categories
            all_books = await db.books.find(query).to_list(100)
            
            if not all_books:
                 # Fallback to all books if no categories matched or no books in categories
                 all_books = await db.books.find().sort("lastUpdated", -1).to_list(200)

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
            print(f"🧬 Generating Embedding for query: '{req.question[:50]}...'")
            query_result = await asyncio.to_thread(
                genai.embed_content,
                model=settings.GEMINI_EMBEDDING_MODEL,
                content=req.question,
                task_type="retrieval_query",
                output_dimensionality=768
            )
            query_vector = query_result['embedding']
            print(f"   ✅ Embedding generated successfully.")
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

        import re
        # Clean keywords: keep letters, numbers, and common whitespace. 
        # Standardize for Uyghur script.
        keywords = [re.sub(r'[^\w]', '', k, flags=re.UNICODE).strip() for k in req.question.split()]
        keywords = [k for k in keywords if len(k) > 2] # Only meaningful keywords
        
        for r in pages_to_search:
            score = 0.0
            if query_vector and r.get("embedding"):
                score = cosine_similarity(query_vector, r["embedding"])
            
            txt = r.get("text", "")
            match_count = 0
            # Faster keyword scanning
            for k in keywords:
                if k in txt:
                    match_count += 1
            
            if match_count > 0:
                score += (match_count * 0.15)
            
            if score > 0.35: # Lowered threshold for better recall
                 scored_results.append({ "text": r["text"], "score": score, "page": r["pageNumber"], "title": r["bookTitle"] })
        
        # 3. Sort and take more results for better context
        top_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[:12]
        
        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)
            
        for r in top_results:
            if is_global or r['page'] != req.currentPage:
                context_parts.append(f"Book: {r['title']}, Page {r['page']}:\n{r['text']}")
        
        context = "\n\n---\n\n".join(context_parts)
        
        # If no context found, we still proceed but note it in the prompt
        if not context and is_global:
             context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

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
1. Primary Goal: Answer the user's question based on the provided context.
2. If the context contains the information, cite the book title and page number.
3. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:
   - Politely explain that you couldn't find a specific match in the indexed books.
   - If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor.
4. Respond ONLY in professional Uyghur (Arabic script).

Question: {req.question}
"""
        print(f"🚀 Calling Gemini Generation Model: {settings.GEMINI_MODEL_NAME}")
        print(f"   History length: {len(chat_history)} messages")
        print(f"   Context length: {len(context)} chars")
        
        response = await chat.send_message_async(rag_prompt)
        print(f"   ✅ Response received ({len(response.text)} chars).")
        return {"answer": response.text}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {str(e)}")
