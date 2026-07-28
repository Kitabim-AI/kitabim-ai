"""Shared retrieval primitives used across RAG handlers and agent tools.

All I/O-backed retrieval helpers live here — no LLM calls, no prompt logic.
"""

from __future__ import annotations

import asyncio
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
    """Embed *query* with Level-1 cache (shared across all RAG handlers) and request-local cache.

    Returns an empty list on any failure — callers must handle the empty-vector
    case (usually by returning no results rather than crashing).
    """
    query_stripped = query.strip()

    # 1. Request-local memory cache check
    local_cache = getattr(ctx, "_query_embeddings", None)
    if local_cache is None:
        local_cache = {}
        ctx._query_embeddings = local_cache

    if query_stripped in local_cache:
        return local_cache[query_stripped]

    # 2. Redis/External API check
    q_hash = hashlib.md5(query_stripped.encode()).hexdigest()
    emb_cache_key = cache_config.KEY_RAG_EMBEDDING.format(hash=q_hash)
    try:
        vector = await cache_service.get(emb_cache_key)
        if not vector:
            embeddings = getattr(ctx, "embeddings", None)
            if not embeddings:
                log_json(
                    logger,
                    logging.WARNING,
                    "No embeddings provider configured on QueryContext",
                )
                return []
            vector = await embeddings.aembed_query(query)
            if vector:
                await cache_service.set(
                    emb_cache_key, vector, ttl=settings.cache_ttl_rag_query
                )
        if vector:
            local_cache[query_stripped] = vector
        return vector or []
    except Exception as exc:
        log_json(logger, logging.WARNING, "Embedding failed", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# Level-2 cache: pgvector similarity search
# ---------------------------------------------------------------------------


def _fuse_rrf(
    vector_results: List[dict], keyword_results: List[dict], limit: int
) -> List[dict]:
    """Reciprocal Rank Fusion: score(chunk) = sum(1 / (RRF_K + rank)) across
    the rankers where the chunk appears, identified by
    (book_id, page_number, chunk_index). A chunk in only one ranker's results
    still gets a score from that one term. The RRF score is used only to
    order/truncate the fused list — it is NOT written back into a returned
    dict's `similarity` field. RRF scores (~0.01-0.03 for RRF_K=60) and
    cosine similarity (~0-1) aren't on a comparable scale, and several
    downstream consumers (e.g. CONTEXT_SWITCH_SCORE_THRESHOLD in
    agent/tools.py and deterministic_handler.py) compare `similarity`/`score`
    against an absolute threshold calibrated for genuine cosine similarity —
    overwriting it with an RRF value made those checks permanently read
    "weak match" whenever hybrid search was on. Each returned dict keeps
    whichever original score field its source leg gave it: `similarity` for
    a vector hit, nothing (no genuine similarity) for a keyword-only hit."""
    from app.services.rag.agent.config import RRF_K

    def key_of(c: dict) -> tuple:
        return (c.get("book_id"), c.get("page_number"), c.get("chunk_index"))

    scores: dict = {}
    docs: dict = {}
    for rank, c in enumerate(vector_results, start=1):
        k = key_of(c)
        scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
        docs.setdefault(k, c)
    for rank, c in enumerate(keyword_results, start=1):
        k = key_of(c)
        scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
        docs.setdefault(k, c)

    ordered_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:limit]
    fused_docs = []
    for k in ordered_keys:
        doc = dict(docs[k])
        doc["rrf_score"] = scores[k]
        fused_docs.append(doc)
    return fused_docs


