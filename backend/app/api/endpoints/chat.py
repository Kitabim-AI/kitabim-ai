from fastapi import APIRouter, HTTPException
import asyncio
from google.genai import types
from app.models.schemas import ChatRequest, ChatResponse
from app.db.mongodb import db_manager
from app.services.ai_service import cosine_similarity
from app.services import genai_client
from app.core.config import settings
from app.core.prompts import CHAT_SYSTEM_PROMPT

router = APIRouter()

def _is_author_query_ug(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    keywords = [
        "ئاپتورى", "ئاپتور", "يازغۇچىسى", "يازغۇچى", "مۇئەللىپى", "مۇئەللىف",
    ]
    return any(k in q for k in keywords)

def _is_current_volume_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    return "بۇ قىسىمدا" in q

def _is_current_page_query(question: str) -> bool:
    if not question:
        return False
    q = question.strip()
    return "بۇ بەتتە" in q

def _extract_title_ug(question: str) -> str | None:
    if not question:
        return None
    import re
    q = question.strip()

    # Prefer quoted titles
    quote_pairs = [
        ("«", "»"),
        ("《", "》"),
        ("“", "”"),
        ("\"", "\""),
        ("'", "'"),
    ]
    for left, right in quote_pairs:
        pattern = re.compile(re.escape(left) + r"(.+?)" + re.escape(right))
        match = pattern.search(q)
        if match:
            title = match.group(1).strip()
            if title:
                return title

    # Fallback: strip common author-question phrases
    cleanup_patterns = [
        r"كىتاب(نىڭ)?",
        r"دېگەن|دەگەن",
        r"ئاپتورى\s*كىم|ئاپتور\s*كىم",
        r"يازغۇچىسى\s*كىم|يازغۇچى\s*كىم",
        r"مۇئەللىپى\s*كىم|مۇئەللىف\s*كىم",
        r"نېمە|كىم",
        r"[؟?]",
    ]
    cleaned = q
    for pat in cleanup_patterns:
        cleaned = re.sub(pat, " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or None

def _normalize_title_for_tokens(title: str) -> str:
    import re
    t = title or ""
    # Remove common Arabic diacritics
    t = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", t)
    # Replace punctuation with spaces
    t = re.sub(r"[«»“”\"'()\[\]{}،,؟?!؛:]", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t

def _build_title_regex(title: str, allow_optional_hamza: bool) -> str:
    import re
    if not title:
        return ""
    pattern = re.escape(title)
    if allow_optional_hamza:
        pattern = pattern.replace("ئ", "ئ?")
    pattern = re.sub(r"\\s+", r"\\s+", pattern)
    return pattern

async def _find_books_by_title(db, title: str):
    import re
    queries = []
    raw = title.strip()
    if raw:
        queries.append({"title": {"$regex": re.escape(raw), "$options": "i"}})
        hamza_regex = _build_title_regex(raw, allow_optional_hamza=True)
        if hamza_regex and hamza_regex != re.escape(raw):
            queries.append({"title": {"$regex": hamza_regex, "$options": "i"}})

    normalized = _normalize_title_for_tokens(raw)
    if normalized:
        tokens = [t for t in normalized.split() if len(t) > 1]
        if tokens:
            token_query = {"$and": [{"title": {"$regex": re.escape(t), "$options": "i"}} for t in tokens]}
            queries.append(token_query)
            token_query_hamza = {"$and": []}
            for t in tokens:
                if t.startswith("ئ") and len(t) > 1:
                    token_regex = "ئ?" + re.escape(t[1:])
                else:
                    token_regex = re.escape(t).replace("ئ", "ئ?")
                token_query_hamza["$and"].append({"title": {"$regex": token_regex, "$options": "i"}})
            if token_query_hamza["$and"]:
                queries.append(token_query_hamza)

    for query in queries:
        matches = await db.books.find(query).to_list(6)
        if matches:
            return matches
    return []

def _extract_model_text(response):
    try:
        text = response.text
        if text:
            return text
    except Exception as e:
        print(f"⚠️ Response text extraction failed: {e}")

    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        parts = getattr(content, "parts", None) or []
        for part in parts:
            part_text = getattr(part, "text", None)
            if part_text:
                return part_text
    return None

def _build_empty_response_message():
    return (
        "كەچۈرۈڭ، ھازىرچە بۇ سوئالغا جاۋاب چىقارالمايمەن. "
        "سوئالىڭىزنى قايتا ئۇچۇرلۇق ۋە ئېنىق قىلىپ، "
        "كىتابنىڭ نامى ياكى تەپسىلىي مەزمۇنى بىلەن بىرگە سوراپ بېرىڭ."
    )

def _build_rag_prompt(
    context: str,
    question: str,
    strict_no_answer: bool = False,
    suppress_page_notice: bool = False,
) -> str:
    if strict_no_answer:
        instructions = """
Instructions:
1. Primary Goal: Answer the user's question ONLY based on the provided context.
2. If the answer is NOT in the context, respond with exactly: «جاۋاب تېپىلمىدى»
3. Respond ONLY in professional Uyghur (Arabic script).
"""
    else:
        extra_rules = ""
        if suppress_page_notice:
            extra_rules = """
5. If you can answer, do NOT mention whether the current page contained the answer. Just answer directly.
"""
        instructions = """
Instructions:
1. Primary Goal: Answer the user's question based on the provided context.
2. If the context contains the information, cite the book title and page number.
3. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:
   - Politely explain that you couldn't find a specific match in the indexed books.
   - If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor.
4. Respond ONLY in professional Uyghur (Arabic script).
""" + extra_rules

    return f"""
[CONTEXT START]
{context}
[CONTEXT END]

{instructions}

Question: {question}
"""

def _build_books_fallback_context(books, max_chars_per_book: int = 4000, max_books: int = 2) -> str:
    parts = []
    for b in (books or [])[:max_books]:
        title = b.get("title", "نامسىز كىتاب")
        content = (b.get("content") or "").strip()
        if not content:
            pages = [
                r for r in b.get("results", [])
                if r.get("status") == "completed" and r.get("text")
            ]
            pages = sorted(pages, key=lambda x: x.get("pageNumber", 0))[:3]
            content = "\n\n".join([r.get("text", "") for r in pages]).strip()
        if not content:
            continue
        if len(content) > max_chars_per_book:
            content = content[:max_chars_per_book]
        parts.append(f"Book: {title} (overview excerpt):\n{content}")
    return "\n\n---\n\n".join(parts)

@router.post("/", response_model=ChatResponse)
async def chat_with_book_api(req: ChatRequest):
    db = db_manager.db
    try:
        print(
            "📝 Chat request: "
            f"bookId={req.bookId} currentPage={req.currentPage} "
            f"history={len(req.history or [])} question_len={len(req.question or '')}"
        )
        if _is_author_query_ug(req.question):
            extracted_title = _extract_title_ug(req.question)
            if extracted_title:
                print(f"👤 Author query detected, extracted_title='{extracted_title}'")
                matches = await _find_books_by_title(db, extracted_title)
                print(f"👤 Author lookup matches={len(matches)}")
                if not matches:
                    return {
                        "answer": (
                            f"«{extracted_title}» ناملىق كىتابنى تېپىلمىدى. "
                            "لطفەن كىتاب نامىنى تولۇق ياكى باشقا شەكىلدە تەكرار سوراڭ."
                        )
                    }
                book_match = matches[0]
                title = book_match.get("title", "نامسىز كىتاب")
                author = book_match.get("author") or "ئاپتور نامەلۇم"
                return {"answer": f"«{title}» ناملىق ئەسەرنىڭ ئاپتورى {author}."}

            if req.bookId != "global":
                book = await db.books.find_one({"id": req.bookId})
                if book:
                    print("👤 Author query fallback to current book.")
                    title = book.get("title", "نامسىز كىتاب")
                    author = book.get("author") or "ئاپتور نامەلۇم"
                    return {"answer": f"«{title}» ناملىق ئەسەرنىڭ ئاپتورى {author}."}

            return {
                "answer": (
                    "كىتابنىڭ ئاپتورىنى تاپالايمەن، ئەمما كىتاب نامىنى "
                    "بەلگىلەپ بەرگەندىن كېيىنلا جاۋاب بېرەلەيمەن."
                )
            }

        is_global = req.bookId == "global"
        book = None
        if not is_global:
            book = await db.books.find_one({"id": req.bookId})
            if not book:
                raise HTTPException(status_code=404, detail="Book not found")
            print(
                "📚 Book context loaded: "
                f"title='{book.get('title', '')}' author='{book.get('author', '')}'"
            )

        use_current_volume_only = _is_current_volume_query(req.question)
        include_current_page_context = _is_current_page_query(req.question)
        current_page_context = ""
        current_page_only = include_current_page_context
        if include_current_page_context and not is_global and req.currentPage and book:
            page_rec = next((r for r in book.get("results", []) if r["pageNumber"] == req.currentPage), None)
            if page_rec and page_rec.get("text"):
                current_page_context = (
                    f"CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - "
                    f"Book: {book.get('title', 'Unknown')}, Page {req.currentPage}:\n{page_rec['text']}"
                )
            print(
                f"📄 Current page context length={len(current_page_context)} "
                f"found={'yes' if current_page_context else 'no'}"
            )
        if current_page_only:
            print("📄 Scope: current page only (explicit page request).")
        elif use_current_volume_only:
            print("📚 Volume scope: current volume only (explicit volume request).")
        else:
            print("📚 Volume scope: all volumes (title + author).")

        suppress_page_notice = False

        if current_page_only:
            context = current_page_context
            if not context:
                context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            client = genai_client.get_genai_client()
            rag_prompt = _build_rag_prompt(
                context,
                req.question,
                strict_no_answer=False,
                suppress_page_notice=suppress_page_notice,
            )
            print(f"🚀 Calling Gemini Generation Model: {settings.GEMINI_MODEL_NAME}")
            print(f"   Context length: {len(context)} chars")
            print(f"   Prompt length: {len(rag_prompt)} chars")

            contents = [{"role": "user", "parts": [{"text": rag_prompt}]}]
            response = await client.aio.models.generate_content(
                model=settings.GEMINI_MODEL_NAME,
                contents=contents,
            )
            response_text = _extract_model_text(response)
            if not response_text:
                finish_reason = None
                candidates = getattr(response, "candidates", None) or []
                if candidates:
                    finish_reason = getattr(candidates[0], "finish_reason", None)
                print(f"⚠️ Empty response from model. finish_reason={finish_reason}")
                response_text = _build_empty_response_message()
            print(f"   ✅ Response received ({len(response_text)} chars).")
            return {"answer": response_text}

        pages_to_search = []
        related_books = []
        
        if is_global:
            # 1. Identify relevant category
            all_categories = await db.books.distinct("categories")
            relevant_categories = []
            
            if all_categories:
                try:
                    cat_prompt = f"""
                    You are a librarian efficiently categorizing a user's question to find the right section of the library.
                    
                    Available Categories: {all_categories}
                    
                    User's New Question: "{req.question}"
                    
                    Task: Identify which of the available categories are most relevant to this *New Question*.
                    Return ONLY a JSON array of strings, e.g. ["History", "Literature"].
                    If the question is completely general or doesn't fit any category, return [].
                    """
                    print(f"🤖 Calling Gemini Categorization Model: {settings.GEMINI_CATEGORIZATION_MODEL}")
                    print(f"   Query: {req.question}")
                    print(f"   Categories count: {len(all_categories)}")
                    client = genai_client.get_genai_client()
                    cat_result = await client.aio.models.generate_content(
                        model=settings.GEMINI_CATEGORIZATION_MODEL,
                        contents=cat_prompt,
                    )
                    import json
                    text = cat_result.text.strip()
                    if text.startswith("```json"):
                        text = text[7:-3]
                    relevant_categories = json.loads(text)
                    
                    print(f"   💡 Final Categories identified: {relevant_categories}")
                except Exception as e:
                    print(f"⚠️ Categorization failed: {e}")
            
            query = {}
            if relevant_categories and isinstance(relevant_categories, list) and len(relevant_categories) > 0:
                # Use categories as a broad filter first
                query = {"categories": {"$in": relevant_categories}}
            
            # Fetch books based on identified categories
            all_books = await db.books.find(query).to_list(100)
            print(f"📚 Global books fetched: {len(all_books)} (query={query})")
            
            if not all_books:
                # Fallback to all books if no categories matched or no books in categories
                all_books = await db.books.find().sort("lastUpdated", -1).to_list(200)
                print(f"📚 Global fallback books fetched: {len(all_books)}")

            for b in all_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b["title"]
                        pages_to_search.append(r)
        else:
            related_books = [book]
            title = book.get("title")
            author = book.get("author")
            
            if title and not use_current_volume_only:
                sibling_query = {"title": title, "id": {"$ne": req.bookId}}
                if author:
                    sibling_query["author"] = author
                print(f"📚 Volume lookup query: {sibling_query}")
                siblings = await db.books.find(sibling_query).to_list(200)
                if siblings:
                    related_books.extend(siblings)

            for b in related_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b["title"]
                        pages_to_search.append(r)

        print(f"📄 Pages to search: {len(pages_to_search)}")

        # 1. Get embedding for the question
        try:
            print(f"🧬 Generating Embedding for query: '{req.question[:50]}...'")
            print(f"   Embedding model: {settings.GEMINI_EMBEDDING_MODEL}")
            client = genai_client.get_genai_client()
            query_result = await client.aio.models.embed_content(
                model=settings.GEMINI_EMBEDDING_MODEL,
                contents=req.question,
                config=types.EmbedContentConfig(
                    task_type="RETRIEVAL_QUERY",
                    output_dimensionality=768,
                ),
            )
            query_vector = genai_client.extract_embedding_vector(query_result)
            print(f"   ✅ Embedding generated successfully.")
        except Exception as e:
            print(f"⚠️ Embedding failed: {e}")
            query_vector = None
        
        # 2. Search for relevant context
        scored_results = []
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
            
            scored_results.append({
                "text": r["text"],
                "score": score,
                "page": r["pageNumber"],
                "title": r["bookTitle"],
            })
        
        # 3. Sort and take more results for better context
        top_results = [r for r in scored_results if r["score"] > 0.35]
        if not top_results and scored_results:
            top_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[:8]
        else:
            top_results = sorted(top_results, key=lambda x: x["score"], reverse=True)[:12]
        print(f"🔎 Scored results: total={len(scored_results)} top={len(top_results)}")
        
        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)
            
        for r in top_results:
            if is_global or r['page'] != req.currentPage:
                context_parts.append(f"Book: {r['title']}, Page {r['page']}:\n{r['text']}")

        if not top_results and not is_global:
            fallback_context = _build_books_fallback_context(related_books)
            if fallback_context:
                context_parts.append(fallback_context)
                print("📚 Added book-level fallback context.")
        
        context = "\n\n---\n\n".join(context_parts)
        print(f"📦 Final context length={len(context)} chars")
        
        # If no context found, we still proceed but note it in the prompt
        if not context and is_global:
             context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

        # 3. Generate Answer with Gemini
        client = genai_client.get_genai_client()
        
        rag_prompt = _build_rag_prompt(
            context,
            req.question,
            strict_no_answer=False,
            suppress_page_notice=suppress_page_notice,
        )
        print(f"🚀 Calling Gemini Generation Model: {settings.GEMINI_MODEL_NAME}")
        print(f"   Context length: {len(context)} chars")
        print(f"   Prompt length: {len(rag_prompt)} chars")

        contents = [{"role": "user", "parts": [{"text": rag_prompt}]}]
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL_NAME,
            contents=contents,
        )
        response_text = _extract_model_text(response)
        if not response_text:
            finish_reason = None
            candidates = getattr(response, "candidates", None) or []
            if candidates:
                finish_reason = getattr(candidates[0], "finish_reason", None)
            print(f"⚠️ Empty response from model. finish_reason={finish_reason}")
            response_text = _build_empty_response_message()
        print(f"   ✅ Response received ({len(response_text)} chars).")
        return {"answer": response_text}
        
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"❌ Chat Error: {e}")
        raise HTTPException(status_code=500, detail=f"AI Assistant Error: {str(e)}")
