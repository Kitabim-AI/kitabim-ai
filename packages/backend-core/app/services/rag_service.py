from __future__ import annotations

import re
from typing import List, Optional, AsyncIterator
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
from app.core.i18n import t
import logging
import time

# Import reranker
try:
    from langchain_community.document_compressors import FlashrankRerank
    FLASHRANK_AVAILABLE = True
except ImportError:
    FLASHRANK_AVAILABLE = False
    logging.warning("FlashrankRerank not available. Install langchain-community and flashrank to enable reranking.")


class CategoryResponse(BaseModel):
    categories: List[str] = Field(default_factory=list)


class RAGService:
    def __init__(self) -> None:
        self.embeddings = GeminiEmbeddings()
        self._parser = PydanticOutputParser(pydantic_object=CategoryResponse)
        self._rag_chains: dict = {}
        self._category_chains: dict = {}
        self.logger = logging.getLogger("app.rag")

        # Initialize reranker if enabled and available
        self.reranker: Optional[FlashrankRerank] = None
        if settings.rag_rerank_enabled and FLASHRANK_AVAILABLE:
            try:
                self.reranker = FlashrankRerank(top_n=settings.rag_rerank_top_n)
                log_json(self.logger, logging.INFO, "Flashrank reranker initialized", top_n=settings.rag_rerank_top_n)
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Failed to initialize reranker", error=str(exc))

    def _get_rag_chain(self, model_name: str):
        if model_name not in self._rag_chains:
            self._rag_chains[model_name] = build_text_chain(
                RAG_PROMPT_TEMPLATE, model_name, run_name="rag_chain"
            )
        return self._rag_chains[model_name]

    def _get_category_chain(self, model_name: str):
        if model_name not in self._category_chains:
            self._category_chains[model_name] = build_structured_chain(
                CATEGORY_PROMPT, model_name, self._parser, run_name="category_chain"
            )
        return self._category_chains[model_name]

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
    def _is_author_or_catalog_query(question: str) -> bool:
        """Detect if the question is about book authors or which books exist in the library."""
        if not question:
            return False
        q = question.strip()
        keywords = [
            # Author-related
            "مۇئەللىپ", "يازغۇچى", "كىم يازغان", "ئاپتور", "مۇئەللىپى",
            "كىم تەرىپىدىن", "يازغانلىقى", "ئەسەر يازغان", "ئەسەرلىرى",
            # Catalog / book-list related
            "كىتابلىرىڭىز", "كىتاب بارمۇ", "كىتابخانىڭىز",
            "كىتاب تىزىملىكى", "قانچە كىتاب", "نەچچە كىتاب",
            "قايسى كىتابلار", "قايسى ئەسەر",
        ]
        return any(k in q for k in keywords)

    @staticmethod
    def _format_book_catalog(books) -> str:
        """Format a list of (title, author) rows as LLM context."""
        if not books:
            return "NO BOOKS FOUND IN THE LIBRARY."
        lines = ["Library catalog — available books:"]
        for book in books:
            title = book.title or "Unknown"
            author = book.author
            if author:
                lines.append(f"- {title} (Author: {author})")
            else:
                lines.append(f"- {title}")
        return "\n".join(lines)

    @staticmethod
    def _build_empty_response_message() -> str:
        return t("errors.chat_no_context")

    @staticmethod
    def _build_instructions(strict_no_answer: bool, suppress_page_notice: bool) -> str:
        if strict_no_answer:
            return (
                "Instructions:\n"
                "1. Primary Goal: Answer the user's question ONLY based on the provided context.\n"
                "2. Chat History: Review the chat history to understand follow-up questions, references to previous topics, and conversational context. If the user asks 'what about...', 'tell me more', or uses pronouns like 'it', 'that', or 'this', refer to the chat history to understand what they're asking about.\n"
                "3. If the answer is NOT in the context, respond with exactly: " + t("errors.chat_no_answer") + "\n"
                "4. Format your response in markdown:\n"
                "   - Use double newlines (\\n\\n) to separate paragraphs for better readability\n"
                "   - Use **bold** for emphasis on key terms\n"
                "   - Use bullet points (- ) for lists when appropriate\n"
                "5. Respond ONLY in professional Uyghur (Arabic script).\n"
                "6. STRICT RULE: Output ONLY Uyghur text. Do not include English words, translations, or explanations in other languages."
            )
        extra_rules = ""
        if suppress_page_notice:
            extra_rules = "\n9. If you can answer, do NOT mention whether the current page contained the answer."
        return (
            "Instructions:\n"
            "1. Primary Goal: Answer the user's question based on the provided context.\n"
            "2. Chat History: Review the chat history to understand follow-up questions, references to previous topics, and conversational context. If the user asks 'what about...', 'tell me more', or uses pronouns like 'it', 'that', or 'this', refer to the chat history to understand what they're asking about.\n"
            "3. Format your response in markdown:\n"
            "   - Use double newlines (\\n\\n) to separate paragraphs for better readability\n"
            "   - Use **bold** for emphasis on key terms or important information\n"
            "   - Use bullet points (- ) for lists when presenting multiple items\n"
            "   - Use > for direct quotations from the source text\n"
            "4. If the context contains the information, ALWAYS cite the source clearly.\n"
            "   Each document in the context starts with a header like: [BookID: abc123, Book: title, Author: name, Volume: N, Page: N]\n"
            "   You MUST use the EXACT author name from the 'Author:' field in that header. If there is no 'Author:' field in the header, omit the author from the citation entirely — do NOT write any 'unknown' or placeholder text for the author.\n"
            "5. Format citations in Uyghur as a markdown link. The link URL MUST be in the format 'ref:book_id:page_number'.\n"
            "   If multiple pages are referenced, separate the page numbers with commas in the URL (e.g. 'ref:book_id:9,10').\n"
            "   Example: **مەنبە:** [ئانا يۇرت (زوردۇن سابىر)، 1-توم، 25-بەت](ref:abc123:25)\n"
            "6. Replace 'abc123' with the actual BookID and the author/title with the exact values from the context header. **Citations must be placed immediately after the relevant sentence or paragraph they support. NEVER group all citations at the end of your response.**\n"
            "7. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:\n"
            "   - Politely explain that you couldn't find a specific match in the indexed books.\n"
            "   - If it's a general question or greeting, respond naturally but maintain your persona as a librarian advisor.\n"
            "8. Respond ONLY in professional Uyghur (Arabic script).\n"
            "9. STRICT RULE: Output ONLY Uyghur text. Do not include English words, translations, or mixed-language sentences. Maintain purely Uyghur syntax and vocabulary."
            + extra_rules
        )



    @staticmethod
    def _format_document(doc: Document) -> str:
        title = doc.metadata.get("title") or "Unknown"
        author = doc.metadata.get("author") or None
        volume = doc.metadata.get("volume")
        page = doc.metadata.get("page")
        book_id = doc.metadata.get("book_id") or "unknown"

        # Build a clear source header for the LLM
        source_parts = [f"BookID: {book_id}", f"Book: {title}"]
        if author:
            source_parts.append(f"Author: {author}")
        if volume is not None:
            source_parts.append(f"Volume: {volume}")
        if page is not None:
            source_parts.append(f"Page: {page}")

        header = ", ".join(source_parts)
        return f"[{header}]\n{doc.page_content}"

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

    @staticmethod
    def _expand_history_categories(categories: List[str]) -> List[str]:
        """When تارىخ is matched, also include ئۇيغۇر تارىخى and ئىسلام تارىخى so those books are always searched.
        ئۇيغۇر تارىخى is prioritized over ئىسلام تارىخى in result ordering (see priority_book_ids logic)."""
        if "تارىخ" in categories:
            extra = [c for c in ["ئۇيغۇر تارىخى", "ئىسلام تارىخى"] if c not in categories]
            return categories + extra
        return categories

    async def _categorize_question(self, question: str, categories: List[str], chain) -> List[str]:
        if not categories:
            return []
        response = await chain.ainvoke(
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
        chain,
        chat_history: str = "",
        strict_no_answer: bool = False,
        suppress_page_notice: bool = False,
    ) -> str:
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice)
        response_text = await chain.ainvoke(
            {
                "context": context,
                "instructions": instructions,
                "chat_history": chat_history,
                "question": question,
            }
        )
        return response_text.strip() or self._build_empty_response_message()

    async def _generate_answer_stream(
        self,
        context: str,
        question: str,
        chain,
        chat_history: str = "",
        strict_no_answer: bool = False,
        suppress_page_notice: bool = False,
    ) -> AsyncIterator[str]:
        """Stream answer chunks as they're generated by the LLM"""
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice)
        has_content = False
        chunk_count = 0

        async for chunk in chain.astream(
            {
                "context": context,
                "instructions": instructions,
                "chat_history": chat_history,
                "question": question,
            }
        ):
            if chunk:
                has_content = True
                chunk_count += 1
                chunk_size = len(chunk) if isinstance(chunk, str) else 0
                log_json(
                    self.logger,
                    logging.INFO,
                    "Streaming chunk",
                    chunk_num=chunk_count,
                    chunk_size=chunk_size,
                    chunk_type=type(chunk).__name__
                )
                yield chunk

        log_json(
            self.logger,
            logging.INFO,
            "Stream generation complete",
            total_chunks=chunk_count
        )

        # If no content was generated, send empty response message
        if not has_content:
            yield self._build_empty_response_message()

    async def _record_eval(self, session, payload: dict, user_id: Optional[str] = None) -> None:
        """Record RAG evaluation metrics using SQLAlchemy"""
        if not settings.rag_eval_enabled:
            log_json(self.logger, logging.DEBUG, "RAG eval recording skipped: disabled in settings")
            return
        if session is None:
            log_json(self.logger, logging.WARNING, "RAG eval recording skipped: session is None")
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
                user_id=user_id,
            )
            await session.commit()
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "RAG eval insert failed", error=str(exc))

    async def answer_question(self, req: ChatRequest, session: AsyncSession, user_id: Optional[str] = None) -> str:
        start_ts = time.monotonic()
        is_global = req.book_id == "global"
        relevant_categories: List[str] = []
        priority_book_ids: set = set()
        book = None

        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.repositories.chunks import ChunksRepository
        from app.db.repositories.system_configs import SystemConfigsRepository
        from sqlalchemy import select, func, and_, or_
        from app.db.models import Book, Page

        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        chunks_repo = ChunksRepository(session)
        configs_repo = SystemConfigsRepository(session)

        chat_model = await configs_repo.get_value("gemini_chat_model", default=settings.gemini_chat_model)
        categorization_model = await configs_repo.get_value("gemini_categorization_model", default=settings.gemini_categorization_model)
        rag_chain = self._get_rag_chain(chat_model)
        category_chain = self._get_category_chain(categorization_model)

        if not is_global:
            book = await books_repo.get(req.book_id)
            if not book:
                raise ValueError(t("errors.book_not_found"))

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
                author_info = f", Author: {book.author}" if book.author else ""
                volume_info = f", Volume {book.volume}" if book.volume is not None else ""
                current_page_context = (
                    f"[BookID: {req.book_id}, Book: {book.title or 'Unknown'}{author_info}{volume_info}, Page {req.current_page}]\n"
                    f"{page_text}"
                )

        if current_page_only:
            context = current_page_context or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            return await self._generate_answer(
                context,
                req.question,
                rag_chain,
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
            # If the user is asking about book authors or catalog, provide the full book list
            if self._is_author_or_catalog_query(req.question):
                stmt = select(Book.title, Book.author).where(
                    Book.status == "ready"
                ).order_by(Book.title)
                result = await session.execute(stmt)
                all_books = result.fetchall()
                context = self._format_book_catalog(all_books)
                answer = await self._generate_answer(
                    context,
                    req.question,
                    rag_chain,
                    chat_history=chat_history_str,
                    strict_no_answer=False,
                    suppress_page_notice=True,
                )
                await self._record_eval(
                    session,
                    {
                        "bookId": req.book_id,
                        "isGlobal": True,
                        "question": req.question,
                        "currentPage": req.current_page,
                        "retrievedCount": len(all_books),
                        "contextChars": len(context),
                        "scores": [],
                        "categoryFilter": [],
                        "latencyMs": int((time.monotonic() - start_ts) * 1000),
                        "answer_chars": len(answer),
                    },
                    user_id=user_id,
                )
                return answer

            # Global content search - categorize to narrow down books
            # Get all unique categories from books table
            stmt = select(Book.categories).where(Book.categories != None)
            result = await session.execute(stmt)
            all_categories = set()
            for cats in result.scalars().all():
                if cats:
                    all_categories.update(cats)

            relevant_categories = []
            try:
                relevant_categories = await self._categorize_question(req.question, list(all_categories), category_chain)
                relevant_categories = self._expand_history_categories(relevant_categories)
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                relevant_categories = []

            # Find books by category
            if relevant_categories:
                # Use overlap (&& in Postgres) for categories
                from sqlalchemy import text
                stmt = select(Book.id, Book.title, Book.categories).where(
                    text("categories && :cats").bindparams(cats=relevant_categories)
                ).limit(100)
                result = await session.execute(stmt)
                all_books_recs = result.fetchall()
                # Track ئۇيغۇر تارىخى books for result prioritization
                if "ئۇيغۇر تارىخى" in relevant_categories:
                    priority_book_ids = {
                        str(b.id) for b in all_books_recs
                        if b.categories and "ئۇيغۇر تارىخى" in b.categories
                    }
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
            # Search the specific book and all its sibling volumes (same title + author)
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

                # Format results with book titles and volume
                for chunk in similar_chunks:
                    top_results.append({
                        "text": chunk.get("text", ""),
                        "score": chunk.get("similarity", 0.0),
                        "page": chunk.get("page_number"),
                        "title": chunk.get("title") or "Unknown",
                        "volume": chunk.get("volume"),
                        "author": chunk.get("author") or None,
                        "book_id": chunk.get("book_id"),
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

        # Apply reranking if enabled and we have results
        if self.reranker and top_results and len(top_results) > 1:
            try:
                rerank_start = time.monotonic()
                log_json(
                    self.logger,
                    logging.INFO,
                    "Starting reranking",
                    candidate_count=len(top_results),
                    timestamp=datetime.utcnow().isoformat()
                )

                # Store original vector scores for logging
                original_scores = [r.get("score", 0.0) for r in top_results]
                original_order = [i for i in range(len(top_results))]

                # Convert to Documents for reranking
                docs_for_rerank = [
                    Document(
                        page_content=r["text"],
                        metadata={
                            "title": r.get("title") or "Unknown",
                            "volume": r.get("volume"),
                            "page": r.get("page"),
                            "book_id": r.get("book_id"),
                            "vector_score": r.get("score", 0.0),
                            "original_index": i
                        }
                    ) for i, r in enumerate(top_results)
                ]

                # Apply reranking
                reranked_docs = await self.reranker.acompress_documents(docs_for_rerank, req.question)

                rerank_end = time.monotonic()
                rerank_duration_ms = int((rerank_end - rerank_start) * 1000)

                # Rebuild top_results from reranked documents
                reranked_results = []
                for doc in reranked_docs:
                    original_idx = doc.metadata.get("original_index", 0)
                    reranked_results.append({
                        "text": doc.page_content,
                        "score": doc.metadata.get("vector_score", 0.0),
                        "page": doc.metadata.get("page"),
                        "title": doc.metadata.get("title") or "Unknown",
                        "volume": doc.metadata.get("volume"),
                        "author": doc.metadata.get("author") or None,
                        "book_id": doc.metadata.get("book_id"),
                    })

                # Log reranking impact
                if reranked_results:
                    reranked_indices = [
                        top_results.index(next(r for r in top_results if r["text"] == rr["text"]))
                        for rr in reranked_results
                    ]
                    log_json(
                        self.logger,
                        logging.INFO,
                        "Reranking completed",
                        original_count=len(top_results),
                        reranked_count=len(reranked_results),
                        original_top_3=original_order[:3],
                        reranked_top_3=reranked_indices[:3] if len(reranked_indices) >= 3 else reranked_indices,
                        duration_ms=rerank_duration_ms,
                        timestamp=datetime.utcnow().isoformat()
                    )
                    top_results = reranked_results

            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Reranking failed, using original order", error=str(exc))

        # Prioritize ئۇيغۇر تارىخى books when تارىخ was matched (stable sort)
        if priority_book_ids:
            top_results.sort(key=lambda r: 0 if str(r.get("book_id", "")) in priority_book_ids else 1)

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
                        metadata={
                            "title": title,
                            "volume": r.get("volume"),
                            "author": r.get("author") or None,
                            "page": r.get("page"),
                            "book_id": r.get("book_id")
                        },
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
            rag_chain,
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
                "answer_chars": len(answer),
            },
            user_id=user_id,
        )

        return answer

    async def answer_question_stream(
        self, req: ChatRequest, session: AsyncSession, user_id: Optional[str] = None
    ) -> AsyncIterator[str]:
        """Stream answer chunks as they're generated by the LLM"""
        start_ts = time.monotonic()
        is_global = req.book_id == "global"
        relevant_categories: List[str] = []
        priority_book_ids: set = set()
        book = None

        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.repositories.chunks import ChunksRepository
        from app.db.repositories.system_configs import SystemConfigsRepository
        from sqlalchemy import select, func, and_, or_
        from app.db.models import Book, Page

        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        chunks_repo = ChunksRepository(session)
        configs_repo = SystemConfigsRepository(session)

        chat_model = await configs_repo.get_value("gemini_chat_model", default=settings.gemini_chat_model)
        categorization_model = await configs_repo.get_value("gemini_categorization_model", default=settings.gemini_categorization_model)
        rag_chain = self._get_rag_chain(chat_model)
        category_chain = self._get_category_chain(categorization_model)

        if not is_global:
            book = await books_repo.get(req.book_id)
            if not book:
                raise ValueError(t("errors.book_not_found"))

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
                author_info = f", Author: {book.author}" if book.author else ""
                volume_info = f", Volume {book.volume}" if book.volume is not None else ""
                current_page_context = (
                    f"[BookID: {req.book_id}, Book: {book.title or 'Unknown'}{author_info}{volume_info}, Page {req.current_page}]\n"
                    f"{page_text}"
                )

        if current_page_only:
            context = current_page_context or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            async for chunk in self._generate_answer_stream(
                context,
                req.question,
                rag_chain,
                chat_history=chat_history_str,
                strict_no_answer=False,
                suppress_page_notice=False,
            ):
                yield chunk
            return

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
            # If the user is asking about book authors or catalog, provide the full book list
            if self._is_author_or_catalog_query(req.question):
                stmt = select(Book.title, Book.author).where(
                    Book.status == "ready"
                ).order_by(Book.title)
                result = await session.execute(stmt)
                all_books = result.fetchall()
                context = self._format_book_catalog(all_books)
                answer_chunks = []
                async for chunk in self._generate_answer_stream(
                    context,
                    req.question,
                    rag_chain,
                    chat_history=chat_history_str,
                    strict_no_answer=False,
                    suppress_page_notice=True,
                ):
                    answer_chunks.append(chunk)
                    yield chunk
                full_answer = "".join(answer_chunks)
                await self._record_eval(
                    session,
                    {
                        "bookId": req.book_id,
                        "isGlobal": True,
                        "question": req.question,
                        "currentPage": req.current_page,
                        "retrievedCount": len(all_books),
                        "contextChars": len(context),
                        "scores": [],
                        "categoryFilter": [],
                        "latencyMs": int((time.monotonic() - start_ts) * 1000),
                        "answer_chars": len(full_answer),
                    },
                    user_id=user_id,
                )
                return

            # Global content search - categorize to narrow down books
            stmt = select(Book.categories).where(Book.categories != None)
            result = await session.execute(stmt)
            all_categories = set()
            for cats in result.scalars().all():
                if cats:
                    all_categories.update(cats)

            relevant_categories = []
            try:
                relevant_categories = await self._categorize_question(req.question, list(all_categories), category_chain)
                relevant_categories = self._expand_history_categories(relevant_categories)
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                relevant_categories = []

            # Find books by category
            if relevant_categories:
                from sqlalchemy import text
                stmt = select(Book.id, Book.title, Book.categories).where(
                    text("categories && :cats").bindparams(cats=relevant_categories)
                ).limit(100)
                result = await session.execute(stmt)
                all_books_recs = result.fetchall()
                # Track ئۇيغۇر تارىخى books for result prioritization
                if "ئۇيغۇر تارىخى" in relevant_categories:
                    priority_book_ids = {
                        str(b.id) for b in all_books_recs
                        if b.categories and "ئۇيغۇر تارىخى" in b.categories
                    }
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
            # Search the specific book and all its sibling volumes (same title + author)
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
                similar_chunks = await chunks_repo.similarity_search(
                    query_embedding=query_vector,
                    book_ids=book_ids if book_ids else None,
                    limit=settings.rag_top_k,
                    threshold=settings.rag_score_threshold
                )

                for chunk in similar_chunks:
                    top_results.append({
                        "text": chunk.get("text", ""),
                        "score": chunk.get("similarity", 0.0),
                        "page": chunk.get("page_number"),
                        "title": chunk.get("title") or "Unknown",
                        "volume": chunk.get("volume"),
                        "author": chunk.get("author") or None,
                        "book_id": chunk.get("book_id"),
                    })
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Vector search failed", error=str(exc))
                top_results = []

        # Fallback if no results or no embedding
        if not top_results and book_ids:
            keywords = self._extract_keywords(req.question)
            if keywords:
                log_json(self.logger, logging.INFO, "Using keyword fallback search")
                top_results = []

        # Apply reranking if enabled and we have results
        if self.reranker and top_results and len(top_results) > 1:
            try:
                rerank_start = time.monotonic()
                log_json(
                    self.logger,
                    logging.INFO,
                    "Starting reranking",
                    candidate_count=len(top_results),
                    timestamp=datetime.utcnow().isoformat()
                )

                original_scores = [r.get("score", 0.0) for r in top_results]
                original_order = [i for i in range(len(top_results))]

                docs_for_rerank = [
                    Document(
                        page_content=r["text"],
                        metadata={
                            "title": r.get("title") or "Unknown",
                            "volume": r.get("volume"),
                            "page": r.get("page"),
                            "book_id": r.get("book_id"),
                            "vector_score": r.get("score", 0.0),
                            "original_index": i
                        }
                    ) for i, r in enumerate(top_results)
                ]

                reranked_docs = await self.reranker.acompress_documents(docs_for_rerank, req.question)

                rerank_end = time.monotonic()
                rerank_duration_ms = int((rerank_end - rerank_start) * 1000)

                reranked_results = []
                for doc in reranked_docs:
                    original_idx = doc.metadata.get("original_index", 0)
                    reranked_results.append({
                        "text": doc.page_content,
                        "score": doc.metadata.get("vector_score", 0.0),
                        "page": doc.metadata.get("page"),
                        "title": doc.metadata.get("title") or "Unknown",
                        "volume": doc.metadata.get("volume"),
                        "author": doc.metadata.get("author") or None,
                        "book_id": doc.metadata.get("book_id"),
                    })

                if reranked_results:
                    reranked_indices = [
                        top_results.index(next(r for r in top_results if r["text"] == rr["text"]))
                        for rr in reranked_results
                    ]
                    log_json(
                        self.logger,
                        logging.INFO,
                        "Reranking completed",
                        original_count=len(top_results),
                        reranked_count=len(reranked_results),
                        original_top_3=original_order[:3],
                        reranked_top_3=reranked_indices[:3] if len(reranked_indices) >= 3 else reranked_indices,
                        duration_ms=rerank_duration_ms,
                        timestamp=datetime.utcnow().isoformat()
                    )
                    top_results = reranked_results

            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Reranking failed, using original order", error=str(exc))

        # Prioritize ئۇيغۇر تارىخى books when تارىخ was matched (stable sort)
        if priority_book_ids:
            top_results.sort(key=lambda r: 0 if str(r.get("book_id", "")) in priority_book_ids else 1)

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
                        metadata={
                            "title": title,
                            "volume": r.get("volume"),
                            "author": r.get("author") or None,
                            "page": r.get("page"),
                            "book_id": r.get("book_id")
                        },
                    )
                )

        for doc in documents:
            context_parts.append(self._format_document(doc))

        context = "\n\n---\n\n".join(context_parts)
        if not context and is_global:
            context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

        # Stream the answer
        answer_chunks = []
        async for chunk in self._generate_answer_stream(
            context,
            req.question,
            rag_chain,
            chat_history=chat_history_str,
            strict_no_answer=False,
            suppress_page_notice=False,
        ):
            answer_chunks.append(chunk)
            yield chunk

        # Record evaluation after streaming completes
        full_answer = "".join(answer_chunks)
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
                "answer_chars": len(full_answer),
            },
            user_id=user_id,
        )


rag_service = RAGService()
