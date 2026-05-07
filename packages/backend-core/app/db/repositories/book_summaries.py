"""Book summaries repository — vector search over per-book semantic summaries."""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import func, select, update
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
        threshold: float = 0.30,
    ) -> List[str]:
        """
        Return book_ids whose summaries are most similar to query_embedding.

        Uses pgvector cosine distance (<=>). Returns ALL books above threshold
        (no row limit — the threshold is the only filter). Results are ordered
        by similarity DESC.
        """
        from sqlalchemy import text

        embedding_str = str(query_embedding)
        if book_ids is not None:
            if not book_ids:
                return []
            query = text("""
                SELECT
                    book_id,
                    1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
                FROM book_summaries
                WHERE book_id = ANY(:book_ids)
                  AND 1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) > :threshold
                ORDER BY similarity DESC
            """)
            params = {"embedding": embedding_str, "threshold": threshold, "book_ids": book_ids}
        else:
            query = text("""
                SELECT
                    book_id,
                    1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) AS similarity
                FROM book_summaries
                WHERE 1 - (embedding::halfvec(3072) <=> CAST(:embedding AS halfvec(3072))) > :threshold
                ORDER BY similarity DESC
            """)
            params = {"embedding": embedding_str, "threshold": threshold}

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

    async def upsert_draft(self, book_id: str, summary: str, embedding: List[float]) -> None:
        """Write regenerated summary + embedding to staging columns during migration 039→040.

        Updates summary and embedding_draft only — the active 'embedding' column is
        intentionally left unchanged so search keeps using old stable embeddings until
        cutover migration 040 swaps them in bulk.

        Remove this method and revert summary_job to upsert() after migration 040.
        """
        await self.session.execute(
            update(BookSummary)
            .where(BookSummary.book_id == book_id)
            .values(summary=summary, embedding_draft=embedding, generated_at=func.now())
        )
        await self.session.flush()

    async def get_summaries_for_books(
        self,
        book_ids: List[str],
        text_filter: Optional[List[str]] = None,
    ) -> List[dict]:
        """Return summary text + book metadata for the given book_ids.

        If text_filter is given, only summaries that contain at least one of
        those terms (case-insensitive) are returned.
        """
        from app.db.models import Book
        from sqlalchemy import or_

        stmt = (
            select(BookSummary.book_id, BookSummary.summary, Book.title, Book.volume, Book.author)
            .join(Book, Book.id == BookSummary.book_id)
            .where(BookSummary.book_id.in_(book_ids))
            .where(BookSummary.summary.isnot(None))
        )
        if text_filter:
            stmt = stmt.where(
                or_(*[BookSummary.summary.ilike(f"%{term}%") for term in text_filter])
            )
        result = await self.session.execute(stmt)
        return [
            {
                "book_id": str(row.book_id),
                "summary": row.summary,
                "title": row.title,
                "volume": row.volume,
                "author": row.author,
            }
            for row in result.fetchall()
        ]

    async def get_by_book_id(self, book_id: str) -> Optional[BookSummary]:
        result = await self.session.execute(
            select(BookSummary).where(BookSummary.book_id == book_id)
        )
        return result.scalar_one_or_none()
