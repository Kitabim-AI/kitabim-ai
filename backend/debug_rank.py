
import motor.motor_asyncio
import asyncio
import os
import numpy as np
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def cosine_similarity(v1, v2):
    dot_product = np.dot(v1, v2)
    norm_a = np.linalg.norm(v1)
    norm_b = np.linalg.norm(v2)
    return dot_product / (norm_a * norm_b)

async def debug_search():
    client = motor.motor_asyncio.AsyncIOMotorClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"))
    db = client.kitabim_ai_db
    
    question = "توغلۇق تۆمۈر كىم؟"
    print(f"Debug Search for: {question}")
    
    # 1. Get embedding for the question
    try:
        query_result = genai.embed_content(
            model="models/embedding-001",
            content=question,
            task_type="retrieval_query"
        )
        query_vector = query_result['embedding']
        print("✅ Computed query embedding.")
    except Exception as e:
        print(f"❌ Costly failure: {e}")
        return

    all_books = await db.books.find().to_list(2000)
    pages_to_search = []
    
    print(f"📚 Loading pages from {len(all_books)} books...")
    for b in all_books:
        # Check if it's Tarikh-i Rashidi to tag it specially
        is_target = "رەشىدىي" in b["title"]
        prefix = "🎯" if is_target else "  "
        if is_target:
            print(f"{prefix} Found Target Book: {b['title']}")
            
        for r in b.get("results", []):
            # Check for truthy embedding (not None, not empty)
            if r.get("status") == "completed" and r.get("embedding"):
                r["bookTitle"] = b["title"]
                r["is_target"] = is_target
                pages_to_search.append(r)

    print(f"📊 Total pages with embeddings: {len(pages_to_search)}")
    
    scored_results = []
    
    keywords = question.lower().split()
    
    for r in pages_to_search:
        # Semantic Score
        sem_score = cosine_similarity(query_vector, r["embedding"])
        
        # Keyword Score (simple count)
        kw_score = sum(1 for k in keywords if k in r["text"].lower())
        
        # Combined logic from main.py (It does separate loops but let's see)
        # In main.py: uses semantic ONLY if available, then fallback to keyword if no semantic results?
        # WAIT! In main.py:
        # if query_vector:
        #    ... append to scored_results ...
        # if not scored_results:
        #    ... fallback to keywords ...
        
        # So it ONLY uses vector search if vectors exist.
        
        scored_results.append({
            "title": r["bookTitle"],
            "page": r["pageNumber"],
            "sem_score": sem_score,
            "kw_score": kw_score,
            "text_preview": r["text"][:50].replace("\n", " "),
            "is_target": r["is_target"]
        })

    # Sort by Semantic Score
    top_sem = sorted(scored_results, key=lambda x: x["sem_score"], reverse=True)[:15]
    
    print("\n🏆 TOP 15 RESULTS (Semantic):")
    for i, r in enumerate(top_sem):
        mark = "🎯" if r["is_target"] else "  "
        print(f"{i+1:2d}. {mark} [{r['sem_score']:.4f}] {r['title']} (p{r['page']}): {r['text_preview']}")

    client.close()

if __name__ == "__main__":
    asyncio.run(debug_search())
