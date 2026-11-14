"""Chunks repository with pgvector similarity search"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Chunk
from app.db.repositories.base_repository import BaseRepository

logger = logging.getLogger("app.db.repositories.chunks_repository")

# Tuned against a production case where a common word matched ~194K rows and
# took 40-60s: work_mem avoids the disk-bound fallback strategies, the
# timeout bounds whatever it doesn't fix. See keyword_search() below.
_KEYWORD_SEARCH_WORK_MEM = "128MB"
_KEYWORD_SEARCH_STATEMENT_TIMEOUT_MS = "5000"

# HNSW returns at most hnsw.ef_search rows (pgvector default 40). The unscoped
# similarity search filters TOC pages, the score threshold and character
# categories *after* the index scan, so over-fetch generously and raise
# ef_search to match. pgvector caps ef_search at 1000.
_VECTOR_OVERFETCH_FACTOR = 8
_HNSW_EF_SEARCH_MAX = 1000


def _opt_int(val: object) -> Optional[int]:
    return int(val) if isinstance(val, int) and not isinstance(val, bool) else None


def _opt_str(val: object) -> Optional[str]:
    return val if isinstance(val, str) else None


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
                "end_page_number": stmt.excluded.end_page_number,
                "section_id": stmt.excluded.section_id,
                "text_hash": stmt.excluded.text_hash,
                "embedding": stmt.excluded.embedding,
            },
        )

        await self.session.execute(stmt)
        await self.session.flush()

    async def get_embedding_hash_map(self, book_id: str) -> dict[str, List[float]]:
        """Return `{text_hash: embedding}` for existing embedded chunks of `book_id`."""
        stmt = select(Chunk.text_hash, Chunk.embedding).where(
            Chunk.book_id == book_id,
            Chunk.text_hash.is_not(None),
            Chunk.embedding.is_not(None),
        )
        res = await self.session.execute(stmt)
        hash_map: dict[str, List[float]] = {}
        for row in res.fetchall():
            th = row[0]
            emb = row[1]
            if th and emb is not None:
                hash_map[str(th)] = list(emb)
        return hash_map

    async def replace_for_book(
        self,
        book_id: str,
        chunks: List[dict],
        embedding_hash_map: Optional[dict[str, List[float]]] = None,
    ) -> int:
        """Atomically replace all chunks for `book_id` in batches, carrying over
        existing embeddings by `text_hash` inside PostgreSQL and returning the
        number of remaining unembedded chunks (`embedding IS NULL`).
        """
        use_sql_carryover = embedding_hash_map is None and bool(chunks)
        if use_sql_carryover:
            await self.session.execute(
                text(
                    """
                    CREATE TEMP TABLE IF NOT EXISTS _tmp_book_chunk_embeddings (
                        text_hash VARCHAR(64) PRIMARY KEY,
                        embedding vector(3072)
                    ) ON COMMIT DROP
                    """
                )
            )
            await self.session.execute(text("TRUNCATE _tmp_book_chunk_embeddings"))
            await self.session.execute(
                text(
                    """
                    INSERT INTO _tmp_book_chunk_embeddings (text_hash, embedding)
                    SELECT DISTINCT ON (text_hash) text_hash, embedding
                    FROM chunks
                    WHERE book_id = :book_id
                      AND text_hash IS NOT NULL
                      AND embedding IS NOT NULL
                    ON CONFLICT (text_hash) DO NOTHING
                    """
                ),
                {"book_id": book_id},
            )

        await self.delete_by_book(book_id)
        if not chunks:
            return 0

        normalized_chunks: List[dict] = []
        for raw in chunks:
            item = dict(raw)
            item.setdefault("book_id", book_id)
            if embedding_hash_map is not None and item.get("embedding") is None:
                th = item.get("text_hash")
                if th and th in embedding_hash_map:
                    item["embedding"] = embedding_hash_map[th]
            else:
                item.setdefault("embedding", None)
            normalized_chunks.append(item)

        batch_size = 250
        for idx in range(0, len(normalized_chunks), batch_size):
            await self.upsert_many(normalized_chunks[idx : idx + batch_size])

        if use_sql_carryover:
            await self.session.execute(
                text(
                    """
                    UPDATE chunks AS c
                    SET embedding = old.embedding
                    FROM _tmp_book_chunk_embeddings AS old
                    WHERE c.book_id = :book_id
                      AND c.embedding IS NULL
                      AND c.text_hash IS NOT NULL
                      AND c.text_hash = old.text_hash
                    """
                ),
                {"book_id": book_id},
            )
            count_res = await self.session.execute(
                text(
                    """
                    SELECT count(*)
                    FROM chunks
                    WHERE book_id = :book_id
                      AND embedding IS NULL
                    """
                ),
                {"book_id": book_id},
            )
            scalar_count = count_res.scalar() if count_res is not None else None
            if isinstance(scalar_count, int) and not isinstance(scalar_count, bool):
                return int(scalar_count)

        return sum(1 for c in normalized_chunks if c.get("embedding") is None)

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
        section_ids: Optional[List[int]] = None,
    ) -> List[dict]:
        """
        Vector similarity search using pgvector cosine distance.

        Uses <=> operator for cosine distance: 1 - cosine_distance = similarity score
        Returns chunks with similarity > threshold, ordered by similarity DESC.

        NOTE: This uses raw SQL for optimal pgvector performance.
        SQLAlchemy 2.0 doesn't have native pgvector operators yet.
        """
        if section_ids is not None and not section_ids:
            return []

        embedding_str = str(query_embedding)

        cat_filter = (
            "AND b.categories && CAST(:categories AS text[])" if categories else ""
        )
        sec_filter = "AND c.section_id = ANY(:section_ids)" if section_ids else ""

        # Over-fetch to compensate for TOC/threshold/category rows filtered out
        # in the outer query (see _VECTOR_OVERFETCH_FACTOR).
        inner_limit = min(int(limit) * _VECTOR_OVERFETCH_FACTOR, _HNSW_EF_SEARCH_MAX)

        if book_ids is not None:
            if not book_ids:
                return []
            query = text(f"""
                WITH filtered_chunks AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.end_page_number,
                        c.section_id,
                        c.chunk_index,
                        c.text,
                        c.embedding
                    FROM chunks c
                    WHERE c.book_id = ANY(:book_ids)
                      AND c.embedding IS NOT NULL
                      {sec_filter}
                ),
                ranked_matches AS (
                    SELECT
                        fc.book_id,
                        fc.page_number,
                        fc.end_page_number,
                        fc.section_id,
                        fc.chunk_index,
                        fc.text,
                        1 - (fc.embedding <=> CAST(:embedding AS vector(3072))) AS similarity
                    FROM filtered_chunks fc
                )
                SELECT
                    rm.book_id,
                    rm.page_number,
                    COALESCE(rm.end_page_number, rm.page_number) AS end_page_number,
                    rm.section_id,
                    CASE
                        WHEN parent_bs.title IS NOT NULL AND bs.title IS NOT NULL AND parent_bs.title <> bs.title
                            THEN parent_bs.title || ' › ' || bs.title
                        ELSE bs.title
                    END AS section_title,
                    rm.chunk_index,
                    rm.text,
                    b.title,
                    b.volume,
                    b.author,
                    p.content_page_number,
                    p_end.content_page_number AS end_content_page_number,
                    rm.similarity
                FROM ranked_matches rm
                JOIN books b ON rm.book_id = b.id
                LEFT JOIN pages p ON rm.book_id = p.book_id AND rm.page_number = p.page_number
                LEFT JOIN pages p_end
                    ON rm.book_id = p_end.book_id
                   AND COALESCE(rm.end_page_number, rm.page_number) = p_end.page_number
                LEFT JOIN book_sections bs ON rm.section_id = bs.id
                LEFT JOIN book_sections parent_bs ON bs.parent_id = parent_bs.id
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
            if section_ids:
                params["section_ids"] = [int(sid) for sid in section_ids]
        else:
            query = text(f"""
                WITH vector_matches AS (
                    SELECT
                        c.book_id,
                        c.page_number,
                        c.end_page_number,
                        c.section_id,
                        c.chunk_index,
                        c.text,
                        1 - (c.embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
                    FROM chunks c
                    WHERE c.embedding IS NOT NULL
                      {sec_filter}
                    ORDER BY c.embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))
                    LIMIT :inner_limit
                )
                SELECT
                    vm.book_id,
                    vm.page_number,
                    COALESCE(vm.end_page_number, vm.page_number) AS end_page_number,
                    vm.section_id,
                    CASE
                        WHEN parent_bs.title IS NOT NULL AND bs.title IS NOT NULL AND parent_bs.title <> bs.title
                            THEN parent_bs.title || ' › ' || bs.title
                        ELSE bs.title
                    END AS section_title,
                    vm.chunk_index,
                    vm.text,
                    b.title,
                    b.volume,
                    b.author,
                    p.content_page_number,
                    p_end.content_page_number AS end_content_page_number,
                    vm.similarity
                FROM vector_matches vm
                JOIN books b ON vm.book_id = b.id
                LEFT JOIN pages p ON vm.book_id = p.book_id AND vm.page_number = p.page_number
                LEFT JOIN pages p_end
                    ON vm.book_id = p_end.book_id
                   AND COALESCE(vm.end_page_number, vm.page_number) = p_end.page_number
                LEFT JOIN book_sections bs ON vm.section_id = bs.id
                LEFT JOIN book_sections parent_bs ON bs.parent_id = parent_bs.id
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
            if section_ids:
                params["section_ids"] = [int(sid) for sid in section_ids]

        if book_ids is None:
            # Int-validated, never user input — SET does not accept bind params.
            # SET LOCAL scopes it to this transaction only.
            await self.session.execute(
                text(f"SET LOCAL hnsw.ef_search = {int(inner_limit)}")
            )

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "book_id": str(row.book_id),
                "page_number": row.page_number,
                "end_page_number": _opt_int(getattr(row, "end_page_number", None))
                or row.page_number,
                "section_id": _opt_int(getattr(row, "section_id", None)),
                "section_title": _opt_str(getattr(row, "section_title", None)),
                "content_page_number": _opt_str(
                    getattr(row, "content_page_number", None)
                ),
                "end_content_page_number": _opt_str(
                    getattr(row, "end_content_page_number", None)
                )
                or _opt_str(getattr(row, "content_page_number", None)),
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
        and_phrases: Optional[List[str]] = None,
        section_ids: Optional[List[int]] = None,
    ) -> List[dict]:
        """
        Postgres full-text EXACT PHRASE search over `pages.text_search`
        (a generated tsvector column, migration 076).
        """
        if section_ids is not None and not section_ids:
            return []

        cat_filter = (
            "WHERE b.categories && CAST(:categories AS text[])" if categories else ""
        )
        sec_exists_filter = (
            """AND EXISTS (
                SELECT 1
                FROM chunks c2
                WHERE c2.book_id = p.book_id
                  AND c2.section_id = ANY(:section_ids)
                  AND p.page_number BETWEEN c2.page_number AND COALESCE(c2.end_page_number, c2.page_number)
            )"""
            if section_ids
            else ""
        )
        extra = list(and_phrases or [])
        tsquery_expr = "phraseto_tsquery('simple', :phrase)" + "".join(
            f" && phraseto_tsquery('simple', :and_phrase_{i})"
            for i in range(len(extra))
        )
        extra_params = {f"and_phrase_{i}": p for i, p in enumerate(extra)}

        if book_ids is not None:
            if not book_ids:
                return []
            query = text(f"""
                WITH keyword_matches AS (
                    SELECT
                        p.book_id,
                        p.page_number,
                        p.content_page_number,
                        p.text,
                        ts_rank(p.text_search, ({tsquery_expr})) AS rank
                    FROM pages p
                    WHERE p.book_id = ANY(:book_ids)
                      AND p.text_search @@ ({tsquery_expr})
                      AND p.is_toc IS NOT TRUE
                      {sec_exists_filter}
                )
                SELECT
                    km.book_id,
                    km.page_number,
                    km.content_page_number,
                    km.text,
                    b.title,
                    b.volume,
                    b.author,
                    sec.section_id,
                    sec.section_title,
                    km.rank
                FROM keyword_matches km
                JOIN books b ON km.book_id = b.id
                LEFT JOIN LATERAL (
                    SELECT
                        bs.id AS section_id,
                        CASE
                            WHEN parent_bs.title IS NOT NULL AND bs.title IS NOT NULL AND parent_bs.title <> bs.title
                                THEN parent_bs.title || ' › ' || bs.title
                            ELSE bs.title
                        END AS section_title
                    FROM book_sections bs
                    LEFT JOIN book_sections parent_bs ON parent_bs.id = bs.parent_id
                    WHERE bs.book_id = km.book_id
                      AND km.page_number BETWEEN bs.start_page AND bs.end_page
                    ORDER BY bs.level DESC, bs.section_index ASC
                    LIMIT 1
                ) sec ON true
                {cat_filter}
                ORDER BY km.rank DESC
                LIMIT :limit
            """)
            params = {
                "phrase": phrase,
                "book_ids": [str(bid) for bid in book_ids],
                "limit": limit,
                **extra_params,
            }
            if categories:
                params["categories"] = categories
            if section_ids:
                params["section_ids"] = [int(sid) for sid in section_ids]
        else:
            query = text(f"""
                WITH keyword_matches AS (
                    SELECT
                        p.book_id,
                        p.page_number,
                        p.content_page_number,
                        p.text,
                        ts_rank(p.text_search, ({tsquery_expr})) AS rank
                    FROM pages p
                    WHERE p.text_search @@ ({tsquery_expr})
                      AND p.is_toc IS NOT TRUE
                      {sec_exists_filter}
                )
                SELECT
                    km.book_id,
                    km.page_number,
                    km.content_page_number,
                    km.text,
                    b.title,
                    b.volume,
                    b.author,
                    sec.section_id,
                    sec.section_title,
                    km.rank
                FROM keyword_matches km
                JOIN books b ON km.book_id = b.id
                LEFT JOIN LATERAL (
                    SELECT
                        bs.id AS section_id,
                        CASE
                            WHEN parent_bs.title IS NOT NULL AND bs.title IS NOT NULL AND parent_bs.title <> bs.title
                                THEN parent_bs.title || ' › ' || bs.title
                            ELSE bs.title
                        END AS section_title
                    FROM book_sections bs
                    LEFT JOIN book_sections parent_bs ON parent_bs.id = bs.parent_id
                    WHERE bs.book_id = km.book_id
                      AND km.page_number BETWEEN bs.start_page AND bs.end_page
                    ORDER BY bs.level DESC, bs.section_index ASC
                    LIMIT 1
                ) sec ON true
                {cat_filter}
                ORDER BY km.rank DESC
                LIMIT :limit
            """)
            params = {"phrase": phrase, "limit": limit, **extra_params}
            if categories:
                params["categories"] = categories
            if section_ids:
                params["section_ids"] = [int(sid) for sid in section_ids]

        await self.session.execute(
            text(f"SET LOCAL work_mem = '{_KEYWORD_SEARCH_WORK_MEM}'")
        )
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
                "end_page_number": row.page_number,
                "page": row.page_number,
                "section_id": _opt_int(getattr(row, "section_id", None)),
                "section_title": _opt_str(getattr(row, "section_title", None)),
                "content_page_number": _opt_str(
                    getattr(row, "content_page_number", None)
                ),
                "end_content_page_number": _opt_str(
                    getattr(row, "content_page_number", None)
                ),
                "text": row.text,
                "title": row.title,
                "volume": row.volume,
                "author": row.author,
                "rank": float(row.rank),
            }
            for row in rows
        ]


def get_chunks_repository(session: AsyncSession) -> ChunksRepository:
    """Factory function for dependency injection"""
    return ChunksRepository(session)
