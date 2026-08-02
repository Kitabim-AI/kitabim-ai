"""Chunks repository with pgvector similarity search"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, delete, func, or_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Book, Chunk
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger("app.db.repositories.chunks_repository")

# Tuned against a production case where a common word matched ~194K rows and
# took 40-60s: work_mem avoids the disk-bound fallback strategies, the
# timeout bounds whatever it doesn't fix. See keyword_search() below.
_KEYWORD_SEARCH_WORK_MEM = "128MB"
_KEYWORD_SEARCH_STATEMENT_TIMEOUT_MS = "5000"


class ChunksRepository(BaseRepository[Chunk]):
    """
    Repository for chunks with vector similarity search.

    This is critical for RAG functionality using pgvector.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(session, Chunk)

    async def upsert_many(self, chunks: List[dict]) -> None:
        """
        Batch upsert chunks using PostgreSQL INSERT ... ON CONFLICT.

        This replaces executemany with SQLAlchemy's insert().on_conflict_do_update().
        Used during OCR processing to insert/update chunks with embeddings.
        """
        if not chunks:
            return

        stmt = insert(Chunk).values(chunks)
        stmt = stmt.on_conflict_do_update(
            index_elements=["book_id", "page_number", "chunk_index"],
            set_={
                "text": stmt.excluded.text,
                "embedding": stmt.excluded.embedding,
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

    async def delete_by_book(self, book_id: str) -> int:
        """Delete all chunks for a book"""
        stmt = delete(Chunk).where(Chunk.book_id == book_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def delete_by_page(self, book_id: str, page_number: int) -> int:
        """Delete chunks for a specific page"""
        stmt = delete(Chunk).where(
            Chunk.book_id == book_id, Chunk.page_number == page_number
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def find_by_book(self, book_id: str, limit: int = 10000) -> List[Chunk]:
        """Find all chunks for a book"""
        stmt = (
            select(Chunk)
            .where(Chunk.book_id == book_id)
            .order_by(Chunk.page_number, Chunk.chunk_index)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def similarity_search(
        self,
        query_embedding: List[float],
        book_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        limit: int = 12,
        threshold: float = 0.35,
    ) -> List[dict]:
        """
        Vector similarity search using pgvector cosine distance.

        Uses <=> operator for cosine distance: 1 - cosine_distance = similarity score
        Returns chunks with similarity > threshold, ordered by similarity DESC.

        NOTE: This uses raw SQL for optimal pgvector performance.
        SQLAlchemy 2.0 doesn't have native pgvector operators yet.

        Args:
            query_embedding: The query vector (768-dimensional)
            book_ids: Optional list of book UUIDs to filter
            categories: Optional list of categories to filter books by
            limit: Maximum number of results
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of dicts with book_id, page_number, text, similarity, title, and volume
        """
        # Convert embedding to PostgreSQL array format
        embedding_str = str(query_embedding)

        cat_filter = (
            "AND b.categories && CAST(:categories AS text[])" if categories else ""
        )

        # Over-fetch to compensate for TOC rows filtered out in the outer query.
        inner_limit = limit * 3

        # Build query using CTE approach: the inner CTE does pure vector search
        # (allowing the HNSW index to be used), then the outer query filters
        # TOC pages and joins book metadata.  This avoids the expensive
        # chunks×pages join that was preventing index usage and causing timeouts.
        if book_ids is not None:
            if not book_ids:
                return []
            query = text(f"""
                WITH filtered_chunks AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.chunk_index,
                        c.text,
                        c.embedding
                    FROM chunks c
                    WHERE c.book_id = ANY(:book_ids)
                      AND c.embedding IS NOT NULL
                ),
                ranked_matches AS (
                    SELECT
                        fc.book_id,
                        fc.page_number,
                        fc.chunk_index,
                        fc.text,
                        1 - (fc.embedding <=> CAST(:embedding AS vector(3072))) AS similarity
                    FROM filtered_chunks fc
                )
                SELECT
                    rm.book_id,
                    rm.page_number,
                    rm.chunk_index,
                    rm.text,
                    b.title,
                    b.volume,
                    b.author,
                    rm.similarity
                FROM ranked_matches rm
                JOIN books b ON rm.book_id = b.id
                LEFT JOIN pages p ON rm.book_id = p.book_id AND rm.page_number = p.page_number
                WHERE rm.similarity > :threshold
                  AND (p.is_toc IS NOT TRUE OR p.id IS NULL)
                  {cat_filter}
                ORDER BY rm.similarity DESC
                LIMIT :limit
            """)
            params = {
                "embedding": embedding_str,
                "book_ids": [str(bid) for bid in book_ids],
                "threshold": threshold,
                "limit": limit,
            }
            if categories:
                params["categories"] = categories
        else:
            query = text(f"""
                WITH vector_matches AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.chunk_index,
                        c.text,
                        1 - (c.embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
                    FROM chunks c
                    WHERE c.embedding IS NOT NULL
                    ORDER BY c.embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))
                    LIMIT :inner_limit
                )
                SELECT
                    vm.book_id,
                    vm.page_number,
                    vm.chunk_index,
                    vm.text,
                    b.title,
                    b.volume,
                    b.author,
                    vm.similarity
                FROM vector_matches vm
                JOIN books b ON vm.book_id = b.id
                LEFT JOIN pages p ON vm.book_id = p.book_id AND vm.page_number = p.page_number
                WHERE vm.similarity > :threshold
                  AND (p.is_toc IS NOT TRUE OR p.id IS NULL)
                  {cat_filter}
                ORDER BY vm.similarity DESC
                LIMIT :limit
            """)
            params = {
                "embedding": embedding_str,
                "threshold": threshold,
                "limit": limit,
                "inner_limit": inner_limit,
            }
            if categories:
                params["categories"] = categories

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "book_id": str(row.book_id),
                "page_number": row.page_number,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "title": row.title,
                "volume": row.volume,
                "author": row.author,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]

    async def keyword_search(
        self,
        phrase: str,
        book_ids: Optional[List[str]] = None,
        categories: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[dict]:
        """
        Postgres full-text EXACT PHRASE search over `chunks.text_search`
        (a generated tsvector column, migration 074).

        Uses `phraseto_tsquery('simple', ...)` — a contiguous-phrase match
        (word order and adjacency matter), not the old OR-based
        any-word-prefix match. This is FTS phrase-exact, not raw substring
        exact: tokenization, punctuation, normalization, and script-specific
        behavior can still affect matches. Uses the 'simple' text search
        config — matching the column's generation expression — deliberately
        not 'english', since book content is substantially Uyghur-language
        and 'english' stemming rules don't meaningfully apply.

        Mirrors similarity_search's two-branch (scoped/unscoped) shape and
        dict keys (plus a `rank` score in place of `similarity`).
        """
        cat_filter = (
            "AND b.categories && CAST(:categories AS text[])" if categories else ""
        )

        if book_ids is not None:
            if not book_ids:
                return []
            query = text(f"""
                WITH keyword_matches AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.chunk_index,
                        c.text,
                        ts_rank(c.text_search, phraseto_tsquery('simple', :phrase)) AS rank
                    FROM chunks c
                    WHERE c.book_id = ANY(:book_ids)
                      AND c.text_search @@ phraseto_tsquery('simple', :phrase)
                )
                SELECT
                    km.book_id,
                    km.page_number,
                    km.chunk_index,
                    km.text,
                    b.title,
                    b.volume,
                    b.author,
                    km.rank
                FROM keyword_matches km
                JOIN books b ON km.book_id = b.id
                LEFT JOIN pages p ON km.book_id = p.book_id AND km.page_number = p.page_number
                WHERE (p.is_toc IS NOT TRUE OR p.id IS NULL)
                  {cat_filter}
                ORDER BY km.rank DESC
                LIMIT :limit
            """)
            params = {
                "phrase": phrase,
                "book_ids": [str(bid) for bid in book_ids],
                "limit": limit,
            }
            if categories:
                params["categories"] = categories
        else:
            query = text(f"""
                WITH keyword_matches AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.chunk_index,
                        c.text,
                        ts_rank(c.text_search, phraseto_tsquery('simple', :phrase)) AS rank
                    FROM chunks c
                    WHERE c.text_search @@ phraseto_tsquery('simple', :phrase)
                )
                SELECT
                    km.book_id,
                    km.page_number,
                    km.chunk_index,
                    km.text,
                    b.title,
                    b.volume,
                    b.author,
                    km.rank
                FROM keyword_matches km
                JOIN books b ON km.book_id = b.id
                LEFT JOIN pages p ON km.book_id = p.book_id AND km.page_number = p.page_number
                WHERE (p.is_toc IS NOT TRUE OR p.id IS NULL)
                  {cat_filter}
                ORDER BY km.rank DESC
                LIMIT :limit
            """)
            params = {"phrase": phrase, "limit": limit}
            if categories:
                params["categories"] = categories

        # A common word in a broad OR tsquery (e.g. a grammatical particle
        # slipping through) can match a huge fraction of the table. Under the
        # default work_mem, that forces a lossy bitmap recheck (re-fetching
        # whole heap pages instead of exact tuples) plus a disk-spilled sort —
        # confirmed in production to take 40-60s. LOCAL scoping keeps this
        # bump to just this statement's transaction, not every connection.
        await self.session.execute(
            text(f"SET LOCAL work_mem = '{_KEYWORD_SEARCH_WORK_MEM}'")
        )
        # Backstop for whatever work_mem doesn't fix: caps the worst case so a
        # single pathological term can't cost a user 40+ seconds. A canceled
        # statement raises here; callers already treat a keyword-leg
        # exception as "fall back to vector-only for this call."
        await self.session.execute(
            text(
                f"SET LOCAL statement_timeout = '{_KEYWORD_SEARCH_STATEMENT_TIMEOUT_MS}'"
            )
        )
        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "book_id": str(row.book_id),
                "page_number": row.page_number,
                "page": row.page_number,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "title": row.title,
                "volume": row.volume,
                "author": row.author,
                "rank": float(row.rank),
            }
            for row in rows
        ]

    async def find_books_by_exact_phrase(
        self,
        phrase: str,
        skip: int = 0,
        limit: int = 40,
        restrict_to_public: bool = True,
    ) -> tuple[List[Book], int]:
        """Home 'Content' tab: exact-phrase search over chunk text, grouped by
        book, paginated (infinite scroll — see keyword-search-rework-plan.md
        Phase 3). This is a browse/discovery search over the whole library,
        not the chat-retrieval keyword leg (`keyword_search`), so it isn't
        capped by `rag_keyword_top_k` — the caller paginates instead.

        *restrict_to_public* mirrors the same guest-visibility rule used
        throughout `books_router.py` (status == "ready" and
        visibility public/legacy-NULL) — callers pass False only for
        admin/editor users who should see private/draft book content too.
        """
        exists_clause = text(
            """EXISTS (
                SELECT 1 FROM chunks c
                WHERE c.book_id = books.id
                  AND c.text_search @@ phraseto_tsquery('simple', :phrase)
            )"""
        ).bindparams(phrase=phrase)

        conditions = [exists_clause]
        if restrict_to_public:
            conditions.append(Book.status == "ready")
            conditions.append(
                or_(Book.visibility == "public", Book.visibility.is_(None))
            )
        else:
            conditions.append(Book.status != "error")

        count_stmt = select(func.count()).select_from(Book).where(*conditions)
        count_result = await self.session.execute(count_stmt)
        total = count_result.scalar_one()

        books_stmt = (
            select(Book)
            .where(*conditions)
            .order_by(Book.title.asc())
            .offset(skip)
            .limit(limit)
        )
        books_result = await self.session.execute(books_stmt)
        books = list(books_result.scalars().all())

        return books, total

    async def search_content_chunks(
        self,
        phrase: str,
        skip: int = 0,
        limit: int = 40,
        restrict_to_public: bool = True,
    ) -> tuple[List[dict], int]:
        """Home 'Content' tab: exact-phrase search over chunk text returning paginated
        chunk hits with text snippets, page numbers, book title, author, volume, and cover.
        """
        vis_clause = (
            "b.status = 'ready' AND (b.visibility = 'public' OR b.visibility IS NULL)"
            if restrict_to_public
            else "b.status != 'error'"
        )

        # Single-token terms (e.g. "ياش") can match thousands of chunks. Evaluating
        # ts_rank() for thousands of hits incurs huge CPU overhead with virtually
        # no ranking benefit. Skip ts_rank for single-word queries to allow Postgres
        # to satisfy the query using fast index scans.
        is_single_token = len(phrase.strip().split()) == 1
        rank_projection = (
            "0.0 AS rank"
            if is_single_token
            else "ts_rank(c.text_search, phraseto_tsquery('simple', :phrase)) AS rank"
        )
        order_clause = (
            "ORDER BY b.title ASC, c.page_number ASC, c.chunk_index ASC"
            if is_single_token
            else "ORDER BY rank DESC, b.title ASC, c.page_number ASC"
        )

        count_query = text(f"""
            SELECT COUNT(*)
            FROM chunks c
            JOIN books b ON c.book_id = b.id
            LEFT JOIN pages p ON c.book_id = p.book_id AND c.page_number = p.page_number
            WHERE c.text_search @@ phraseto_tsquery('simple', :phrase)
              AND (p.is_toc IS NOT TRUE OR p.id IS NULL)
              AND {vis_clause}
        """)

        hits_query = text(f"""
            SELECT
                c.book_id,
                c.page_number,
                c.chunk_index,
                c.text,
                b.title,
                b.volume,
                b.author,
                b.cover_url,
                {rank_projection}
            FROM chunks c
            JOIN books b ON c.book_id = b.id
            LEFT JOIN pages p ON c.book_id = p.book_id AND c.page_number = p.page_number
            WHERE c.text_search @@ phraseto_tsquery('simple', :phrase)
              AND (p.is_toc IS NOT TRUE OR p.id IS NULL)
              AND {vis_clause}
            {order_clause}
            OFFSET :skip LIMIT :limit
        """)

        params = {"phrase": phrase, "skip": skip, "limit": limit}

        try:
            await self.session.execute(
                text(f"SET LOCAL work_mem = '{_KEYWORD_SEARCH_WORK_MEM}'")
            )
            await self.session.execute(
                text(
                    f"SET LOCAL statement_timeout = '{_KEYWORD_SEARCH_STATEMENT_TIMEOUT_MS}'"
                )
            )

            count_res = await self.session.execute(count_query, {"phrase": phrase})
            total = count_res.scalar_one()

            hits_res = await self.session.execute(hits_query, params)
            rows = hits_res.fetchall()
        except Exception as e:
            logger.warning(
                "Content search query timed out or failed for phrase '%s': %s",
                phrase,
                e,
            )
            return [], 0

        hits = [
            {
                "id": f"{row.book_id}_{row.page_number}_{row.chunk_index}",
                "book_id": str(row.book_id),
                "book_title": row.title,
                "book_author": row.author,
                "book_volume": row.volume,
                "book_cover_url": row.cover_url,
                "page_number": row.page_number,
                "page": row.page_number,
                "snippet": row.text,
                "rank": float(row.rank),
            }
            for row in rows
        ]

        return hits, total


def get_chunks_repository(session: AsyncSession) -> ChunksRepository:
    """Factory function for dependency injection"""
    return ChunksRepository(session)
