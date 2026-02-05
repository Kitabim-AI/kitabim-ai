from __future__ import annotations

import re
from typing import List
from datetime import datetime
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

import numpy as np
from langchain_core.documents import Document

from app.core.config import settings
from app.core.prompts import CATEGORY_PROMPT, RAG_PROMPT_TEMPLATE
from app.langchain import GeminiEmbeddings, build_structured_chain, build_text_chain
from app.models.schemas import ChatRequest
from app.utils.markdown import strip_markdown
from app.utils.observability import log_json
import logging
import time


class CategoryResponse(BaseModel):
    categories: List[str] = Field(default_factory=list)


class RAGService:
    def __init__(self) -> None:
        parser = PydanticOutputParser(pydantic_object=CategoryResponse)
        self.embeddings = GeminiEmbeddings()
        self.category_chain = build_structured_chain(
            CATEGORY_PROMPT,
            settings.gemini_categorization_model,
            parser,
            run_name="category_chain",
        )
        self.rag_chain = build_text_chain(
            RAG_PROMPT_TEMPLATE,
            settings.gemini_model_name,
            run_name="rag_chain",
        )
        self.logger = logging.getLogger("app.rag")

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
        q = question.strip()
        keywords = ["ئۇشبۇ بەتتە", "مەزكور بەتتە", "بۇ بەتتە"]
        return any(k in q for k in keywords)

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
    def _format_document(doc: Document) -> str:
        title = doc.metadata.get("title", "Unknown")
        page = doc.metadata.get("page")
        if page is None:
            return f"Book: {title}:\n{doc.page_content}"
        return f"Book: {title}, Page {page}:\n{doc.page_content}"

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
        response = await self.category_chain.ainvoke(
            {
                "categories": categories,
                "question": question,
            }
        )
        if not response:
            return []
        return [str(x) for x in (response.categories or [])]

    @staticmethod
    def _format_chat_history(history: List[dict]) -> str:
        if not history:
            return "No previous conversation."
        
        formatted = []
        for msg in history[-6:]:  # Limit to last 6 turns to keep context incomplete but focused
            role = "User" if msg.get("role") == "user" else "AI"
            text = msg.get("text", "").replace("\n", " ").strip()
            formatted.append(f"{role}: {text}")
        return "\n".join(formatted)

    async def _generate_answer(
        self,
        context: str,
        question: str,
        chat_history: str = "",
        strict_no_answer: bool = False,
        suppress_page_notice: bool = False,
    ) -> str:
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice)
        response_text = await self.rag_chain.ainvoke(
            {
                "context": context,
                "instructions": instructions,
                "chat_history": chat_history,
                "question": question,
            }
        )
        return response_text.strip() or self._build_empty_response_message()

    async def _record_eval(self, db, payload: dict) -> None:
        if not settings.rag_eval_enabled or db is None:
            return
        payload["ts"] = datetime.utcnow()
        try:
            await db.rag_evaluations.insert_one(payload)
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "RAG eval insert failed", error=str(exc))

    async def answer_question(self, req: ChatRequest, db) -> str:
        start_ts = time.monotonic()
        is_global = req.bookId == "global"
        relevant_categories: List[str] = []
        book = None
        if not is_global:
            book = await db.books.find_one({"id": req.bookId})
            if not book:
                raise ValueError("Book not found")

        use_current_volume_only = self._is_current_volume_query(req.question)
        include_current_page_context = self._is_current_page_query(req.question)
        current_page_context = ""
        current_page_only = include_current_page_context

        # Prepare chat history string
        chat_history_str = self._format_chat_history(req.history)

        if include_current_page_context and not is_global and req.currentPage and book:
            page_rec = await db.pages.find_one(
                {"bookId": req.bookId, "pageNumber": req.currentPage}
            )
            if page_rec and page_rec.get("text"):
                # ... existing logic remains ...
                page_text = strip_markdown(page_rec.get("text") or "")
                current_page_context = (
                    "CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - "
                    f"Book: {book.get('title', 'Unknown')}, Page {req.currentPage}:\n"
                    f"{page_text}"
                )

        if current_page_only:
            context = current_page_context or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            return await self._generate_answer(
                context,
                req.question,
                chat_history=chat_history_str,
                strict_no_answer=False,
                suppress_page_notice=False,
            )

        # ... (rest of search logic) ...


        pages_to_search = []
        related_books = []

        if is_global:
            all_categories = await db.books.distinct("categories")
            relevant_categories = []
            try:
                relevant_categories = await self._categorize_question(req.question, all_categories)
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                relevant_categories = []

            query = {}
            if relevant_categories:
                query = {"categories": {"$in": relevant_categories}}

            all_books_recs = await db.books.find(query, {"id": 1, "title": 1}).to_list(100)
            if not all_books_recs:
                all_books_recs = await db.books.find({}, {"id": 1, "title": 1}).sort("lastUpdated", -1).to_list(200)
            
            book_id_to_title = {b["id"]: b.get("title") for b in all_books_recs}
            book_ids = list(book_id_to_title.keys())
            
            # Fetch chunks from chunks collection
            chunks_recs = await db.chunks.find(
                {"bookId": {"$in": book_ids}}
            ).to_list(15000)
            
            for r in chunks_recs:
                r["bookTitle"] = book_id_to_title.get(r.get("bookId"))
                pages_to_search.append(r)
        else:
            # For specific book, get siblings
            title = book.get("title")
            author = book.get("author")
            
            related_ids = [req.bookId]
            book_id_to_title = {req.bookId: book.get("title")}

            if title and not use_current_volume_only:
                sibling_query = {"title": title, "id": {"$ne": req.bookId}}
                if author:
                    sibling_query["author"] = author
                siblings = await db.books.find(sibling_query, {"id": 1, "title": 1}).to_list(200)
                for s in siblings:
                    related_ids.append(s["id"])
                    book_id_to_title[s["id"]] = s.get("title")

            # Fetch chunks from chunks collection
            chunks_recs = await db.chunks.find(
                {"bookId": {"$in": related_ids}}
            ).to_list(15000)
            
            for r in chunks_recs:
                r["bookTitle"] = book_id_to_title.get(r.get("bookId"))
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

            txt = strip_markdown(r.get("text", ""))
            match_count = 0
            for k in keywords:
                if k and k in txt:
                    match_count += 1
            if match_count > 0:
                score += match_count * 0.15

            scored_results.append(
                {
                    "text": txt,
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

        documents: List[Document] = []
        for r in top_results:
            if is_global or r["page"] != req.currentPage:
                title = r.get("title") or "Unknown"
                documents.append(
                    Document(
                        page_content=r["text"],
                        metadata={"title": title, "page": r.get("page")},
                    )
                )

        for doc in documents:
            context_parts.append(self._format_document(doc))



        context = "\n\n---\n\n".join(context_parts)
        if not context and is_global:
            context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

        answer = await self._generate_answer(
            context,
            req.question,
            chat_history=chat_history_str,
            strict_no_answer=False,
            suppress_page_notice=False,
        )

        await self._record_eval(
            db,
            {
                "bookId": req.bookId,
                "isGlobal": is_global,
                "question": req.question,
                "currentPage": req.currentPage,
                "retrievedCount": len(top_results),
                "contextChars": len(context),
                "scores": [r.get("score") for r in top_results],
                "categoryFilter": relevant_categories if is_global else [],
                "latencyMs": int((time.monotonic() - start_ts) * 1000),
                "answerChars": len(answer),
            },
        )

        return answer


rag_service = RAGService()
