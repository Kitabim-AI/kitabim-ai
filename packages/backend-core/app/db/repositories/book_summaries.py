"""Book summaries repository — vector search over per-book semantic summaries."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BookSummary
from app.db.repositories.base import BaseRepository


class BookSummariesRepository(BaseRepository[BookSummary]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, BookSummary)

    async def summary_search(
        self,
        query_embedding: List[float],
        book_ids: Optional[List[str]] = None,
        limit: int = 5,
        threshold: float = 0.30,
    ) -> List[str]:
        """
        Return book_ids whose summaries are most similar to query_embedding.

        Uses pgvector cosine distance (<=>). Only returns books above threshold.
        Results are ordered by similarity DESC.
        """
        from sqlalchemy import text

        embedding_str = str(query_embedding)
        if book_ids:
            query = text("""
                SELECT
                    book_id,
                    1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM book_summaries
                WHERE book_id = ANY(:book_ids)
                  AND 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {"embedding": embedding_str, "threshold": threshold, "limit": limit, "book_ids": book_ids}
        else:
            query = text("""
                SELECT
                    book_id,
                    1 - (embedding <=> CAST(:embedding AS vector)) AS similarity
                FROM book_summaries
                WHERE 1 - (embedding <=> CAST(:embedding AS vector)) > :threshold
                ORDER BY similarity DESC
                LIMIT :limit
            """)
            params = {"embedding": embedding_str, "threshold": threshold, "limit": limit}

        result = await self.session.execute(query, params)
        return [str(row.book_id) for row in result.fetchall()]

    async def upsert(self, book_id: str, summary: str, embedding: List[float]) -> None:
        """Insert or replace the summary for a book."""
        stmt = insert(BookSummary).values(
            book_id=book_id,
            summary=summary,
            embedding=embedding,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["book_id"],
            set_={
                "summary": stmt.excluded.summary,
                "embedding": stmt.excluded.embedding,
                "generated_at": stmt.excluded.generated_at,
            },
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def get_by_book_id(self, book_id: str) -> Optional[BookSummary]:
        result = await self.session.execute(
            select(BookSummary).where(BookSummary.book_id == book_id)
        )
        return result.scalar_one_or_none()
