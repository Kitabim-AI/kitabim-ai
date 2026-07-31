"""Shared retrieval primitives used across RAG handlers and agent tools.

All I/O-backed retrieval helpers live here — no LLM calls, no prompt logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from typing import TYPE_CHECKING, List, Optional, Tuple

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


def _fuse_rrf(*result_lists: List[dict], limit: int) -> Tuple[List[dict], dict]:
    """Reciprocal Rank Fusion: score(chunk) = sum(1 / (RRF_K + rank)) across
    the rankers where the chunk appears, identified by
    (book_id, page_number, chunk_index). Supports arbitrary number of result
    lists (vector_results as first list, followed by keyword result lists).
    The RRF score is used only to order/truncate the fused list — it is NOT written back
    into a returned dict's `similarity` field. RRF scores (~0.01-0.03 for RRF_K=60)
    and cosine similarity (~0-1) aren't on a comparable scale, and several
    downstream consumers (e.g. CONTEXT_SWITCH_SCORE_THRESHOLD in
    agent/tools.py and deterministic_handler.py) compare `similarity`/`score`
    against an absolute threshold calibrated for genuine cosine similarity —
    overwriting it with an RRF value made those checks permanently read
    "weak match" whenever hybrid search was on. Each returned dict keeps
    whichever original score field its source leg gave it: `similarity` for
    a vector hit, nothing (no genuine similarity) for a keyword-only hit.

    Returns a tuple of (fused_docs, stats_dict)."""
    from app.services.rag.agent.config import RRF_K

    def key_of(c: dict) -> tuple:
        return (c.get("book_id"), c.get("page_number"), c.get("chunk_index"))

    scores: dict = {}
    docs: dict = {}
    vector_keys = set()
    keyword_keys = set()

    if result_lists:
        for rank, c in enumerate(result_lists[0], start=1):
            k = key_of(c)
            vector_keys.add(k)
            scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
            docs.setdefault(k, c)

        for kw_list in result_lists[1:]:
            for rank, c in enumerate(kw_list, start=1):
                k = key_of(c)
                keyword_keys.add(k)
                scores[k] = scores.get(k, 0.0) + 1.0 / (RRF_K + rank)
                docs.setdefault(k, c)

    ordered_keys = sorted(scores.keys(), key=lambda k: scores[k], reverse=True)[:limit]
    fused_docs = []
    final_vector_only = 0
    final_keyword_only = 0
    final_both = 0

    for k in ordered_keys:
        doc = dict(docs[k])
        doc["rrf_score"] = scores[k]
        in_vec = k in vector_keys
        in_kw = k in keyword_keys
        if in_vec and in_kw:
            final_both += 1
        elif in_vec:
            final_vector_only += 1
        else:
            final_keyword_only += 1
        fused_docs.append(doc)

    stats = {
        "vector_hits": len(vector_keys),
        "keyword_hits": len(keyword_keys),
        "fused_count": len(fused_docs),
        "final_from_vector": final_vector_only + final_both,
        "final_from_keyword": final_keyword_only + final_both,
        "final_vector_only": final_vector_only,
        "final_keyword_only": final_keyword_only,
        "final_both": final_both,
    }
    return fused_docs, stats


async def _search_chunks(
    chunks_repo,
    query_embedding: List[float],
    query_text: str,
    book_ids: Optional[List[str]],
    categories: Optional[List[str]],
    limit: int,
    threshold: float,
    hybrid_enabled: bool,
    allow_unscoped_keyword: bool = True,
) -> List[dict]:
    """Vector search, plus — when hybrid_enabled — a parallel Postgres
    keyword search leg (both scoped and unscoped when book_ids is provided
    and allow_unscoped_keyword is True), fused via Reciprocal Rank Fusion.
    Falls back to vector-only results if the keyword legs error (e.g. a
    malformed tsquery from unusual input) — equivalent to hybrid search being
    off for that one call, not a whole-turn failure.

    NOTE: the two keyword legs below share *chunks_repo* (one AsyncSession)
    and are gathered concurrently — a single session/connection can only run
    one statement at a time, so this pair silently serializes rather than
    erroring. Left as-is (small, bounded cost — at most 2 legs); the caller
    is responsible for giving each *book* its own session/repo when fanning
    this call out per book, since that fan-out is unbounded and was the
    dominant cost observed in production (see vector_search()).
    """
    import time

    vector_start = time.perf_counter()
    vector_results = await chunks_repo.similarity_search(
        query_embedding=query_embedding,
        book_ids=book_ids,
        categories=categories,
        limit=limit,
        threshold=threshold,
    )
    vector_ms = round((time.perf_counter() - vector_start) * 1000)
    if not hybrid_enabled:
        return vector_results

    keyword_start = time.perf_counter()
    try:
        if book_ids:
            leg_labels = ["scoped"]
            tasks = [
                chunks_repo.keyword_search(
                    query_text=query_text,
                    book_ids=book_ids,
                    categories=categories,
                    limit=limit,
                )
            ]
            if allow_unscoped_keyword:
                leg_labels.append("unscoped")
                tasks.append(
                    chunks_repo.keyword_search(
                        query_text=query_text,
                        book_ids=None,
                        categories=categories,
                        limit=limit,
                    )
                )

            results = await asyncio.gather(*tasks, return_exceptions=True)
            keyword_legs = [r for r in results if isinstance(r, list)]
            keyword_ms = round((time.perf_counter() - keyword_start) * 1000)
            # A partial failure (e.g. the unscoped leg hitting statement_timeout
            # while the scoped leg succeeds) previously left no trace at all —
            # keyword_leg_count would just read lower with no explanation why.
            failed_legs = [
                {"leg": label, "error": str(r)}
                for label, r in zip(leg_labels, results)
                if not isinstance(r, list)
            ]
            if failed_legs:
                log_json(
                    logger,
                    logging.WARNING,
                    "One or more keyword search legs failed or timed out",
                    failed_legs=failed_legs,
                )
            if not keyword_legs:
                log_json(
                    logger,
                    logging.WARNING,
                    "Keyword search legs failed, falling back to vector-only for this call",
                )
                return vector_results
            fused, stats = _fuse_rrf(vector_results, *keyword_legs, limit=limit)
            log_json(
                logger,
                logging.INFO,
                "Hybrid search fused vector + keyword results",
                keyword_leg_count=len(keyword_legs),
                vector_ms=vector_ms,
                keyword_ms=keyword_ms,
                **stats,
            )
            return fused
        else:
            keyword_results = await chunks_repo.keyword_search(
                query_text=query_text,
                book_ids=None,
                categories=categories,
                limit=limit,
            )
            keyword_ms = round((time.perf_counter() - keyword_start) * 1000)
            fused, stats = _fuse_rrf(vector_results, keyword_results, limit=limit)
            log_json(
                logger,
                logging.INFO,
                "Hybrid search fused vector + keyword results",
                vector_ms=vector_ms,
                keyword_ms=keyword_ms,
                **stats,
            )
            return fused
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "Keyword search leg failed, falling back to vector-only for this call",
            error=str(exc),
        )
        return vector_results


async def vector_search(
    ctx: "QueryContext",
    book_ids: Optional[List[str]],
    query_vector: Optional[List[float]] = None,
    keywords: Optional[List[str]] = None,
) -> List[dict]:
    """Cached pgvector similarity search.

    Uses *query_vector* when provided; falls back to ``ctx.query_vector``.
    *keywords*, when provided, replaces the whole question as the keyword-search
    leg's input text — the caller (agent tool) is expected to have already
    stripped grammatical filler, so the tsquery built from it stays small
    instead of matching a huge fraction of the table on a common word.
    Falls back to the full question when omitted, unchanged from before.
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
    from app.db.session import async_session_factory

    chunks_repo = get_vector_store(ctx.session)

    async def _search_book_isolated(
        bid: str, limit: int, threshold: float, allow_unscoped: bool
    ) -> List[dict]:
        # Own session per book: asyncio.gather over _search_chunks calls that
        # all shared ctx.session's single connection was serializing what
        # looked like concurrent per-book searches into N sequential ones —
        # the dominant cost in a since-fixed production slowdown (multi-book
        # questions taking minutes instead of seconds).
        async with async_session_factory() as book_session:
            return await _search_chunks(
                get_vector_store(book_session),
                query_embedding=effective_vector,
                query_text=keyword_query_text,
                book_ids=[bid],
                categories=ctx.character_categories or None,
                limit=limit,
                threshold=threshold,
                hybrid_enabled=hybrid_enabled,
                allow_unscoped_keyword=allow_unscoped,
            )

    configs_repo = SystemConfigsRepository(ctx.session)
    hybrid_enabled = (
        await configs_repo.get_value("rag_hybrid_search_enabled", "true")
    ).lower() == "true"
    rag_top_k_str = await configs_repo.get_value("rag_top_k", str(settings.rag_top_k))
    try:
        rag_top_k = int(rag_top_k_str)
    except ValueError:
        rag_top_k = settings.rag_top_k
    keyword_query_text = (
        " ".join(keywords) if keywords else (ctx.enriched_question or ctx.question)
    )

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
                allow_unscoped = getattr(ctx, "is_global", True)
                per_book_limit = max(rag_top_k // len(sorted_book_ids), 3)
                per_book_results = await asyncio.gather(
                    *[
                        _search_book_isolated(
                            bid,
                            limit=per_book_limit,
                            threshold=settings.rag_score_threshold,
                            allow_unscoped=allow_unscoped,
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
                    allow_unscoped_keyword=getattr(ctx, "is_global", True),
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
                            _search_book_isolated(
                                bid,
                                limit=per_book_limit,
                                threshold=0.0,
                                allow_unscoped=allow_unscoped,
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
                        allow_unscoped_keyword=getattr(ctx, "is_global", True),
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
# Knowledge-graph entity lookup (design v2 §6)
# ---------------------------------------------------------------------------


async def graph_entity_lookup(question: str) -> List[dict]:
    """Query-time knowledge-graph lookup — Redis cache read with prefix enumeration (B1),
    partial-name token-intersection & IDF specificity scoring (B2), and miss-only
    Neo4j full-text fuzzy fallback (B3). No LLM call is made here.

    Returns [] on no match — callers fall back to the existing hybrid text search
    unchanged. On a match, returns chunk-shaped dicts (`text`/`score`/`page`/`title`/
    `book_id`) so the rest of the RAG pipeline (grading, Document conversion,
    citations) handles them exactly like any other retrieved chunk.
    """
    import math
    from app.core import cache_config
    from app.services.cache_service import cache_service
    from app.services.rag.utils import normalize_uyghur, PUNCTUATION_STRIP_CHARS
    from app.services.entity_resolution_service import (
        normalize_alias,
        TITLES_HONORIFICS,
    )
    from app.db.repositories.graph_repository import GraphRepository

    import hashlib

    q_hash = hashlib.md5(question.encode("utf-8")).hexdigest()
    cache_key = f"rag_graph_lookup:{q_hash}"
    try:
        cached_results = await cache_service.get(cache_key)
        if cached_results is not None:
            return cached_results
    except Exception:
        pass

    raw_words = [
        w.strip(PUNCTUATION_STRIP_CHARS) for w in normalize_uyghur(question).split()
    ]
    words = [w for w in raw_words if len(w) >= 3]
    if not words:
        return []

    # 1. Generate prefix candidates per word (B1)
    word_prefix_candidates: dict[int, list[str]] = {}
    for idx, w in enumerate(words):
        norm_w = normalize_alias(w)
        prefixes = []
        min_prefix_len = min(len(norm_w), 4)
        for length in range(len(norm_w), min_prefix_len - 1, -1):
            prefixes.append(norm_w[:length])
        word_prefix_candidates[idx] = list(dict.fromkeys(prefixes))

    candidate_keys_to_lookup: set[str] = set()

    # Bigrams & full phrase
    for a, b in zip(words, words[1:]):
        candidate_keys_to_lookup.add(normalize_alias(f"{a} {b}"))
    if len(words) >= 3:
        candidate_keys_to_lookup.add(normalize_alias(" ".join(words)))

    # Prefix stems for single words
    for idx, p_list in word_prefix_candidates.items():
        for p in p_list:
            candidate_keys_to_lookup.add(p)

    alias_to_ids: dict[str, list[str]] = {}
    try:
        for candidate in candidate_keys_to_lookup:
            key = cache_config.KEY_GRAPH_ALIAS_LOOKUP.format(alias=candidate)
            ids = await cache_service.get(key)
            if ids:
                alias_to_ids[candidate] = ids
    except Exception as exc:
        log_json(
            logger, logging.WARNING, "graph alias cache lookup failed", error=str(exc)
        )
        return []

    # 2. Select best matches per word token (longest prefix hit) & phrase matches (B1 & B2)
    entity_matched_tokens: dict[str, set[int]] = {}
    entity_is_phrase_match: dict[str, bool] = {}
    alias_doc_freq: dict[str, int] = {}

    for alias_key, ids in alias_to_ids.items():
        alias_doc_freq[alias_key] = len(ids)

    # Check multi-word phrase / bigram hits first
    for a_idx in range(len(words) - 1):
        w1, w2 = words[a_idx], words[a_idx + 1]
        bigram_key = normalize_alias(f"{w1} {w2}")
        if bigram_key in alias_to_ids:
            for eid in alias_to_ids[bigram_key]:
                entity_matched_tokens.setdefault(eid, set()).update({a_idx, a_idx + 1})
                entity_is_phrase_match[eid] = True

    # For each word index, find the longest matching prefix key
    for idx, p_list in word_prefix_candidates.items():
        for p in p_list:
            if p in alias_to_ids:
                for eid in alias_to_ids[p]:
                    entity_matched_tokens.setdefault(eid, set()).add(idx)
                break

    entity_scores: dict[str, float] = {}
    if entity_matched_tokens:
        max_tokens_matched = max(
            len(tokens) for tokens in entity_matched_tokens.values()
        )

        surviving_ids = set()
        for eid, matched_indices in entity_matched_tokens.items():
            if max_tokens_matched >= 2 and len(matched_indices) < max_tokens_matched:
                continue
            surviving_ids.add(eid)

            is_phrase = entity_is_phrase_match.get(eid, False)
            base_score = 0.95 if (is_phrase or len(matched_indices) >= 2) else 0.85

            matched_freqs = [
                alias_doc_freq[k] for k, ids in alias_to_ids.items() if eid in ids
            ]
            min_freq = min(matched_freqs) if matched_freqs else 1
            if min_freq > 1:
                idf_weight = 1.0 / (1.0 + 0.1 * math.log(min_freq))
                entity_scores[eid] = round(base_score * idf_weight, 3)
            else:
                entity_scores[eid] = base_score

        matched_ids = surviving_ids
    else:
        matched_ids = set()

    graph_repo = GraphRepository()

    # 3. Miss-Only Neo4j Full-Text Fuzzy Fallback (B3)
    if not matched_ids:
        query_terms = [w for w in words if len(w) >= 4 and w not in TITLES_HONORIFICS]
        if query_terms:
            try:
                fuzzy_hits = await graph_repo.search_entities_fulltext(
                    query_terms, edit_distance=1, limit=5
                )
                for hit in fuzzy_hits:
                    eid = hit["id"]
                    matched_ids.add(eid)
                    entity_scores[eid] = 0.80
            except Exception as exc:
                log_json(
                    logger,
                    logging.WARNING,
                    "graph fuzzy fulltext fallback failed",
                    error=str(exc),
                )

    if not matched_ids:
        return []

    results: List[dict] = []
    try:
        facts_map = await graph_repo.get_entities_facts_for_citation_bulk(
            list(matched_ids)
        )
        if not isinstance(facts_map, dict):
            facts_map = {}
    except Exception:
        facts_map = {}

    for entity_id in matched_ids:
        facts = facts_map.get(entity_id)
        if facts is None:
            try:
                facts = await graph_repo.get_entity_facts_for_citation(entity_id)
            except Exception:
                facts = []
        if not isinstance(facts, list):
            continue
        for fact in facts:
            results.append(
                {
                    "text": fact["text"],
                    "score": entity_scores.get(entity_id, 0.9),
                    "page": fact.get("page"),
                    "title": "Knowledge Graph",
                    "volume": None,
                    "author": None,
                    "book_id": fact.get("book_id") or "knowledge_graph",
                }
            )

    try:
        await cache_service.set(cache_key, results, ttl=60)
    except Exception:
        pass

    return results


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
