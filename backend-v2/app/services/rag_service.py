from __future__ import annotations

import json
import re
from typing import List, Optional

import numpy as np

from app.core.config import settings
from app.core.prompts import CATEGORY_PROMPT, RAG_PROMPT_TEMPLATE
from app.models.schemas import ChatRequest
from app.services.langchain_service import GeminiEmbeddings, PromptChainFactory


class RAGService:
    def __init__(self) -> None:
        self.embeddings = GeminiEmbeddings()
        self.category_chain = PromptChainFactory.build_text_chain(
            CATEGORY_PROMPT,
            settings.gemini_categorization_model,
        )
        self.answer_chain = PromptChainFactory.build_text_chain(
            RAG_PROMPT_TEMPLATE,
            settings.gemini_model_name,
        )

    @staticmethod
    def _is_author_query_ug(question: str) -> bool:
        if not question:
            return False
        q = question.strip()
        keywords = ["ئاپتورى", "ئاپتور", "يازغۇچىسى", "يازغۇچى", "مۇئەللىپى", "مۇئەللىف"]
        return any(k in q for k in keywords)

    @staticmethod
    def _is_current_volume_query(question: str) -> bool:
        if not question:
            return False
        q = question.strip()
        keywords = ["ئۇشبۇ تومدا", "ئۇشبۇ قىسىمدا", "مەزكور تومدا", "مەزكور قىسىمدا", "بۇ تومدا", "بۇ قىسىمدا"]
        return any(k in q for k in keywords)

    @staticmethod
    def _is_current_page_query(question: str) -> bool:
        if not question:
            return False
        keywords = ["ئۇشبۇ بەتتە", "مەزكور بەتتە", "بۇ بەتتە"]
        return any(k in q for k in keywords)

    @staticmethod
    def _extract_title_ug(question: str) -> Optional[str]:
        if not question:
            return None

        q = question.strip()
        quote_pairs = [("«", "»"), ("《", "》"), ("“", "”"), ('"', '"'), ("'", "'")]
        for left, right in quote_pairs:
            pattern = re.compile(re.escape(left) + r"(.+?)" + re.escape(right))
            match = pattern.search(q)
            if match:
                title = match.group(1).strip()
                if title:
                    return title

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

    @staticmethod
    def _normalize_title_for_tokens(title: str) -> str:
        t = title or ""
        t = re.sub(r"[\u064B-\u065F\u0670\u06D6-\u06ED]", "", t)
        t = re.sub(r"[«»“”\"'()\[\]{}،,؟?!؛:]", " ", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t

    @staticmethod
    def _build_title_regex(title: str, allow_optional_hamza: bool) -> str:
        if not title:
            return ""
        pattern = re.escape(title)
        if allow_optional_hamza:
            pattern = pattern.replace("ئ", "ئ?")
        pattern = re.sub(r"\\s+", r"\\s+", pattern)
        return pattern

    async def _find_books_by_title(self, db, title: str) -> List[dict]:
        queries = []
        raw = title.strip()
        if raw:
            queries.append({"title": {"$regex": re.escape(raw), "$options": "i"}})
            hamza_regex = self._build_title_regex(raw, allow_optional_hamza=True)
            if hamza_regex and hamza_regex != re.escape(raw):
                queries.append({"title": {"$regex": hamza_regex, "$options": "i"}})

        normalized = self._normalize_title_for_tokens(raw)
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

    @staticmethod
    def _build_empty_response_message() -> str:
        return (
            "كەچۈرۈڭ، ھازىرچە بۇ سوئالغا جاۋاب بېرەلمەيمەن. "
            "سوئالىڭىزنى قايتا تەپسىلى ۋە ئېنىق قىلىپ، "
            "كىتابنىڭ نامى ياكى تەپسىلىي مەزمۇنى بىلەن بىرگە سوراپ بېرىڭ."
        )

    @staticmethod
    def _build_instructions(strict_no_answer: bool, suppress_page_notice: bool) -> str:
        if strict_no_answer:
            return (
                "Instructions:\n"
                "1. Primary Goal: Answer the user's question ONLY based on the provided context.\n"
                "2. If the answer is NOT in the context, respond with exactly: جاۋاب تېپىلمىدى\n"
                "3. Respond ONLY in professional Uyghur (Arabic script)."
            )
        extra_rules = ""
        if suppress_page_notice:
            extra_rules = "\n5. If you can answer, do NOT mention whether the current page contained the answer."
        return (
            "Instructions:\n"
            "1. Primary Goal: Answer the user's question based on the provided context.\n"
            "2. If the context contains the information, cite the book title and page number.\n"
            "3. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:\n"
            "   - Politely explain that you couldn't find a specific match in the indexed books.\n"
            "   - If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor.\n"
            "4. Respond ONLY in professional Uyghur (Arabic script)."
            + extra_rules
        )

    @staticmethod
    def _build_books_fallback_context(books, max_chars_per_book: int = 4000, max_books: int = 2) -> str:
        parts = []
        for b in (books or [])[:max_books]:
            title = b.get("title", "نامسىز كىتاب")
            content = (b.get("content") or "").strip()
            if not content:
                pages = [
                    r
                    for r in b.get("results", [])
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

    @staticmethod
    def _cosine_similarity(v1: List[float], v2: List[float]) -> float:
        if not v1 or not v2:
            return 0.0
        a = np.array(v1)
        b = np.array(v2)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    @staticmethod
    def _extract_keywords(question: str) -> List[str]:
        tokens = [re.sub(r"[^\w]", "", k, flags=re.UNICODE).strip() for k in question.split()]
        return [k for k in tokens if len(k) > 2]

    async def _categorize_question(self, question: str, categories: List[str]) -> List[str]:
        if not categories:
            return []
        response_text = await self.category_chain.ainvoke(
            {
                "categories": categories,
                "question": question,
            }
        )
        cleaned = response_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:-3].strip()
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return [str(x) for x in result]
        except json.JSONDecodeError:
            return []
        return []

    async def _generate_answer(
        self,
        context: str,
        question: str,
        strict_no_answer: bool = False,
        suppress_page_notice: bool = False,
    ) -> str:
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice)
        response_text = await self.answer_chain.ainvoke(
            {
                "context": context,
                "instructions": instructions,
                "question": question,
            }
        )
        return response_text.strip() or self._build_empty_response_message()

    async def answer_question(self, req: ChatRequest, db) -> str:
        if self._is_author_query_ug(req.question):
            extracted_title = self._extract_title_ug(req.question)
            if extracted_title:
                matches = await self._find_books_by_title(db, extracted_title)
                if not matches:
                    return (
                        f"«{extracted_title}» ناملىق كىتابنى تېپىلمىدى. "
                        "لطفەن كىتاب نامىنى تولۇق ياكى باشقا شەكىلدە تەكرار سوراڭ."
                    )
                book_match = matches[0]
                title = book_match.get("title", "نامسىز كىتاب")
                author = book_match.get("author") or "ئاپتور نامەلۇم"
                return f"«{title}» ناملىق ئەسەرنىڭ ئاپتورى {author}."

            if req.bookId != "global":
                book = await db.books.find_one({"id": req.bookId})
                if book:
                    title = book.get("title", "نامسىز كىتاب")
                    author = book.get("author") or "ئاپتور نامەلۇم"
                    return f"«{title}» ناملىق ئەسەرنىڭ ئاپتورى {author}."

            return (
                "كىتابنىڭ ئاپتورىنى تاپالايمەن، ئەمما كىتاب نامىنى "
                "تەمىنلەپ بەرگەندىن كېيىنلا جاۋاب بېرەلەيمەن."
            )

        is_global = req.bookId == "global"
        book = None
        if not is_global:
            book = await db.books.find_one({"id": req.bookId})
            if not book:
                raise ValueError("Book not found")

        use_current_volume_only = self._is_current_volume_query(req.question)
        include_current_page_context = self._is_current_page_query(req.question)
        current_page_context = ""
        current_page_only = include_current_page_context

        if include_current_page_context and not is_global and req.currentPage and book:
            page_rec = next(
                (r for r in book.get("results", []) if r.get("pageNumber") == req.currentPage),
                None,
            )
            if page_rec and page_rec.get("text"):
                current_page_context = (
                    "CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - "
                    f"Book: {book.get('title', 'Unknown')}, Page {req.currentPage}:\n"
                    f"{page_rec['text']}"
                )

        if current_page_only:
            context = current_page_context or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            return await self._generate_answer(
                context,
                req.question,
                strict_no_answer=False,
                suppress_page_notice=False,
            )

        pages_to_search = []
        related_books = []

        if is_global:
            all_categories = await db.books.distinct("categories")
            relevant_categories = []
            try:
                relevant_categories = await self._categorize_question(req.question, all_categories)
            except Exception:
                relevant_categories = []

            query = {}
            if relevant_categories:
                query = {"categories": {"$in": relevant_categories}}

            all_books = await db.books.find(query).to_list(100)
            if not all_books:
                all_books = await db.books.find().sort("lastUpdated", -1).to_list(200)

            for b in all_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b.get("title")
                        pages_to_search.append(r)
        else:
            related_books = [book]
            title = book.get("title")
            author = book.get("author")

            if title and not use_current_volume_only:
                sibling_query = {"title": title, "id": {"$ne": req.bookId}}
                if author:
                    sibling_query["author"] = author
                siblings = await db.books.find(sibling_query).to_list(200)
                if siblings:
                    related_books.extend(siblings)

            for b in related_books:
                for r in b.get("results", []):
                    if r.get("status") == "completed":
                        r["bookTitle"] = b.get("title")
                        pages_to_search.append(r)

        query_vector = []
        try:
            query_vector = await self.embeddings.aembed_query(req.question)
        except Exception:
            query_vector = []

        scored_results = []
        keywords = self._extract_keywords(req.question)

        for r in pages_to_search:
            score = 0.0
            if query_vector and r.get("embedding"):
                score = self._cosine_similarity(query_vector, r["embedding"])

            txt = r.get("text", "")
            match_count = 0
            for k in keywords:
                if k and k in txt:
                    match_count += 1
            if match_count > 0:
                score += match_count * 0.15

            scored_results.append(
                {
                    "text": r.get("text", ""),
                    "score": score,
                    "page": r.get("pageNumber"),
                    "title": r.get("bookTitle"),
                }
            )

        top_results = [r for r in scored_results if r["score"] > settings.rag_score_threshold]
        if not top_results and scored_results:
            top_results = sorted(scored_results, key=lambda x: x["score"], reverse=True)[: settings.rag_fallback_k]
        else:
            top_results = sorted(top_results, key=lambda x: x["score"], reverse=True)[: settings.rag_top_k]

        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)

        for r in top_results:
            if is_global or r["page"] != req.currentPage:
                context_parts.append(f"Book: {r['title']}, Page {r['page']}:\n{r['text']}")

        if not top_results and not is_global:
            fallback_context = self._build_books_fallback_context(
                related_books,
                max_chars_per_book=settings.rag_max_chars_per_book,
            )
            if fallback_context:
                context_parts.append(fallback_context)

        context = "\n\n---\n\n".join(context_parts)
        if not context and is_global:
            context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

        return await self._generate_answer(
            context,
            req.question,
            strict_no_answer=False,
            suppress_page_notice=False,
        )


rag_service = RAGService()
