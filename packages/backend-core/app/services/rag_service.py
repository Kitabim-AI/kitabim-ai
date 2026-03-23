from __future__ import annotations

import re
from typing import List, Optional, AsyncIterator
from pydantic import BaseModel, Field
from langchain_core.output_parsers import PydanticOutputParser

import numpy as np
from langchain_core.documents import Document
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import Book
from app.core.prompts import CATEGORY_PROMPT, RAG_PROMPT_TEMPLATE

from app.langchain import GeminiEmbeddings, build_structured_chain, build_text_chain
from app.models.schemas import ChatRequest
from app.utils.markdown import strip_markdown
from app.utils.observability import log_json
from app.core.i18n import t
from app.services.cache_service import cache_service
from app.core import cache_config
from app.core.characters import CHARACTERS, DEFAULT_CHARACTER_ID
import logging
import time
import hashlib





class CategoryResponse(BaseModel):
    categories: List[str] = Field(default_factory=list)


class RAGService:
    def __init__(self) -> None:
        self._parser = PydanticOutputParser(pydantic_object=CategoryResponse)
        self._rag_chains: dict = {}
        self._category_chains: dict = {}
        self._embeddings_cache: dict = {}  # Cache embeddings by model name
        self.logger = logging.getLogger("app.rag")

    def _get_embeddings(self, model_name: str) -> GeminiEmbeddings:
        """Get or create cached embeddings instance for the given model."""
        if model_name not in self._embeddings_cache:
            self._embeddings_cache[model_name] = GeminiEmbeddings(model_name)
        return self._embeddings_cache[model_name]

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
    def _normalize_uyghur(text: str) -> str:
        """Normalize Uyghur character variants for reliable keyword matching.
        ې (U+06D0) and ي (U+064A) are often used interchangeably with ى (U+06CC)
        depending on keyboard/input method.
        """
        return text.replace("\u06D0", "\u06CC").replace("\u0649", "\u06CC").replace("\u064A", "\u06CC")

    @staticmethod
    def _is_author_or_catalog_query(question: str) -> bool:
        """Detect if the question is about book authors or which books exist in the library."""
        if not question:
            return False
        q = RAGService._normalize_uyghur(question.strip())
        keywords = [
            # Author-related — "who wrote X" / "author of X"
            "مۇئەللىپ", "مۇئەللىپى", "يازغۇچى", "يازغۇچىسى", "ئاپتور", "ئاپتورى",
            "كىم يازغان", "يازغان كىشى", "يازغان كىم",
            "كىم تەرىپىدىن", "يازغانلىقى", "كىمنىڭ", "كىمنىكى",
            # Author-related — "X's books / works"
            "ئەسەر يازغان", "ئەسەرلىرى", "كىتابلىرى",
            # Catalog / book-list related
            "كىتابلىرىڭىز", "كىتاب بارمۇ", "كىتابخانىڭىز",
            "كىتاب تىزىملىكى", "قانچە كىتاب", "نەچچە كىتاب",
            "قايسى كىتابلار", "قايسى ئەسەر",
        ]
        normalized_keywords = [RAGService._normalize_uyghur(k) for k in keywords]
        return any(k in q for k in normalized_keywords)

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
    def _entity_matches_question(entity: str, question: str) -> bool:
        """
        Check if an author name or book title is referenced in the question,
        handling Uyghur agglutinative suffixes (e.g. 'سابىر' matches 'سابىرنىڭ').
        Each word of the entity must appear as a prefix of at least one word in the question.
        Requires at least 2 words to match to avoid false positives on common single words.
        Normalizes ى/ې/ي variants before comparison.
        """
        normalize = RAGService._normalize_uyghur
        entity_words = normalize(entity.strip()).split()
        if len(entity_words) < 2:
            return False
        q_words = normalize(question.strip()).split()
        return all(
            any(q_word.startswith(e_word) for q_word in q_words)
            for e_word in entity_words
        )

    @staticmethod
    async def _build_catalog_context(question: str, session, categories: Optional[List[str]] = None) -> tuple[str, int]:
        """
        Build the most specific context possible from the books table:
        - If a known book title is referenced in the question → return info for that book
        - Elif a known author name is referenced → return that author's books
        - Else → return the library catalog (optionally filtered by categories)
        Returns (context_str, retrieved_count).
        """
        q = question.strip()

        # 1. Try to match a book title (word-prefix match to handle Uyghur suffixes)
        stmt = select(Book.title).where(Book.status != "error")
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))
        
        title_result = await session.execute(stmt)
        titles = [row[0] for row in title_result.fetchall() if row[0]]
        matched_title = next((t for t in titles if RAGService._entity_matches_question(t, q)), None)

        if matched_title:
            stmt = select(Book.title, Book.author, Book.volume, Book.total_pages, Book.status).where(
                Book.status != "error",
                Book.title == matched_title,
            ).order_by(Book.volume)
            result = await session.execute(stmt)
            books = result.fetchall()
            if books:
                lines = [f"Information about '{matched_title}':"]
                for book in books:
                    author = book.author or "Unknown"
                    volume = f", Volume {book.volume}" if book.volume is not None else ""
                    pages = f", {book.total_pages} pages" if book.total_pages else ""
                    status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
                    lines.append(f"- Title: {book.title}{volume}, Author: {author}{pages}{status_tag}")
                return "\n".join(lines), len(books)

        # 2. Try to match an author name (word-prefix match to handle Uyghur suffixes)
        stmt = select(Book.author).where(Book.author.isnot(None), Book.status != "error").distinct()
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))
        
        author_result = await session.execute(stmt)
        authors = [row[0] for row in author_result.fetchall() if row[0]]
        matched_author = next((a for a in authors if RAGService._entity_matches_question(a, q)), None)

        if matched_author:
            stmt = select(Book.title, Book.author, Book.volume, Book.total_pages, Book.status).where(
                Book.status != "error",
                Book.author == matched_author,
            ).order_by(Book.volume, Book.title)
            result = await session.execute(stmt)
            books = result.fetchall()
            lines = [f"Books by author '{matched_author}' in the library:"]
            for book in books:
                volume = f", Volume {book.volume}" if book.volume is not None else ""
                pages = f", {book.total_pages} pages" if book.total_pages else ""
                status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
                lines.append(f"- {book.title}{volume}{pages}{status_tag}")
            return "\n".join(lines), len(books)

        # 3. Fall back to library catalog (optionally filtered by categories)
        stmt = select(Book.title, Book.author, Book.status).where(Book.status != "error")
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))
        
        stmt = stmt.order_by(Book.title)
        result = await session.execute(stmt)
        all_books = result.fetchall()
        
        if not all_books:
            return "NO BOOKS FOUND IN THE LIBRARY.", 0
            
        lines = ["Library catalog — available books:"]
        for book in all_books:
            title = book.title or "Unknown"
            author = book.author
            status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
            if author:
                lines.append(f"- {title} (Author: {author}){status_tag}")
            else:
                lines.append(f"- {title}{status_tag}")
        return "\n".join(lines), len(all_books)

    @staticmethod
    async def _find_books_by_title_in_question(question: str, session) -> Optional[List[str]]:
        """
        Detect if the question mentions a known book title and return matching book IDs.
        Handles Uyghur agglutinative suffixes via word-prefix matching.
        Returns all volume IDs for the matched title, or None if no match.
        """
        from sqlalchemy import select
        from app.db.models import Book

        q = question.strip()
        title_result = await session.execute(
            select(Book.id, Book.title).where(Book.status != "error")
        )
        rows = title_result.fetchall()

        # Group IDs by title (handles multi-volume books)
        title_to_ids: dict = {}
        for row in rows:
            book_id, title = str(row[0]), row[1]
            if title:
                title_to_ids.setdefault(title, []).append(book_id)

        matched_title = next(
            (t for t in title_to_ids if RAGService._entity_matches_question(t, q)),
            None,
        )
        return title_to_ids[matched_title] if matched_title else None

    @staticmethod
    def _build_empty_response_message() -> str:
        return t("errors.chat_no_context")

    @staticmethod
    def _build_instructions(strict_no_answer: bool, suppress_page_notice: bool, persona_prompt: Optional[str] = None, is_global: bool = False, has_categories: bool = False) -> str:
        prefix = ""
        if persona_prompt:
            prefix = f"Persona: {persona_prompt}\n\n"

        if strict_no_answer:
            return (
                prefix +
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
        if is_global:
            extra_rules += "\n10. Skip any greetings, introductions, or pleasantries (e.g., 'Hello', 'As-salamu alaykum', 'How can I help you?'). Start your response directly with the answer or the most relevant information."

        librarian_fallback = ""
        if is_global and has_categories:
            librarian_fallback = "   - Suggest that the user ask the Librarian (زېرەكچاق) for assistance with books or authors outside your specific expertise.\n"

        return (
            prefix +
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
            "   STRICT RULE: Do NOT include the 'BookID: abc123' part in the visible text label of the link! Keep the book ID ONLY in the URL parenthesis.\n"
            "   Example: **مەنبە:** [ئانا يۇرت (زوردۇن سابىر)، 1-توم، 25-بەت](ref:abc123:25)\n"
            "6. Replace 'abc123' with the actual BookID in the URL, and use the exact values from the context header for the author/title. **Citations must be placed immediately after the relevant sentence or paragraph they support. NEVER group all citations at the end of your response.**\n"
            "7. If the context is marked as 'NO RELEVANT DOCUMENTS FOUND' or does not contain the answer:\n"
            "   - Politely explain that you couldn't find a specific match in the indexed books.\n"
            "   - Skip any greeting and directly state that no match was found.\n"
            + librarian_fallback + 
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
        persona_prompt: Optional[str] = None,
        is_global: bool = False,
        has_categories: bool = False,
    ) -> str:
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice, persona_prompt, is_global, has_categories)
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
        persona_prompt: Optional[str] = None,
        is_global: bool = False,
        has_categories: bool = False,
    ) -> AsyncIterator[str]:
        """Stream answer chunks as they're generated by the LLM"""
        instructions = self._build_instructions(strict_no_answer, suppress_page_notice, persona_prompt, is_global, has_categories)
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
        priority_book_ids: set = set()
        book = None

        # Character logic
        persona_prompt = None
        character_categories = []
        char_id = req.character_id or DEFAULT_CHARACTER_ID
        character = CHARACTERS.get(char_id)
        if character:
            persona_prompt = character.persona_prompt
            character_categories = character.categories

        log_json(self.logger, logging.INFO, "RAG answer_question requested", 
                book_id=req.book_id, is_global=is_global, char_id=char_id, categories=character_categories)

        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.repositories.chunks import ChunksRepository
        from app.db.repositories.system_configs import SystemConfigsRepository
        from sqlalchemy import select, and_
        from app.db.models import Book

        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        chunks_repo = ChunksRepository(session)
        configs_repo = SystemConfigsRepository(session)

        chat_model = await configs_repo.get_value("gemini_chat_model")
        if not chat_model:
            raise RuntimeError("system_config 'gemini_chat_model' is not set")
        categorization_model = await configs_repo.get_value("gemini_categorization_model")
        if not categorization_model:
            raise RuntimeError("system_config 'gemini_categorization_model' is not set")
        embedding_model = await configs_repo.get_value("gemini_embedding_model")
        if not embedding_model:
            raise RuntimeError("system_config 'gemini_embedding_model' is not set")
        rag_chain = self._get_rag_chain(chat_model)
        category_chain = self._get_category_chain(categorization_model)
        embeddings = self._get_embeddings(embedding_model)

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
                is_global=is_global,
                has_categories=bool(character_categories),
            )

        # Get query embedding for vector search (Level 1 Cache)
        query_vector = []
        q_hash = hashlib.md5(req.question.strip().encode()).hexdigest()
        emb_cache_key = cache_config.KEY_RAG_EMBEDDING.format(hash=q_hash)
        
        try:
            query_vector = await cache_service.get(emb_cache_key)
            if not query_vector:
                query_vector = await embeddings.aembed_query(req.question)
                if query_vector:
                    await cache_service.set(emb_cache_key, query_vector, ttl=settings.cache_ttl_rag_query)
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "Embedding retrieval/generation failed", error=str(exc))
            query_vector = []


        # Determine which books to search
        book_ids = []
        book_id_to_title = {}

        # 0. Check if the user is asking about book authors or the general catalog
        if self._is_author_or_catalog_query(req.question):
            context, retrieved_count = await self._build_catalog_context(req.question, session, categories=character_categories)
            
            # If we are in a specific book, also include its metadata specifically
            # This handles cases like "Who is the author of this book?" when in reader
            if not is_global and book:
                author_info = f", Author: {book.author}" if book.author else ""
                volume_info = f", Volume {book.volume}" if book.volume is not None else ""
                pages_info = f", {book.total_pages} pages" if book.total_pages else ""
                status_info = f" [Status: {book.status}]" if book.status != "ready" else ""
                
                current_book_intro = "Information about the book the user is currently reading:\n"
                current_book_intro += f"- Title: {book.title or 'Unknown'}{author_info}{volume_info}{pages_info}{status_info}\n\n---\n\n"
                context = current_book_intro + context

            answer = await self._generate_answer(
                context,
                req.question,
                rag_chain,
                chat_history=chat_history_str,
                strict_no_answer=False,
                suppress_page_notice=True,
                persona_prompt=persona_prompt,
                is_global=is_global,
                has_categories=bool(character_categories),
            )
            await self._record_eval(
                session,
                {
                    "bookId": req.book_id,
                    "isGlobal": is_global,
                    "question": req.question,
                    "currentPage": req.current_page,
                    "retrievedCount": retrieved_count,
                    "contextChars": len(context),
                    "scores": [],
                    "categoryFilter": [],
                    "latencyMs": int((time.monotonic() - start_ts) * 1000),
                    "answer_chars": len(answer),
                },
                user_id=user_id,
            )
            return answer

        if is_global:
            # 0. Character-based filtering (Pre-filter)
            char_book_ids = None
            if character_categories:
                from sqlalchemy import text as sa_text
                stmt = select(Book.id).where(
                    sa_text("categories && :cats").bindparams(cats=character_categories)
                ).where(Book.status == "ready")
                result = await session.execute(stmt)
                char_book_ids = [str(bid) for bid in result.scalars().all()]
                log_json(self.logger, logging.INFO, "Character categories filtered search space", count=len(char_book_ids), char_id=char_id)

            # 1. Check if the question references a specific book title
            title_matched_ids = await self._find_books_by_title_in_question(req.question, session)
            if title_matched_ids:
                if char_book_ids is not None:
                    # Filter matching titles by character allowed books
                    filtered_matched_ids = [bid for bid in title_matched_ids if bid in char_book_ids]
                    if filtered_matched_ids:
                        book_ids = filtered_matched_ids
                        log_json(self.logger, logging.INFO, "Book title detected and allowed by character categories", count=len(book_ids))
                    else:
                        log_json(self.logger, logging.INFO, "Book title detected but ignored: not in character categories")
                else:
                    book_ids = title_matched_ids
                    log_json(self.logger, logging.INFO, "Book title detected in global query, restricting search", count=len(title_matched_ids))

            if not book_ids:
                # 2. Summary-based book selection (stage 1 of hierarchical retrieval).
                if query_vector:
                    try:
                        from app.db.repositories.book_summaries import BookSummariesRepository
                        summaries_repo = BookSummariesRepository(session)

                        # Cache Lookup (Level 3)
                        emb_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
                        char_tag = char_id if character_categories else "all"
                        summary_cache_key = cache_config.KEY_RAG_SUMMARY_SEARCH.format(hash=f"{char_tag}:{emb_hash}")
                        
                        book_ids = await cache_service.get(summary_cache_key)
                        if book_ids is None:
                            book_ids = await summaries_repo.summary_search(
                                query_embedding=query_vector,
                                book_ids=char_book_ids,
                                limit=settings.summary_top_k,
                                threshold=settings.summary_threshold,
                            )
                            if book_ids is not None:
                                await cache_service.set(summary_cache_key, book_ids, ttl=settings.cache_ttl_rag_query)

                        if book_ids:
                            log_json(self.logger, logging.INFO, "Summary search selected books", count=len(book_ids))

                    except Exception as exc:
                        log_json(self.logger, logging.WARNING, "Summary search failed", error=str(exc))
                        book_ids = []

                # 3. Fallback: category-based search
                if not book_ids:
                    if not character_categories:
                        # Auto-categorize if no character categories are set
                        stmt = select(Book.categories).where(Book.categories.isnot(None))
                        result = await session.execute(stmt)
                        all_categories = set()
                        for cats in result.scalars().all():
                            if cats:
                                all_categories.update(cats)

                        try:
                            relevant_categories = await self._categorize_question(req.question, list(all_categories), category_chain)
                            relevant_categories = self._expand_history_categories(relevant_categories)
                            log_json(self.logger, logging.INFO, "Auto-categorized question", categories=relevant_categories)
                        except Exception as exc:
                            log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                            relevant_categories = []

                        if relevant_categories:
                            from sqlalchemy import text as sa_text
                            stmt = select(Book.id, Book.title, Book.categories).where(
                                sa_text("categories && :cats").bindparams(cats=relevant_categories)
                            ).limit(100)
                            result = await session.execute(stmt)
                            all_books_recs = result.fetchall()
                            if "ئۇيغۇر تارىخى" in relevant_categories:
                                priority_book_ids = {
                                    str(b.id) for b in all_books_recs
                                    if b.categories and "ئۇيغۇر تارىخى" in b.categories
                                }
                        else:
                            all_books_recs = []
                    else:
                        # Use character book IDs if available
                        if char_book_ids:
                            all_books_recs = []
                            # Fetch metadata for the character's books
                            stmt = select(Book.id, Book.title).where(Book.id.in_(char_book_ids[:200]))
                            result = await session.execute(stmt)
                            all_books_recs = result.fetchall()
                        else:
                            all_books_recs = []

                    if not all_books_recs and not character_categories:
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

        # Use PostgreSQL pgvector for similarity search (Level 2 Cache)
        top_results = []
        if query_vector:
            # Generate Cache Key (Level 2)
            emb_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
            # Sort IDs for stable hash
            sorted_book_ids = sorted(book_ids) if book_ids else []
            book_ids_hash = hashlib.md5(",".join(sorted_book_ids).encode()).hexdigest() if sorted_book_ids else "all"
            
            if not is_global and len(sorted_book_ids) == 1:
                search_cache_key = cache_config.KEY_RAG_SEARCH_SINGLE.format(
                    book_id=sorted_book_ids[0], 
                    hash=emb_hash
                )
            else:
                search_cache_key = cache_config.KEY_RAG_SEARCH_MULTI.format(
                    book_ids_hash=book_ids_hash, 
                    hash=emb_hash
                )

            try:
                top_results = await cache_service.get(search_cache_key)
                if top_results is None:
                    # Perform vector similarity search using PostgreSQL
                    similar_chunks = await chunks_repo.similarity_search(
                        query_embedding=query_vector,
                        book_ids=book_ids if book_ids else None,
                        limit=settings.rag_top_k,
                        threshold=settings.rag_score_threshold
                    )

                    # Format results with book titles and volume
                    top_results = []
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
                    
                    if top_results is not None:
                        await cache_service.set(search_cache_key, top_results, ttl=settings.cache_ttl_rag_query)
                
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
            persona_prompt=persona_prompt,
            is_global=is_global,
            has_categories=bool(character_categories),
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
                "categoryFilter": character_categories or (relevant_categories if is_global else []),
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
        priority_book_ids: set = set()
        book = None

        # Character logic
        persona_prompt = None
        character_categories = []
        char_id = req.character_id or DEFAULT_CHARACTER_ID
        character = CHARACTERS.get(char_id)
        if character:
            persona_prompt = character.persona_prompt
            character_categories = character.categories

        log_json(self.logger, logging.INFO, "RAG answer_question_stream requested", 
                book_id=req.book_id, is_global=is_global, char_id=char_id, categories=character_categories)

        from app.db.repositories.books import BooksRepository
        from app.db.repositories.pages import PagesRepository
        from app.db.repositories.chunks import ChunksRepository
        from app.db.repositories.system_configs import SystemConfigsRepository
        from sqlalchemy import select, and_
        from app.db.models import Book

        books_repo = BooksRepository(session)
        pages_repo = PagesRepository(session)
        chunks_repo = ChunksRepository(session)
        configs_repo = SystemConfigsRepository(session)

        chat_model = await configs_repo.get_value("gemini_chat_model")
        if not chat_model:
            raise RuntimeError("system_config 'gemini_chat_model' is not set")
        categorization_model = await configs_repo.get_value("gemini_categorization_model")
        if not categorization_model:
            raise RuntimeError("system_config 'gemini_categorization_model' is not set")
        embedding_model = await configs_repo.get_value("gemini_embedding_model")
        if not embedding_model:
            raise RuntimeError("system_config 'gemini_embedding_model' is not set")
        rag_chain = self._get_rag_chain(chat_model)
        category_chain = self._get_category_chain(categorization_model)
        embeddings = self._get_embeddings(embedding_model)

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
                persona_prompt=persona_prompt,
                is_global=is_global,
                has_categories=bool(character_categories),
            ):
                yield chunk
            return

        # Get query embedding for vector search (Level 1 Cache)
        query_vector = []
        q_hash = hashlib.md5(req.question.strip().encode()).hexdigest()
        emb_cache_key = cache_config.KEY_RAG_EMBEDDING.format(hash=q_hash)
        
        try:
            query_vector = await cache_service.get(emb_cache_key)
            if not query_vector:
                query_vector = await embeddings.aembed_query(req.question)
                if query_vector:
                    await cache_service.set(emb_cache_key, query_vector, ttl=settings.cache_ttl_rag_query)
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "Embedding retrieval/generation failed", error=str(exc))
            query_vector = []


        # Determine which books to search
        book_ids = []
        book_id_to_title = {}

        # 0. Check if the user is asking about book authors or the general catalog
        if self._is_author_or_catalog_query(req.question):
            context, retrieved_count = await self._build_catalog_context(req.question, session, categories=character_categories)
            
            # If we are in a specific book, also include its metadata specifically
            if not is_global and book:
                author_info = f", Author: {book.author}" if book.author else ""
                volume_info = f", Volume {book.volume}" if book.volume is not None else ""
                pages_info = f", {book.total_pages} pages" if book.total_pages else ""
                status_info = f" [Status: {book.status}]" if book.status != "ready" else ""
                
                current_book_intro = "Information about the book the user is currently reading:\n"
                current_book_intro += f"- Title: {book.title or 'Unknown'}{author_info}{volume_info}{pages_info}{status_info}\n\n---\n\n"
                context = current_book_intro + context

            answer_chunks = []
            async for chunk in self._generate_answer_stream(
                context,
                req.question,
                rag_chain,
                chat_history=chat_history_str,
                strict_no_answer=False,
                suppress_page_notice=True,
                persona_prompt=persona_prompt,
                is_global=is_global,
                has_categories=bool(character_categories),
            ):
                answer_chunks.append(chunk)
                yield chunk
            
            full_answer = "".join(answer_chunks)
            try:
                await self._record_eval(
                    session,
                    {
                        "bookId": req.book_id,
                        "isGlobal": is_global,
                        "question": req.question,
                        "currentPage": req.current_page,
                        "retrievedCount": retrieved_count,
                        "contextChars": len(context),
                        "scores": [],
                        "categoryFilter": character_categories,
                        "latencyMs": int((time.monotonic() - start_ts) * 1000),
                        "answer_chars": len(full_answer),
                    },
                    user_id=user_id,
                )
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Failed to record eval (catalog path)", error=str(exc))
            return

        if is_global:
            # 0. Character-based filtering (Pre-filter)
            char_book_ids = None
            if character_categories:
                from sqlalchemy import text as sa_text
                stmt = select(Book.id).where(
                    sa_text("categories && :cats").bindparams(cats=character_categories)
                ).where(Book.status == "ready")
                result = await session.execute(stmt)
                char_book_ids = [str(bid) for bid in result.scalars().all()]
                log_json(self.logger, logging.INFO, "Character categories filtered search space", count=len(char_book_ids), char_id=char_id)

            # 1. Check if the question references a specific book title
            title_matched_ids = await self._find_books_by_title_in_question(req.question, session)
            if title_matched_ids:
                if char_book_ids is not None:
                    # Filter matching titles by character allowed books
                    filtered_matched_ids = [bid for bid in title_matched_ids if bid in char_book_ids]
                    if filtered_matched_ids:
                        book_ids = filtered_matched_ids
                        log_json(self.logger, logging.INFO, "Book title detected and allowed by character categories", count=len(book_ids))
                    else:
                        log_json(self.logger, logging.INFO, "Book title detected but ignored: not in character categories")
                else:
                    book_ids = title_matched_ids
                    log_json(self.logger, logging.INFO, "Book title detected in global query, restricting search", count=len(title_matched_ids))

            if not book_ids:
                # 2. Summary-based book selection (stage 1 of hierarchical retrieval).
                # query_vector is already computed and reused here — no extra API call.
                if query_vector:
                    try:
                        from app.db.repositories.book_summaries import BookSummariesRepository
                        summaries_repo = BookSummariesRepository(session)
                        # Cache Lookup (Level 3)
                        emb_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
                        char_tag = char_id if character_categories else "all"
                        summary_cache_key = cache_config.KEY_RAG_SUMMARY_SEARCH.format(hash=f"{char_tag}:{emb_hash}")
                        
                        book_ids = await cache_service.get(summary_cache_key)
                        if book_ids is None:
                            book_ids = await summaries_repo.summary_search(
                                query_embedding=query_vector,
                                book_ids=char_book_ids,
                                limit=settings.summary_top_k,
                                threshold=settings.summary_threshold,
                            )
                            if book_ids is not None:
                                await cache_service.set(summary_cache_key, book_ids, ttl=settings.cache_ttl_rag_query)

                        if book_ids:
                            log_json(self.logger, logging.INFO, "Summary search selected books", count=len(book_ids))

                    except Exception as exc:
                        log_json(self.logger, logging.WARNING, "Summary search failed, falling back to category search", error=str(exc))
                        book_ids = []

                # 3. Fallback: category-based search (when no summaries exist yet)
                if not book_ids:
                    if not character_categories:
                        # Auto-categorize if no character categories are set
                        stmt = select(Book.categories).where(Book.categories.isnot(None))
                        result = await session.execute(stmt)
                        all_categories = set()
                        for cats in result.scalars().all():
                            if cats:
                                all_categories.update(cats)

                    try:
                        relevant_categories = await self._categorize_question(req.question, list(all_categories), category_chain)
                        relevant_categories = self._expand_history_categories(relevant_categories)
                        log_json(self.logger, logging.INFO, "Auto-categorized question", categories=relevant_categories)
                    except Exception as exc:
                        log_json(self.logger, logging.WARNING, "Category routing failed", error=str(exc))
                        relevant_categories = []

                    if relevant_categories:
                        from sqlalchemy import text
                        stmt = select(Book.id, Book.title, Book.categories).where(
                            text("categories && :cats").bindparams(cats=relevant_categories)
                        ).limit(100)
                        result = await session.execute(stmt)
                        all_books_recs = result.fetchall()
                        if "ئۇيغۇر تارىخى" in relevant_categories:
                            priority_book_ids = {
                                str(b.id) for b in all_books_recs
                                if b.categories and "ئۇيغۇر تارىخى" in b.categories
                            }
                    else:
                        all_books_recs = []

                    if not all_books_recs and not character_categories:
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

        # Use PostgreSQL pgvector for similarity search (Level 2 Cache)
        top_results = []
        if query_vector:
            # Generate Cache Key (Level 2)
            emb_hash = hashlib.md5(str(query_vector).encode()).hexdigest()
            sorted_book_ids = sorted(book_ids) if book_ids else []
            book_ids_hash = hashlib.md5(",".join(sorted_book_ids).encode()).hexdigest() if sorted_book_ids else "all"
            
            if not is_global and len(sorted_book_ids) == 1:
                search_cache_key = cache_config.KEY_RAG_SEARCH_SINGLE.format(
                    book_id=sorted_book_ids[0], 
                    hash=emb_hash
                )
            else:
                search_cache_key = cache_config.KEY_RAG_SEARCH_MULTI.format(
                    book_ids_hash=book_ids_hash, 
                    hash=emb_hash
                )

            try:
                top_results = await cache_service.get(search_cache_key)
                if top_results is None:
                    similar_chunks = await chunks_repo.similarity_search(
                        query_embedding=query_vector,
                        book_ids=book_ids if book_ids else None,
                        limit=settings.rag_top_k,
                        threshold=settings.rag_score_threshold
                    )

                    top_results = []
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
                    
                    if top_results is not None:
                        await cache_service.set(search_cache_key, top_results, ttl=settings.cache_ttl_rag_query)
                
            except Exception as exc:
                log_json(self.logger, logging.WARNING, "Vector search failed", error=str(exc))
                top_results = []


        # Fallback if no results or no embedding
        if not top_results and book_ids:
            keywords = self._extract_keywords(req.question)
            if keywords:
                log_json(self.logger, logging.INFO, "Using keyword fallback search")
                top_results = []


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
            persona_prompt=persona_prompt,
            is_global=is_global,
            has_categories=bool(character_categories),
        ):
            answer_chunks.append(chunk)
            yield chunk

        # Record evaluation after streaming completes
        full_answer = "".join(answer_chunks)
        try:
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
                    "categoryFilter": character_categories or (relevant_categories if is_global else []),
                    "latencyMs": int((time.monotonic() - start_ts) * 1000),
                    "answer_chars": len(full_answer),
                },
                user_id=user_id,
            )
        except Exception as exc:
            log_json(self.logger, logging.WARNING, "Failed to record eval (main path)", error=str(exc))


rag_service = RAGService()
