"""Shared retrieval primitives used across RAG handlers and agent tools.

All I/O-backed retrieval helpers live here — no LLM calls, no prompt logic.
"""
from __future__ import annotations

import hashlib
import logging
import re
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select

from app.core import cache_config
from app.core.config import settings
from app.db.models import Book
from app.services.cache_service import cache_service
from app.utils.observability import log_json

if TYPE_CHECKING:
    from app.services.rag.context import QueryContext

logger = logging.getLogger("app.rag.retrieval")


# ---------------------------------------------------------------------------
# Level-1 cache: query embedding
# ---------------------------------------------------------------------------

async def embed_query(query: str, ctx: "QueryContext") -> List[float]:
    """Embed *query* with Level-1 cache (shared across all RAG handlers).

    Returns an empty list on any failure — callers must handle the empty-vector
    case (usually by returning no results rather than crashing).
    """
    q_hash = hashlib.md5(query.strip().encode()).hexdigest()
    emb_cache_key = cache_config.KEY_RAG_EMBEDDING.format(hash=q_hash)
    try:
        vector = await cache_service.get(emb_cache_key)
        if not vector:
            vector = await ctx.embeddings.aembed_query(query)
            if vector:
                await cache_service.set(emb_cache_key, vector, ttl=settings.cache_ttl_rag_query)
        return vector or []
    except Exception as exc:
        log_json(logger, logging.WARNING, "Embedding failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Level-2 cache: pgvector similarity search
# ---------------------------------------------------------------------------

async def vector_search(
    ctx: "QueryContext",
    book_ids: List[str],
    query_vector: Optional[List[float]] = None,
) -> List[dict]:
    """Cached pgvector similarity search.

    Uses *query_vector* when provided; falls back to ``ctx.query_vector``.
    Returns a list of dicts with keys: text, score, page, title, volume, author, book_id.
    """
    effective_vector = query_vector if query_vector is not None else ctx.query_vector
    if not effective_vector:
        return []

    from app.db.repositories.chunks import ChunksRepository
    chunks_repo = ChunksRepository(ctx.session)

    emb_hash = hashlib.md5(str(effective_vector).encode()).hexdigest()
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
                query_embedding=effective_vector,
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


# ---------------------------------------------------------------------------
# Title lookup
# ---------------------------------------------------------------------------

async def find_books_by_title_in_question(
    question: str, session
) -> Optional[List[str]]:
    """Return IDs for all volumes of a title mentioned in *question*, or None.

    If the question contains a title in «» quotes, exact (normalized) matching
    is tried first so that a quoted title is not accidentally matched to a
    shorter title that shares some words.
    Falls back to word-prefix matching when no «» are present.
    """
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
        # Quoted title present but no exact match — don't fall through to fuzzy
        # (avoids wrong-book answers like the «ئۇيغۇر تارىخى» case).
        return None

    # --- Fuzzy word-prefix match (no quotes in question) ---
    matched_title = next(
        (t for t in title_to_ids if entity_matches_question(t, q)), None
    )
    return title_to_ids[matched_title] if matched_title else None
