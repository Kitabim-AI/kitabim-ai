"""StandardRAGHandler — full vector-search pipeline, fallback for all unmatched intents."""
from __future__ import annotations

import hashlib
import logging
from typing import AsyncIterator, List, Optional, Tuple

from langchain_core.documents import Document
from sqlalchemy import select, and_

from app.core.config import settings
from app.core import cache_config
from app.db.models import Book
from app.services.cache_service import cache_service
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import (
    expand_history_categories,
    extract_keywords,
)
from app.services.rag.answer_builder import (
    categorize_question,
    format_document,
    generate_answer,
    generate_answer_stream,
)
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.standard")


class StandardRAGHandler(QueryHandler):
    """Full hierarchical retrieval pipeline.

    Steps (global mode):
    1. Character-category pre-filter
    2. Book-title match (exact prefix)
    3. Summary-vector book selection  (Level-3 cache)
    4. Category-based fallback
    5. pgvector chunk search           (Level-2 cache)

    Steps (single-book mode):
    1. Sibling-volume discovery (respects ctx.use_current_volume_only)
    2. pgvector chunk search           (Level-2 cache)
    """

    intent_name = "standard_rag"
    priority = 999

    def can_handle(self, ctx: QueryContext) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def handle(self, ctx: QueryContext) -> str:
        context, top_results, category_filter = await self._build_rag_context(ctx)
        ctx.retrieved_count = len(top_results)
        ctx.context_chars = len(context)
        ctx.scores = [r.get("score") for r in top_results]
        ctx.category_filter = category_filter

        return await generate_answer(
            context,
            ctx.enriched_question or ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        )

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        context, top_results, category_filter = await self._build_rag_context(ctx)
        ctx.retrieved_count = len(top_results)
        ctx.context_chars = len(context)
        ctx.scores = [r.get("score") for r in top_results]
        ctx.category_filter = category_filter

        async for chunk in generate_answer_stream(
            context,
            ctx.enriched_question or ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Core pipeline
    # ------------------------------------------------------------------

    async def _build_rag_context(
        self, ctx: QueryContext
    ) -> Tuple[str, List[dict], List[str]]:
        """Return (context_str, top_results, category_filter).

        Also populates ctx.query_vector via the Level-1 embedding cache.
        """
        session = ctx.session
        priority_book_ids: set = set()
        relevant_categories: List[str] = []

        # ── Level-1 cache: query embedding ──────────────────────────────────
        retrieval_query = ctx.enriched_question or ctx.question
        q_hash = hashlib.md5(retrieval_query.strip().encode()).hexdigest()
        emb_cache_key = cache_config.KEY_RAG_EMBEDDING.format(hash=q_hash)
        try:
            ctx.query_vector = await cache_service.get(emb_cache_key)
            if not ctx.query_vector:
                ctx.query_vector = await ctx.embeddings.aembed_query(retrieval_query)
                if ctx.query_vector:
                    await cache_service.set(
                        emb_cache_key, ctx.query_vector, ttl=settings.cache_ttl_rag_query
                    )
        except Exception as exc:
            log_json(logger, logging.WARNING, "Embedding retrieval/generation failed", error=str(exc))
            ctx.query_vector = []

        # ── Book scope determination ─────────────────────────────────────────
        book_ids: List[str] = []

        if ctx.is_global:
            book_ids, priority_book_ids, relevant_categories = await self._select_global_books(ctx)
        else:
            book_ids = await self._select_single_book_scope(ctx)

        # ── Level-2 cache: pgvector similarity search ────────────────────────
        top_results = await self._vector_search(ctx, book_ids)

        # Keyword fallback (stub — pgvector already covers this well)
        if not top_results and book_ids:
            keywords = extract_keywords(ctx.question)
            if keywords:
                log_json(logger, logging.INFO, "Using keyword fallback search")

        # Prioritise ئۇيغۇر تارىخى books when تارىخ was matched
        if priority_book_ids:
            top_results.sort(
                key=lambda r: 0 if str(r.get("book_id", "")) in priority_book_ids else 1
            )

        # ── Build context string ─────────────────────────────────────────────
        context_parts: List[str] = []
        documents: List[Document] = []
        for r in top_results:
            if ctx.is_global or r["page"] != ctx.current_page:
                documents.append(
                    Document(
                        page_content=r["text"],
                        metadata={
                            "title": r.get("title") or "Unknown",
                            "volume": r.get("volume"),
                            "author": r.get("author") or None,
                            "page": r.get("page"),
                            "book_id": r.get("book_id"),
                        },
                    )
                )

        for doc in documents:
            context_parts.append(format_document(doc))

        context = "\n\n---\n\n".join(context_parts)
        if not context and ctx.is_global:
            context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."

        category_filter = ctx.character_categories or relevant_categories
        return context, top_results, category_filter

    # ------------------------------------------------------------------
    # Book-scope helpers
    # ------------------------------------------------------------------

    async def _select_global_books(
        self, ctx: QueryContext
    ) -> Tuple[List[str], set, List[str]]:
        """Return (book_ids, priority_book_ids, relevant_categories) for global search."""
        session = ctx.session
        char_id = ctx.character_id
        character_categories = ctx.character_categories
        priority_book_ids: set = set()
        relevant_categories: List[str] = []

        # ── Character-based pre-filter ───────────────────────────────────────
        char_book_ids: Optional[List[str]] = None
        if character_categories:
            from sqlalchemy import text as sa_text
            stmt = (
                select(Book.id)
                .where(sa_text("categories && :cats").bindparams(cats=character_categories))
                .where(Book.status == "ready")
            )
            result = await session.execute(stmt)
            char_book_ids = [str(bid) for bid in result.scalars().all()]
            log_json(
                logger, logging.INFO,
                "Character categories filtered search space",
                count=len(char_book_ids), char_id=char_id,
            )

        # ── 1. Book title match ──────────────────────────────────────────────
        book_ids: List[str] = []
        retrieval_query = ctx.enriched_question or ctx.question
        title_matched_ids = await self._find_books_by_title_in_question(retrieval_query, session)
        if title_matched_ids:
            if char_book_ids is not None:
                filtered = [bid for bid in title_matched_ids if bid in char_book_ids]
                if filtered:
                    book_ids = filtered
                    log_json(logger, logging.INFO, "Book title detected and allowed by character categories", count=len(book_ids))
                else:
                    log_json(logger, logging.INFO, "Book title detected but ignored: not in character categories")
            else:
                book_ids = title_matched_ids
                log_json(logger, logging.INFO, "Book title detected in global query, restricting search", count=len(title_matched_ids))

        if not book_ids:
            # ── 2. Summary-based book selection (Level-3 cache) ─────────────
            if ctx.query_vector:
                book_ids = await self._summary_search(ctx, char_book_ids)

        if not book_ids:
            # ── 3. Category-based fallback ───────────────────────────────────
            book_ids, priority_book_ids, relevant_categories = await self._category_fallback(
                ctx, char_book_ids
            )

        return book_ids, priority_book_ids, relevant_categories

    async def _select_single_book_scope(self, ctx: QueryContext) -> List[str]:
        """Return book IDs to search when in single-book (reader) mode."""
        book = ctx.book
        session = ctx.session

        book_ids = [str(ctx.book_id)]
        title = book.title
        author = book.author

        if title and not ctx.use_current_volume_only:
            stmt = select(Book.id, Book.title).where(
                and_(Book.title == title, Book.id != ctx.book_id)
            )
            if author:
                stmt = stmt.where(Book.author == author)
            result = await session.execute(stmt)
            for s in result.fetchall():
                book_ids.append(str(s.id))

        return book_ids

    async def _summary_search(
        self, ctx: QueryContext, char_book_ids: Optional[List[str]]
    ) -> List[str]:
        try:
            from app.db.repositories.book_summaries import BookSummariesRepository
            summaries_repo = BookSummariesRepository(ctx.session)

            emb_hash = hashlib.md5(str(ctx.query_vector).encode()).hexdigest()
            char_tag = ctx.character_id if ctx.character_categories else "all"
            summary_cache_key = cache_config.KEY_RAG_SUMMARY_SEARCH.format(
                hash=f"{char_tag}:{emb_hash}"
            )

            book_ids = await cache_service.get(summary_cache_key)
            if book_ids is None:
                book_ids = await summaries_repo.summary_search(
                    query_embedding=ctx.query_vector,
                    book_ids=char_book_ids,
                    limit=settings.summary_top_k,
                    threshold=settings.summary_threshold,
                )
                if book_ids is not None:
                    await cache_service.set(
                        summary_cache_key, book_ids, ttl=settings.cache_ttl_rag_query
                    )

            if book_ids:
                log_json(logger, logging.INFO, "Summary search selected books", count=len(book_ids))
            return book_ids or []

        except Exception as exc:
            log_json(logger, logging.WARNING, "Summary search failed", error=str(exc))
            return []

    async def _category_fallback(
        self, ctx: QueryContext, char_book_ids: Optional[List[str]]
    ) -> Tuple[List[str], set, List[str]]:
        session = ctx.session
        priority_book_ids: set = set()
        relevant_categories: List[str] = []

        if not ctx.character_categories:
            # Auto-categorize
            stmt = select(Book.categories).where(Book.categories.isnot(None))
            result = await session.execute(stmt)
            all_categories: set = set()
            for cats in result.scalars().all():
                if cats:
                    all_categories.update(cats)

            try:
                relevant_categories = await categorize_question(
                    ctx.question, list(all_categories), ctx.category_chain
                )
                relevant_categories = expand_history_categories(relevant_categories)
                log_json(logger, logging.INFO, "Auto-categorized question", categories=relevant_categories)
            except Exception as exc:
                log_json(logger, logging.WARNING, "Category routing failed", error=str(exc))
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
            # Use character book IDs
            all_books_recs = []
            if char_book_ids:
                stmt = select(Book.id, Book.title).where(Book.id.in_(char_book_ids[:200]))
                result = await session.execute(stmt)
                all_books_recs = result.fetchall()

        if not all_books_recs and not ctx.character_categories:
            stmt = select(Book.id, Book.title).order_by(Book.last_updated.desc()).limit(200)
            result = await session.execute(stmt)
            all_books_recs = result.fetchall()

        book_ids = [str(b.id) for b in all_books_recs]
        return book_ids, priority_book_ids, relevant_categories

    # ------------------------------------------------------------------
    # Vector search
    # ------------------------------------------------------------------

    async def _vector_search(self, ctx: QueryContext, book_ids: List[str]) -> List[dict]:
        if not ctx.query_vector:
            return []

        from app.db.repositories.chunks import ChunksRepository
        chunks_repo = ChunksRepository(ctx.session)

        emb_hash = hashlib.md5(str(ctx.query_vector).encode()).hexdigest()
        sorted_book_ids = sorted(book_ids) if book_ids else []
        book_ids_hash = (
            hashlib.md5(",".join(sorted_book_ids).encode()).hexdigest()
            if sorted_book_ids
            else "all"
        )

        if not ctx.is_global and len(sorted_book_ids) == 1:
            search_cache_key = cache_config.KEY_RAG_SEARCH_SINGLE.format(
                book_id=sorted_book_ids[0], hash=emb_hash
            )
        else:
            search_cache_key = cache_config.KEY_RAG_SEARCH_MULTI.format(
                book_ids_hash=book_ids_hash, hash=emb_hash
            )

        try:
            top_results = await cache_service.get(search_cache_key)
            if top_results is None:
                similar_chunks = await chunks_repo.similarity_search(
                    query_embedding=ctx.query_vector,
                    book_ids=book_ids if book_ids else None,
                    limit=settings.rag_top_k,
                    threshold=settings.rag_score_threshold,
                )
                top_results = [
                    {
                        "text": chunk.get("text", ""),
                        "score": chunk.get("similarity", 0.0),
                        "page": chunk.get("page_number"),
                        "title": chunk.get("title") or "Unknown",
                        "volume": chunk.get("volume"),
                        "author": chunk.get("author") or None,
                        "book_id": chunk.get("book_id"),
                    }
                    for chunk in similar_chunks
                ]
                if top_results is not None:
                    await cache_service.set(
                        search_cache_key, top_results, ttl=settings.cache_ttl_rag_query
                    )
            return top_results or []
        except Exception as exc:
            log_json(logger, logging.WARNING, "Vector search failed", error=str(exc))
            return []

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _find_books_by_title_in_question(
        question: str, session
    ) -> Optional[List[str]]:
        """Return IDs for all volumes of a title mentioned in the question, or None.

        If the question contains a title in «» quotes, exact (normalized) matching
        is tried first so that a quoted title like «تۈرك ئۇيغۇر دۆلەتلەر تارىخى»
        is not accidentally matched to a shorter title that shares some words.
        Falls back to word-prefix matching when no «» are present.
        """
        import re
        from app.services.rag.utils import entity_matches_question, normalize_uyghur

        q = question.strip()
        title_result = await session.execute(
            select(Book.id, Book.title).where(Book.status != "error")
        )
        rows = title_result.fetchall()

        title_to_ids: dict = {}
        for row in rows:
            book_id, title = str(row[0]), row[1]
            if title:
                title_to_ids.setdefault(title, []).append(book_id)

        # --- Exact match for «quoted» titles ---
        quoted = re.findall(r'«([^»]+)»', q)
        if quoted:
            for candidate in quoted:
                candidate_norm = normalize_uyghur(candidate.strip())
                for title, ids in title_to_ids.items():
                    if normalize_uyghur(title.strip()) == candidate_norm:
                        return ids
            # Quoted title present but no exact match → don't fall through to
            # fuzzy matching (avoids wrong-book answers like the «ئۇيغۇر تارىخى» case)
            return None

        # --- Fuzzy word-prefix match (no quotes in question) ---
        matched_title = next(
            (t for t in title_to_ids if entity_matches_question(t, q)), None
        )
        return title_to_ids[matched_title] if matched_title else None
