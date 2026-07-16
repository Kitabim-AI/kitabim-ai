"""Chunks repository with pgvector similarity search"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Chunk
from app.db.repositories.base_repository import BaseRepository


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


def get_chunks_repository(session: AsyncSession) -> ChunksRepository:
    """Factory function for dependency injection"""
    return ChunksRepository(session)