async def _search_chunks(
    chunks_repo,
    query_embedding: List[float],
    query_text: str,
    book_ids: Optional[List[str]],
    categories: Optional[List[str]],
    limit: int,
    threshold: float,
    hybrid_enabled: bool,
) -> List[dict]:
    """Vector search, plus — when hybrid_enabled — a parallel Postgres
    keyword search over the same scope, fused via Reciprocal Rank Fusion.
    Falls back to vector-only results if the keyword leg errors (e.g. a
    malformed tsquery from unusual input) — equivalent to hybrid search being
    off for that one call, not a whole-turn failure."""
    vector_results = await chunks_repo.similarity_search(
        query_embedding=query_embedding,
        book_ids=book_ids,
        categories=categories,
        limit=limit,
        threshold=threshold,
    )
    if not hybrid_enabled:
        return vector_results

    try:
        keyword_results = await chunks_repo.keyword_search(
            query_text=query_text,
            book_ids=book_ids,
            categories=categories,
            limit=limit,
        )
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Keyword search leg failed, falling back to vector-only for this call",
            error=str(exc),
        )
        return vector_results

    fused = _fuse_rrf(vector_results, keyword_results, limit=limit)
    log_json(
        logger,
        logging.INFO,
        "Hybrid search fused vector + keyword results",
        vector_hits=len(vector_results),
        keyword_hits=len(keyword_results),
        fused_count=len(fused),
    )
    return fused


