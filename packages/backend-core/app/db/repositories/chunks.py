"""Chunks repository with pgvector similarity search"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select, delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Chunk
from app.db.repositories.base import BaseRepository


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
            }
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
            Chunk.book_id == book_id,
            Chunk.page_number == page_number
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
        limit: int = 12,
        threshold: float = 0.35
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
            limit: Maximum number of results
            threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of dicts with book_id, page_number, text, and similarity score
        """
        # Build query with or without book_ids filter
        if book_ids:
            query = text("""
                SELECT
                    book_id,
                    page_number,
                    chunk_index,
                    text,
                    1 - (embedding <=> :embedding::vector) AS similarity
                FROM chunks
                WHERE book_id = ANY(:book_ids)
                  AND embedding IS NOT NULL
                  AND 1 - (embedding <=> :embedding::vector) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {
                "embedding": str(query_embedding),
                "book_ids": [str(bid) for bid in book_ids],
                "threshold": threshold,
                "limit": limit
            }
        else:
            query = text("""
                SELECT
                    book_id,
                    page_number,
                    chunk_index,
                    text,
                    1 - (embedding <=> :embedding::vector) AS similarity
                FROM chunks
                WHERE embedding IS NOT NULL
                  AND 1 - (embedding <=> :embedding::vector) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {
                "embedding": str(query_embedding),
                "threshold": threshold,
                "limit": limit
            }

        result = await self.session.execute(query, params)
        rows = result.fetchall()

        return [
            {
                "book_id": str(row.book_id),
                "page_number": row.page_number,
                "chunk_index": row.chunk_index,
                "text": row.text,
                "similarity": float(row.similarity),
            }
            for row in rows
        ]


def get_chunks_repository(session: AsyncSession) -> ChunksRepository:
    """Factory function for dependency injection"""
    return ChunksRepository(session)
