"""Pages repository with upsert operations"""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, delete, func, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Page, Book
from app.db.repositories.base_repository import BaseRepository

from app.db.repositories.system_configs_repository import SystemConfigsRepository

logger = logging.getLogger(__name__)

_KEYWORD_SEARCH_WORK_MEM = "64MB"
_KEYWORD_SEARCH_STATEMENT_TIMEOUT_MS = "15000ms"


class PagesRepository(BaseRepository[Page]):
    """Repository for pages with upsert operations"""

    def __init__(self, session: AsyncSession):
        super().__init__(session, Page)

    async def search_content_pages(
        self,
        phrase: str,
        skip: int = 0,
        limit: int = 40,
        restrict_to_public: bool = True,
    ) -> tuple[List[dict], int]:
        """Home 'Content' tab: exact-phrase search over page text returning paginated
        page hits with contextual page text snippets, page numbers, book title, author, volume, and cover.
        """
        vis_clause = (
            "b.status = 'ready' AND (b.visibility = 'public' OR b.visibility IS NULL)"
            if restrict_to_public
            else "b.status != 'error'"
        )

        is_single_token = len(phrase.strip().split()) == 1
        rank_projection = (
            "0.0 AS rank"
            if is_single_token
            else "ts_rank(p.text_search, phraseto_tsquery('simple', :phrase)) AS rank"
        )
        order_clause = (
            "ORDER BY b.title ASC, p.page_number ASC"
            if is_single_token
            else "ORDER BY rank DESC, b.title ASC, p.page_number ASC"
        )

        max_snippet_len = 500
        try:
            config_repo = SystemConfigsRepository(self.session)
            val = await config_repo.get_value(
                "sys_content_search_snippet_max_chars", default="500"
            )
            if val is not None:
                max_snippet_len = int(val)
        except Exception as e:
            logger.warning(
                "Failed to load content_search_snippet_max_chars config: %s", e
            )
            max_snippet_len = 500

        count_query = text(f"""
            SELECT COUNT(*)
            FROM pages p
            JOIN books b ON p.book_id = b.id
            WHERE p.text_search @@ phraseto_tsquery('simple', :phrase)
              AND (p.is_toc IS NOT TRUE OR p.id IS NULL)
              AND {vis_clause}
        """)

        hits_query = text(f"""
            SELECT
                p.book_id,
                p.page_number,
                ts_headline('simple', p.text, phraseto_tsquery('simple', :phrase),
                    'MaxWords=75, MinWords=35, ShortWord=2, StartSel="", StopSel=""') AS snippet,
                p.text AS full_text,
                b.title,
                b.volume,
                b.author,
                b.cover_url,
                {rank_projection}
            FROM pages p
            JOIN books b ON p.book_id = b.id
            WHERE p.text_search @@ phraseto_tsquery('simple', :phrase)
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
                "Pages content search query timed out or failed for phrase '%s': %s",
                phrase,
                e,
            )
            return [], 0

        hits = []
        for row in rows:
            raw_text = row.snippet or row.full_text or ""
            if max_snippet_len and len(raw_text) > max_snippet_len:
                cut = raw_text[:max_snippet_len]
                if " " in cut:
                    cut = cut.rsplit(" ", 1)[0]
                snippet = cut + "..."
            else:
                snippet = raw_text

            hits.append(
                {
                    "id": f"{row.book_id}_{row.page_number}",
                    "book_id": str(row.book_id),
                    "book_title": row.title,
                    "book_author": row.author,
                    "book_volume": row.volume,
                    "book_cover_url": row.cover_url,
                    "page_number": row.page_number,
                    "page": row.page_number,
                    "snippet": snippet,
                    "rank": float(row.rank),
                }
            )

        return hits, total

    async def find_by_book(
        self, book_id: str, skip: int = 0, limit: int = 10000
    ) -> List[Page]:
        """Find all pages for a book, ordered by page number"""
        stmt = (
            select(Page)
            .where(Page.book_id == book_id)
            .order_by(Page.page_number)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_first_pages_with_text(
        self, book_id: str, limit: int = 5
    ) -> List[Page]:
        """Find the first pages of a book that contain non-empty text content."""
        stmt = (
            select(Page)
            .where(
                Page.book_id == book_id,
                Page.text.is_not(None),
                Page.text != "",
                func.length(func.trim(Page.text)) > 10,
            )
            .order_by(Page.page_number)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_one(self, book_id: str, page_number: int) -> Optional[Page]:
        """Find a specific page by book ID and page number"""
        stmt = select(Page).where(
            Page.book_id == book_id, Page.page_number == page_number
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(self, page_data: dict) -> Page:
        """
        Upsert a page using PostgreSQL INSERT ... ON CONFLICT.

        Replaces the manual SQL with SQLAlchemy's insert().on_conflict_do_update().
        This is critical for OCR processing where pages may be reprocessed.
        """
        stmt = insert(Page).values(**page_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=["book_id", "page_number"],
            set_={
                "text": stmt.excluded.text,
                "status": stmt.excluded.status,
                "error": stmt.excluded.error,
                "updated_by": stmt.excluded.updated_by,
                "last_updated": func.now(),
            },
        )
        stmt = stmt.returning(Page)

        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one()

    async def update_status(
        self, book_id: str, page_number: int, status: str, error: Optional[str] = None
    ) -> Optional[Page]:
        """Update page status and optional error message"""
        from sqlalchemy import update

        values = {"status": status, "last_updated": func.now()}
        if error is not None:
            values["error"] = error

        stmt = (
            update(Page)
            .where(Page.book_id == book_id, Page.page_number == page_number)
            .values(**values)
            .returning(Page)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def update_many_status(
        self, book_id: str, page_numbers: List[int], status: str
    ) -> int:
        """Update status for multiple pages"""
        from sqlalchemy import update

        stmt = (
            update(Page)
            .where(Page.book_id == book_id, Page.page_number.in_(page_numbers))
            .values(status=status, last_updated=func.now())
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def set_is_toc(
        self, book_id: str, page_number: int, is_toc: bool, updated_by: str
    ) -> bool:
        """Manually mark or unmark a page as a Table of Contents page"""
        from sqlalchemy import update

        stmt = (
            update(Page)
            .where(Page.book_id == book_id, Page.page_number == page_number)
            .values(is_toc=is_toc, last_updated=func.now(), updated_by=updated_by)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def sync_content_page_offset(self, book_id: str) -> int:
        """Calculate and update book.content_page_offset based on MAX(page_number) where is_toc IS TRUE."""
        from sqlalchemy import update

        stmt = select(func.coalesce(func.max(Page.page_number), 0)).where(
            Page.book_id == book_id, Page.is_toc.is_(True)
        )
        res = await self.session.execute(stmt)
        max_toc_page = res.scalar_one() or 0

        update_stmt = (
            update(Book)
            .where(Book.id == book_id)
            .values(content_page_offset=max_toc_page)
        )
        await self.session.execute(update_stmt)
        await self.session.flush()
        return max_toc_page

    async def delete_by_book(self, book_id: str) -> int:
        """Delete all pages for a book"""
        stmt = delete(Page).where(Page.book_id == book_id)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def count_by_book(self, book_id: str, status: Optional[str] = None) -> int:
        """Count pages for a book, optionally filtered by status"""
        stmt = select(func.count()).select_from(Page).where(Page.book_id == book_id)

        if status:
            stmt = stmt.where(Page.status == status)

        result = await self.session.execute(stmt)
        return result.scalar_one()


def get_pages_repository(session: AsyncSession) -> PagesRepository:
    """Factory function for dependency injection"""
    return PagesRepository(session)
