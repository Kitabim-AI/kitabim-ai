"""Shared retrieval primitives used across RAG handlers and agent tools.

All I/O-backed retrieval helpers live here — no LLM calls, no prompt logic.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import select

from app.core import cache_config
from app.core.config import settings
from app.core.i18n import t
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


async def exact_phrase_chunk_search(
    chunks_repo,
    phrases: List[str],
    book_ids: Optional[List[str]],
    categories: Optional[List[str]],
    limit: int,
) -> List[dict]:
    """Keyword-only exact-phrase retrieval — the phrase-search-intent leg
    (see keyword-search-rework-plan.md Phase 1). No vector or graph fusion:
    phrase mode is keyword-only by design.

    Multiple phrases are ANDed together (a result must contain all of them),
    per the resolved decision on multi-phrase queries — implemented as one
    `keyword_search` call per phrase, intersected by (book_id, page_number).
    """
    if not phrases:
        return []

    per_phrase_results = await asyncio.gather(
        *[
            chunks_repo.keyword_search(
                phrase=phrase,
                book_ids=book_ids,
                categories=categories,
                limit=limit,
            )
            for phrase in phrases
        ]
    )

    def key_of(c: dict) -> tuple:
        page_val = c.get("page") if c.get("page") is not None else c.get("page_number")
        return (c.get("book_id"), page_val)

    common_keys = None
    docs: dict = {}
    for leg in per_phrase_results:
        leg_keys = set()
        for c in leg:
            k = key_of(c)
            leg_keys.add(k)
            docs.setdefault(k, c)
        common_keys = leg_keys if common_keys is None else (common_keys & leg_keys)

    if not common_keys:
        return []

    matched = [docs[k] for k in common_keys]
    matched.sort(key=lambda c: c.get("rank", 0.0), reverse=True)
    return matched[:limit]


async def vector_search(
    ctx: "QueryContext",
    book_ids: Optional[List[str]],
    query_vector: Optional[List[float]] = None,
) -> List[dict]:
    """Cached pgvector similarity search — vector-only.

    Uses *query_vector* when provided; falls back to ``ctx.query_vector``.
    The keyword leg never blends with vector results (see
    exact_phrase_chunk_search / keyword-search-rework-plan.md Phase 1) — it
    runs standalone, only for exact-phrase-search intent.
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
        bid: str, limit: int, threshold: float
    ) -> List[dict]:
        # Own session per book: asyncio.gather over similarity_search calls
        # that all shared ctx.session's single connection was serializing
        # what looked like concurrent per-book searches into N sequential
        # ones — the dominant cost in a since-fixed production slowdown
        # (multi-book questions taking minutes instead of seconds).
        async with async_session_factory() as book_session:
            return await get_vector_store(book_session).similarity_search(
                query_embedding=effective_vector,
                book_ids=[bid],
                categories=ctx.character_categories or None,
                limit=limit,
                threshold=threshold,
            )

    configs_repo = SystemConfigsRepository(ctx.session)
    rag_top_k_str = await configs_repo.get_value(
        "rag_vector_top_k", str(settings.rag_top_k)
    )
    try:
        rag_top_k = int(rag_top_k_str)
    except ValueError:
        rag_top_k = settings.rag_top_k

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
                        _search_book_isolated(
                            bid,
                            limit=per_book_limit,
                            threshold=settings.rag_score_threshold,
                        )
                        for bid in sorted_book_ids
                    ]
                )
                similar_chunks = [
                    chunk for chunks in per_book_results for chunk in chunks
                ]
                similar_chunks.sort(
                    key=lambda c: c.get("similarity", 0.0),
                    reverse=True,
                )
            else:
                similar_chunks = await chunks_repo.similarity_search(
                    query_embedding=effective_vector,
                    book_ids=book_ids,
                    categories=ctx.character_categories or None,
                    limit=rag_top_k,
                    threshold=settings.rag_score_threshold,
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
                            )
                            for bid in sorted_book_ids
                        ]
                    )
                    similar_chunks = [
                        chunk for chunks in per_book_results for chunk in chunks
                    ]
                    similar_chunks.sort(
                        key=lambda c: c.get("similarity", 0.0),
                        reverse=True,
                    )
                else:
                    similar_chunks = await chunks_repo.similarity_search(
                        query_embedding=effective_vector,
                        book_ids=book_ids,
                        categories=ctx.character_categories or None,
                        limit=rag_top_k,
                        threshold=0.0,
                    )
            top_results = [
                {
                    "text": chunk.get("text", ""),
                    "score": chunk.get("similarity", 0.0),
                    "page": chunk.get("page_number")
                    if chunk.get("page") is None
                    else chunk.get("page"),
                    "page_number": chunk.get("page_number")
                    if chunk.get("page") is None
                    else chunk.get("page"),
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
                                "page_number": mc["row"][1],
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


async def graph_entity_lookup(question: str, top_k: int = 10) -> List[dict]:
    """Query-time knowledge-graph lookup — Redis cache read with prefix enumeration (B1),
    partial-name token-intersection & IDF specificity scoring (B2), and miss-only
    Neo4j full-text fuzzy fallback (B3). No LLM call is made here.

    Returns [] on no match — callers fall back to the existing hybrid text search
    unchanged. On a match, returns chunk-shaped dicts (`text`/`score`/`page`/`title`/
    `book_id`) so the rest of the RAG pipeline (grading, Document conversion,
    citations) handles them exactly like any other retrieved chunk.

    *top_k* caps the number of facts returned (highest-scoring first) — the
    matching stages above (B1/B2/B3) are otherwise uncapped, and a broad
    question can surface many entities. The cache holds the full uncapped
    result set so a later call with a different top_k isn't stuck with a
    stale, differently-truncated cached list.
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
            return sorted(cached_results, key=lambda r: r["score"], reverse=True)[
                :top_k
            ]
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
            page_val = (
                fact.get("page")
                if fact.get("page") is not None
                else fact.get("page_number")
            )
            results.append(
                {
                    "text": fact["text"],
                    "score": entity_scores.get(entity_id, 0.9),
                    "page": page_val,
                    "page_number": page_val,
                    "title": t("rag.knowledge_graph_title", default="بىلىم گىرافى"),
                    "volume": None,
                    "author": None,
                    "book_id": fact.get("book_id") or "knowledge_graph",
                }
            )

    try:
        await cache_service.set(cache_key, results, ttl=60)
    except Exception:
        pass

    return sorted(results, key=lambda r: r["score"], reverse=True)[:top_k]


# ---------------------------------------------------------------------------
# Title lookup
# ---------------------------------------------------------------------------


async def find_books_by_title_in_question(
    question: str, session, categories: Optional[List[str]] = None
) -> Optional[List[dict]]:
    """Return metadata (id, title, author, volume) for all volumes of a title mentioned in *question*, or None.

    Uses fuzzy word-prefix matching (Uyghur agglutinative-suffix aware).
    `«...»` has no special effect here — it now signals phrase-search intent
    elsewhere in the RAG pipeline, not a quoted title (keyword-search-rework-plan.md 1.7).
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

    # --- Fuzzy word-prefix match ---
    # `«...»` no longer signals a quoted title (it now means phrase-search
    # intent, see keyword-search-rework-plan.md 1.7) — quoting a title has no
    # special effect here; it resolves the same way whether quoted or not.
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
