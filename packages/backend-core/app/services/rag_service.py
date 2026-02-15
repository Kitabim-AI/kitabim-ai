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

    async def _record_eval(self, session, payload: dict) -> None:
        """Record RAG evaluation metrics using SQLAlchemy"""
        if not settings.rag_eval_enabled or session is None:
            return
        try:
            from app.db.repositories.rag_evaluations import RAGEvaluationsRepository

            repo = RAGEvaluationsRepository(session)
            await repo.create_evaluation(
                book_id=payload.get("bookId"),
                is_global=payload.get("isGlobal", False),
                question=payload.get("question", ""),
                current_page=payload.get("currentPage"),
                retrieved_count=payload.get("retrievedCount", 0),
                context_chars=payload.get("contextChars", 0),
                scores=payload.get("scores", []),
                category_filter=payload.get("categoryFilter", []),
                latency_ms=payload.get("latencyMs", 0),
                answer_chars=payload.get("answerChars", 0),
            )
            await session.commit()
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "RAG eval insert failed", error=str(exc))

    async def answer_question(self, req: ChatRequest, session: AsyncSession) -> str:
        start_ts = time.monotonic()
        is_global = req.book_id == "global"
        relevant_categories: List[str] = []
        book = None

        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.repositories.chunks import ChunksRepository
        from sqlalchemy import select, func, and_, or_
        from app.db.models import Book, Page

        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        chunks_repo = ChunksRepository(session)

        if not is_global:
            book = await books_repo.get(req.book_id)
            if not book:
                raise ValueError("Book not found")

        use_current_volume_only = self._is_current_volume_query(req.question)
        include_current_page_context = self._is_current_page_query(req.question)
        current_page_context = ""
        current_page_only = include_current_page_context

        # Prepare chat history string
        chat_history_str = self._format_chat_history(req.history)

        if include_current_page_context and not is_global and req.current_page and book:
            page_rec = await pages_repo.find_one(req.book_id, req.current_page)
            if page_rec and page_rec.text:
                page_text = strip_markdown(page_rec.text or "")
                current_page_context = (
                    "CURRENT PAGE (THE USER IS LOOKING AT THIS NOW) - "
                    f"Book: {book.title or 'Unknown'}, Page {req.current_page}:\n"
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

        # Get query embedding for vector search
        query_vector = []
        try:
            query_vector = await self.embeddings.aembed_query(req.question)
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "Embedding generation failed", error=str(exc))
            query_vector = []

        # Determine which books to search
        book_ids = []
        book_id_to_title = {}

        if is_global:
            # Global search - categorize to narrow down books
            # Get all unique categories from books table
            stmt = select(Book.categories).where(Book.categories != None)
            result = await session.execute(stmt)
            all_categories = set()
            for cats in result.scalars().all():
                if cats:
                    all_categories.update(cats)

            relevant_categories = []
            try:
                relevant_categories = await self._categorize_question(req.question, list(all_categories))
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                relevant_categories = []

            # Find books by category
            if relevant_categories:
                # Use overlap (&& in Postgres) for categories
                from sqlalchemy import text
                stmt = select(Book.id, Book.title).where(
                    text("categories && :cats").bindparams(cats=relevant_categories)
                ).limit(100)
                result = await session.execute(stmt)
                all_books_recs = result.fetchall()
            else:
                all_books_recs = []

            if not all_books_recs:
                # Fallback to recent books
                stmt = select(Book.id, Book.title).order_by(Book.last_updated.desc()).limit(200)
                result = await session.execute(stmt)
                all_books_recs = result.fetchall()

            book_id_to_title = {str(b.id): b.title for b in all_books_recs}
            book_ids = list(book_id_to_title.keys())
        else:
            # Search specific book and siblings
            title = book.title
            author = book.author

            book_ids = [str(req.book_id)]
            book_id_to_title = {str(req.book_id): book.title}

            if title and not use_current_volume_only:
                # Find sibling volumes
                stmt = select(Book.id, Book.title).where(
                    and_(
                        Book.title == title,
                        Book.id != req.book_id
                    )
                )
                if author:
                    stmt = stmt.where(Book.author == author)
                
                result = await session.execute(stmt)
                siblings = result.fetchall()
                for s in siblings:
                    book_ids.append(str(s.id))
                    book_id_to_title[str(s.id)] = s.title

        # Use PostgreSQL pgvector for similarity search
        top_results = []
        if query_vector:
            try:
                # Perform vector similarity search using PostgreSQL
                similar_chunks = await chunks_repo.similarity_search(
                    query_embedding=query_vector,
                    book_ids=book_ids if book_ids else None,
                    limit=settings.rag_top_k,
                    threshold=settings.rag_score_threshold
                )

                # Format results with book titles
                for chunk in similar_chunks:
                    b_id = chunk.get("book_id")
                    top_results.append({
                        "text": chunk.get("text", ""),
                        "score": chunk.get("similarity", 0.0),
                        "page": chunk.get("page_number"),
                        "title": book_id_to_title.get(b_id, "Unknown"),
                    })
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Vector search failed", error=str(exc))
                top_results = []

        # Fallback if no results or no embedding
        if not top_results and book_ids:
            # Keyword-based fallback (basic text search)
            keywords = self._extract_keywords(req.question)
            if keywords:
                log_json(self.logger, logging.INFO, "Using keyword fallback search")
                # TODO: Implement full-text search fallback in Postgres
                top_results = []

        context_parts = []
        if current_page_context:
            context_parts.append(current_page_context)

        documents: List[Document] = []
        for r in top_results:
            if is_global or r["page"] != req.current_page:
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
            session,
            {
                "bookId": req.book_id,
                "isGlobal": is_global,
                "question": req.question,
                "currentPage": req.current_page,
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