async def vector_search(
    ctx: "QueryContext",
    book_ids: Optional[List[str]],
    query_vector: Optional[List[float]] = None,
) -> List[dict]:
    """Cached pgvector similarity search.

    Uses *query_vector* when provided; falls back to ``ctx.query_vector``.
    Returns a list of dicts with keys: text, score, page, title, volume, author, book_id.
    """
    effective_vector = query_vector if query_vector is not None else ctx.query_vector
    if not effective_vector:
        return []

    # Explicit empty list means discovery tools returned nothing — don't fall back to global scan.
    if book_ids is not None and not book_ids:
        return []

    from app.core.providers import get_vector_store
    from app.db.repositories.system_configs_repository import SystemConfigsRepository

    chunks_repo = get_vector_store(ctx.session)

    configs_repo = SystemConfigsRepository(ctx.session)
    hybrid_enabled = (
        await configs_repo.get_value("rag_hybrid_search_enabled", "true")
    ).lower() == "true"
    rag_top_k_str = await configs_repo.get_value("rag_top_k", str(settings.rag_top_k))
    try:
        rag_top_k = int(rag_top_k_str)
    except ValueError:
        rag_top_k = settings.rag_top_k
    keyword_query_text = ctx.enriched_question or ctx.question

    emb_hash = hashlib.md5(str(effective_vector).encode()).hexdigest()
    sorted_book_ids = sorted(book_ids) if book_ids else []
    book_ids_hash = (
        hashlib.md5(",".join(sorted_book_ids).encode()).hexdigest()
        if sorted_book_ids
        else "all"
    )

    if ctx.character_categories:
        cat_hash = hashlib.md5(
            ",".join(sorted(ctx.character_categories)).encode()
        ).hexdigest()
        book_ids_hash += f"_cat_{cat_hash}"

    if not ctx.is_global and len(sorted_book_ids) == 1 and not ctx.character_categories:
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
            if len(sorted_book_ids) > 1:
                # Multi-book named-title questions (e.g. "compare book A, B
                # and C") would otherwise compete for one global top-K ranked
                # across every book's chunks combined — whichever book scores
                # highest can crowd out the others entirely. Guarantee each
                # named book a minimum slice instead of letting a single
                # embedding-similarity ranking decide.
                per_book_limit = max(rag_top_k // len(sorted_book_ids), 3)
                per_book_results = await asyncio.gather(
                    *[
                        _search_chunks(
                            chunks_repo,
                            query_embedding=effective_vector,
                            query_text=keyword_query_text,
                            book_ids=[bid],
                            categories=ctx.character_categories or None,
                            limit=per_book_limit,
                            threshold=settings.rag_score_threshold,
                            hybrid_enabled=hybrid_enabled,
                        )
                        for bid in sorted_book_ids
                    ]
                )
                similar_chunks = [
                    chunk for chunks in per_book_results for chunk in chunks
                ]
                similar_chunks.sort(
                    key=lambda c: (c.get("rrf_score", 0.0), c.get("similarity", 0.0)),
                    reverse=True,
                )
            else:
                similar_chunks = await _search_chunks(
                    chunks_repo,
                    query_embedding=effective_vector,
                    query_text=keyword_query_text,
                    book_ids=book_ids,
                    categories=ctx.character_categories or None,
                    limit=rag_top_k,
                    threshold=settings.rag_score_threshold,
                    hybrid_enabled=hybrid_enabled,
                )

            if not similar_chunks:
                # If vector search with strict threshold returns 0 chunks (e.g. meta/summary
                # questions, or a cold-start global query whose phrasing doesn't score above
                # threshold against body text), retry without threshold to guarantee the top
                # matching chunks are retrieved instead of an empty turn. Applies to both
                # book-scoped and global (book_ids=None) searches.
                if len(sorted_book_ids) > 1:
                    per_book_limit = max(rag_top_k // len(sorted_book_ids), 3)
                    per_book_results = await asyncio.gather(
                        *[
                            _search_chunks(
                                chunks_repo,
                                query_embedding=effective_vector,
                                query_text=keyword_query_text,
                                book_ids=[bid],
                                categories=ctx.character_categories or None,
                                limit=per_book_limit,
                                threshold=0.0,
                                hybrid_enabled=hybrid_enabled,
                            )
                            for bid in sorted_book_ids
                        ]
                    )
                    similar_chunks = [
                        chunk for chunks in per_book_results for chunk in chunks
                    ]
                    similar_chunks.sort(
                        key=lambda c: (
                            c.get("rrf_score", 0.0),
                            c.get("similarity", 0.0),
                        ),
                        reverse=True,
                    )
                else:
                    similar_chunks = await _search_chunks(
                        chunks_repo,
                        query_embedding=effective_vector,
                        query_text=keyword_query_text,
                        book_ids=book_ids,
                        categories=ctx.character_categories or None,
                        limit=rag_top_k,
                        threshold=0.0,
                        hybrid_enabled=hybrid_enabled,
                    )
            top_results = [
                {
                    "text": chunk.get("text", ""),
                    "score": chunk.get("similarity", 0.0),
                    "rrf_score": chunk.get("rrf_score", 0.0),
                    "rank": chunk.get("rank"),
                    "page": chunk.get("page_number"),
                    "title": chunk.get("title") or "Unknown",
                    "volume": chunk.get("volume"),
                    "author": chunk.get("author") or None,
                    "book_id": chunk.get("book_id"),
                }
                for chunk in similar_chunks
            ]

            # Fallback to database text matching when vector embeddings are missing
            # (common in local dev dumps). Never runs in production — a genuine
            # zero-hit vector search there means "nothing relevant", not "no
            # embeddings backfilled yet", and this fuzzy match must not be mistaken
            # for a real semantic match.
            used_fallback = False
            if not top_results and book_ids and settings.environment != "production":
                from sqlalchemy import select, and_, or_
                from app.db.models import Chunk, Book, Page
                from app.services.rag.utils import (
                    normalize_uyghur,
                    fuzzy_token_similar,
                    PUNCTUATION_STRIP_CHARS,
                )

                try:
                    stmt = (
                        select(
                            Chunk.book_id,
                            Chunk.page_number,
                            Chunk.chunk_index,
                            Chunk.text,
                            Book.title,
                            Book.volume,
                            Book.author,
                        )
                        .join(Book, Chunk.book_id == Book.id)
                        .outerjoin(
                            Page,
                            and_(
                                Chunk.book_id == Page.book_id,
                                Chunk.page_number == Page.page_number,
                            ),
                        )
                        .where(
                            Chunk.book_id.in_(book_ids),
                            or_(Page.is_toc.is_not(True), Page.id.is_(None)),
                        )
                        .order_by(Chunk.page_number.asc(), Chunk.chunk_index.asc())
                        .limit(1000)
                    )
                    db_res = await ctx.session.execute(stmt)
                    all_chunks = db_res.fetchall()

                    q_norm = normalize_uyghur(ctx.question or "")
                    q_words = [w.strip(PUNCTUATION_STRIP_CHARS) for w in q_norm.split()]
                    q_words = [w for w in q_words if w and len(w) >= 3]

                    if q_words:
                        matched_chunks = []
                        for row in all_chunks:
                            chunk_text = normalize_uyghur(row[3] or "")

                            # Check how many query keywords match this chunk (prefix or fuzzy)
                            match_count = 0
                            for qw in q_words:
                                if qw in chunk_text:
                                    match_count += 1
                                    continue
                                # Fuzzy spelling tolerance matching
                                if any(
                                    fuzzy_token_similar(
                                        qw,
                                        cw.strip(PUNCTUATION_STRIP_CHARS),
                                        threshold=0.8,
                                    )
                                    for cw in chunk_text.split()
                                ):
                                    match_count += 1

                            if match_count > 0:
                                matched_chunks.append(
                                    {"row": row, "match_count": match_count}
                                )

                        # Sort by match count DESC, then by page/index ASC
                        matched_chunks.sort(
                            key=lambda x: (-x["match_count"], x["row"][1], x["row"][2])
                        )

                        top_results = [
                            {
                                "text": mc["row"][3],
                                "score": 0.8 + (0.05 * mc["match_count"]),
                                "page": mc["row"][1],
                                "title": mc["row"][4] or "Unknown",
                                "volume": mc["row"][5],
                                "author": mc["row"][6] or None,
                                "book_id": mc["row"][0],
                            }
                            for mc in matched_chunks[:rag_top_k]
                        ]
                        used_fallback = bool(top_results)
                except Exception as exc:
                    log_json(
                        logger,
                        logging.WARNING,
                        "Fuzzy text search fallback failed",
                        error=str(exc),
                    )

            # 2. Integrate Quran vector search
            from app.services.rag.utils import is_islam_or_quran_query
            from sqlalchemy import text as sa_text

            is_islam = is_islam_or_quran_query(ctx.question) or (
                ctx.enriched_question and is_islam_or_quran_query(ctx.enriched_question)
            )

            if is_islam:
                embedding_str = str(effective_vector)
                # Query Quran table using pgvector
                quran_query = sa_text("""
                    SELECT 
                        id, surah, surah_name_en, surah_name_ar, surah_name_ug,
                        ayah, text_ar, text_en, text_ug,
                        1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
                    FROM quran
                    WHERE embedding IS NOT NULL
                    ORDER BY embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))
                    LIMIT :limit
                """)
                res = await ctx.session.execute(
                    quran_query,
                    {"embedding": embedding_str, "limit": rag_top_k},
                )
                rows = res.fetchall()

                quran_results = []
                for row in rows:
                    similarity = float(row.similarity)
                    if similarity >= settings.rag_score_threshold:
                        quran_results.append(
                            {
                                "text": f"Arabic: {row.text_ar}\nUyghur Translation: {row.text_ug}\nEnglish Translation: {row.text_en}",
                                "score": similarity,
                                "page": row.ayah,
                                "title": row.surah_name_ug,
                                "surah_name_en": row.surah_name_en,
                                "surah_name_ar": row.surah_name_ar,
                                "surah": row.surah,
                                "ayah": row.ayah,
                                "volume": row.surah,
                                "author": "Holy Quran",
                                "book_id": "quran",
                            }
                        )

                # Merge, sort globally by score, and limit
                top_results = top_results + quran_results
                top_results.sort(key=lambda x: x["score"], reverse=True)
                top_results = top_results[:rag_top_k]

            # Never cache fuzzy-fallback results under the same key real vector
            # search hits use — once real embeddings are backfilled, a stale
            # cached fallback entry must not keep shadowing them.
            if top_results is not None and not used_fallback:
                await cache_service.set(
                    search_cache_key, top_results, ttl=settings.cache_ttl_rag_query
                )
        return top_results or []
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Vector search failed",
            exc_type=type(exc).__name__,
            error=str(exc) or repr(exc),
        )
        try:
            await ctx.session.rollback()
        except Exception:
            pass
        raise


# ---------------------------------------------------------------------------
# Title lookup
# ---------------------------------------------------------------------------


async def find_books_by_title_in_question(
    question: str, session, categories: Optional[List[str]] = None
) -> Optional[List[dict]]:
    """Return metadata (id, title, author, volume) for all volumes of a title mentioned in *question*, or None.

    If the question contains a title in «» quotes, exact (normalized) matching
    is tried first so that a quoted title is not accidentally matched to a
    shorter title that shares some words.
    Falls back to word-prefix matching when no «» are present.
    """
    from app.services.rag.utils import entity_matches_question, normalize_uyghur

    q = question.strip()

    stmt = (
        select(Book.id, Book.title, Book.author, Book.volume)
        .where(Book.status != "error")
        .order_by(Book.volume.asc().nulls_first())
    )
    if categories:
        from sqlalchemy import text as sa_text

        stmt = stmt.where(
            sa_text("categories && CAST(:cats AS text[])").bindparams(cats=categories)
        )

    # Use request-level cache if session has info dict to prevent duplicate DB queries
    cache_key = None
    if hasattr(session, "info") and isinstance(session.info, dict):
        cat_hash = (
            hashlib.md5(",".join(sorted(categories)).encode()).hexdigest()
            if categories
            else "all"
        )
        cache_key = f"find_books_by_title_rows_{cat_hash}"

    if cache_key and cache_key in session.info:
        rows = session.info[cache_key]
    else:
        title_result = await session.execute(stmt)
        rows = title_result.fetchall()
        if cache_key is not None:
            session.info[cache_key] = rows

    title_to_books: dict = {}
    for row in rows:
        book_id, title, author, volume = str(row[0]), row[1], row[2], row[3]
        if title:
            title_to_books.setdefault(title, []).append(
                {
                    "id": book_id,
                    "title": title,
                    "author": author,
                    "volume": volume,
                }
            )

    # --- Exact match for «quoted» titles ---
    quoted = re.findall(r"«([^»]+)»", q)
    if quoted:
        # Collect a match for every quoted title (not just the first one) so
        # "«Book A» بىلەن «Book B» نى سېلىشتۇر" resolves both books.
        matched_titles: list = []
        matched_books: list = []
        for candidate in quoted:
            candidate_norm = normalize_uyghur(candidate.strip())
            for title, books in title_to_books.items():
                if (
                    normalize_uyghur(title.strip()) == candidate_norm
                    and title not in matched_titles
                ):
                    matched_titles.append(title)
                    matched_books.extend(books)
                    break
        # Quoted titles present but none matched — don't fall through to fuzzy
        # (avoids wrong-book answers like the «ئۇيغۇر تارىخى» case).
        return matched_books if matched_books else None

    # --- Fuzzy word-prefix match (no quotes in question) ---
    # Collect ALL matching titles so multi-book questions return info for every
    # named book (not just the first one that happens to match).
    matching_titles: list[str] = []
    for title in title_to_books.keys():
        if entity_matches_question(title, q):
            matching_titles.append(title)

    # Filter out titles that are strict subsets of other matched titles.
    # For example, if both "لېيىغان بۇلاق" and "بۇلاق" matched, we keep "لېيىغان بۇلاق"
    # and discard "بۇلاق" because its words are a subset of the longer title.
    # Normalize variants before checking subset relationship.
    filtered_titles = []
    for title in matching_titles:
        title_norm = normalize_uyghur(title.strip())
        title_words = set(title_norm.split())

        is_subset = False
        for other in matching_titles:
            if title == other:
                continue
            other_norm = normalize_uyghur(other.strip())
            other_words = set(other_norm.split())
            if title_words.issubset(other_words) and len(title_words) < len(
                other_words
            ):
                is_subset = True
                break
        if not is_subset:
            filtered_titles.append(title)

    all_matching_books: list = []
    for title in filtered_titles:
        all_matching_books.extend(title_to_books[title])
    return all_matching_books if all_matching_books else None
