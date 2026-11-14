"""Pages repository with upsert operations"""

from __future__ import annotations

import logging
import re
from typing import List, Optional

from sqlalchemy import select, delete, func, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import Page, Book
from app.core.pipeline import (
    PAGE_MILESTONE_IDLE,
    PAGE_MILESTONE_SUCCEEDED,
)
from app.db.repositories.base_repository import BaseRepository

# Characters with meaning in to_tsquery syntax, plus quote/punctuation marks
# that can wrap a title. Stripped before building a prefix query.
_TSQUERY_UNSAFE = re.compile(r"[&|!():*<>'\\\"«»،؟.,;\-\[\]{}\s]")
# Bounds the per-word book count used by the one-word title filter; the
# caller treats a timeout as "common word".
_WORD_BOOK_COUNT_TIMEOUT_MS = 2000

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

    async def count_books_with_text(self) -> int:
        """Number of distinct books that have at least one page with text."""
        result = await self.session.execute(
            text(
                "SELECT count(DISTINCT book_id) FROM pages "
                "WHERE text IS NOT NULL AND text <> ''"
            )
        )
        return int(result.scalar_one() or 0)

    async def count_books_mentioning(self, word: str) -> int:
        """Number of distinct books whose pages contain *word* or a suffixed
        form of it (prefix match on pages.text_search, 'simple' config).

        Raises ValueError when nothing usable remains after stripping tsquery
        syntax, and lets a statement timeout propagate — callers treat both as
        "common word". Runs SET LOCAL, so call it on a dedicated session.
        """
        token = _TSQUERY_UNSAFE.sub("", word or "")
        if not token:
            raise ValueError("no searchable token in word")
        await self.session.execute(
            text(f"SET LOCAL statement_timeout = '{_WORD_BOOK_COUNT_TIMEOUT_MS}'")
        )
        result = await self.session.execute(
            text(
                "SELECT count(DISTINCT book_id) FROM pages "
                "WHERE text_search @@ to_tsquery('simple', :q)"
            ),
            {"q": f"{token}:*"},
        )
        return int(result.scalar_one() or 0)

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

    async def find_toc_pages(self, book_id: str) -> List[Page]:
        """Find a book's table-of-contents pages (``is_toc``), ordered by
        page number. A ToC can span multiple pages (e.g. a long anthology),
        so this returns all of them, not just the first."""
        stmt = (
            select(Page)
            .where(Page.book_id == book_id, Page.is_toc.is_(True))
            .order_by(Page.page_number)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def search_toc_pages_by_phrase(
        self,
        phrase: str,
        book_ids: Optional[List[str]] = None,
        limit: int = 10,
    ) -> List[dict]:
        """Full-text search over `pages.text_search` restricted to
        table-of-contents pages (`is_toc IS TRUE`) -- the inverse filter of
        `ChunksRepository.keyword_search`/`search_content_pages`, which both
        exclude ToC pages as non-content. Used to locate which book(s)'
        ToC lists a named short work when the calling book isn't already
        known (global chat with no reader-mode book_id).
        """
        if book_ids is not None and not book_ids:
            return []

        book_filter = "AND p.book_id = ANY(:book_ids)" if book_ids else ""
        query = text(f"""
            SELECT p.book_id, p.page_number, p.text,
                   ts_rank(p.text_search, phraseto_tsquery('simple', :phrase)) AS rank
            FROM pages p
            WHERE p.text_search @@ phraseto_tsquery('simple', :phrase)
              AND p.is_toc IS TRUE
              {book_filter}
            ORDER BY rank DESC
            LIMIT :limit
        """)
        params: dict = {"phrase": phrase, "limit": limit}
        if book_ids:
            params["book_ids"] = [str(bid) for bid in book_ids]

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
                "text": row.text,
                "rank": float(row.rank),
            }
            for row in rows
        ]

    async def find_range(
        self, book_id: str, start_page: int, end_page: int
    ) -> List[Page]:
        """Find all pages for a book within [start_page, end_page] inclusive,
        ordered by page number. Used to fetch a short work's full content
        once its page range has been resolved from the ToC."""
        stmt = (
            select(Page)
            .where(
                Page.book_id == book_id,
                Page.page_number >= start_page,
                Page.page_number <= end_page,
            )
            .order_by(Page.page_number)
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

    async def get_pages_by_ids(self, page_ids: List[int]) -> List[Page]:
        """Fetch pages by their primary key IDs ordered by page number."""
        if not page_ids:
            return []
        stmt = select(Page).where(Page.id.in_(page_ids)).order_by(Page.page_number)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_pages_by_book_id(self, book_id: str) -> List[Page]:
        """Fetch all pages for a book ordered by page number."""
        stmt = select(Page).where(Page.book_id == book_id).order_by(Page.page_number)
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def get_content_page_map(self, book_id: str) -> dict[str, int]:
        """Return `{content_page_number: MIN(page_number)}` across non-ToC pages of `book_id`."""
        stmt = (
            select(
                Page.content_page_number,
                func.min(Page.page_number).label("min_page"),
            )
            .where(
                Page.book_id == book_id,
                Page.content_page_number.is_not(None),
                Page.content_page_number != "",
                Page.is_toc.is_not(True),
            )
            .group_by(Page.content_page_number)
        )
        res = await self.session.execute(stmt)
        return {
            str(row.content_page_number): int(row.min_page)
            for row in res.fetchall()
            if row.content_page_number is not None and row.min_page is not None
        }

    async def bulk_replace_pages(
        self,
        book_id: str,
        pages_payload: List[dict],
        *,
        reset_spell_check: bool = True,
        force_overwrite_manual: bool = False,
        existing_pages: Optional[List[Page]] = None,
    ) -> tuple[int, int]:
        """Batch-upsert non-skipped OCR backfill pages for `book_id`.

        Preserves manually edited pages (`updated_by IS NOT NULL`) unless
        `force_overwrite_manual` is True. For replaced pages, sets `updated_by = NULL`,
        `status = 'ocr_done'`, `ocr_milestone = 'succeeded'`, and resets
        `spell_check_milestone` to `'idle'` when `reset_spell_check` is True.

        Returns `(pages_updated, pages_unchanged)`.
        """
        if existing_pages is None:
            existing_pages = await self.find_by_book(book_id, limit=20000)
        existing_by_num = {p.page_number: p for p in existing_pages}

        rows_to_upsert: List[dict] = []
        updated_page_ids: List[int] = []
        pages_unchanged = 0
        target_sc_milestone = (
            PAGE_MILESTONE_IDLE if reset_spell_check else PAGE_MILESTONE_SUCCEEDED
        )

        for item in pages_payload:
            if item.get("skipped"):
                pages_unchanged += 1
                continue

            page_num = int(
                item.get("page_number")
                if item.get("page_number") is not None
                else item["pageNumber"]
            )
            raw_text = (item.get("text") or "").replace("\x00", "")
            existing = existing_by_num.get(page_num)

            detected_page_num = (
                item.get("detected_page_number")
                if "detected_page_number" in item
                else item.get("detectedPageNumber")
            )
            if detected_page_num is not None:
                detected_page_num = int(detected_page_num)

            if (
                not force_overwrite_manual
                and existing is not None
                and bool(getattr(existing, "updated_by", None))
            ):
                if (
                    detected_page_num is not None
                    and getattr(existing, "detected_page_number", None)
                    != detected_page_num
                ):
                    existing.detected_page_number = detected_page_num
                pages_unchanged += 1
                continue

            raw_is_toc = (
                item.get("is_toc")
                if "is_toc" in item and item.get("is_toc") is not None
                else item.get("isToc")
            )
            if raw_is_toc is None:
                is_toc = bool(existing.is_toc) if existing is not None else False
            else:
                is_toc = bool(raw_is_toc)

            if (
                existing is not None
                and (existing.text or "") == raw_text
                and bool(existing.is_toc) == is_toc
                and getattr(existing, "detected_page_number", None) == detected_page_num
            ):
                pages_unchanged += 1
                continue

            if existing is not None and getattr(existing, "id", None) is not None:
                updated_page_ids.append(existing.id)

            rows_to_upsert.append(
                {
                    "book_id": book_id,
                    "page_number": page_num,
                    "text": raw_text,
                    "is_toc": is_toc,
                    "detected_page_number": detected_page_num,
                    "status": "ocr_done",
                    "error": None,
                    "ocr_milestone": PAGE_MILESTONE_SUCCEEDED,
                    "spell_check_milestone": target_sc_milestone,
                    "updated_by": None,
                }
            )

        if updated_page_ids:
            from app.db.models import PageSpellIssue

            await self.session.execute(
                delete(PageSpellIssue).where(
                    PageSpellIssue.page_id.in_(updated_page_ids)
                )
            )

        batch_size = 250
        for idx in range(0, len(rows_to_upsert), batch_size):
            batch = rows_to_upsert[idx : idx + batch_size]
            stmt = insert(Page).values(batch)
            stmt = stmt.on_conflict_do_update(
                index_elements=["book_id", "page_number"],
                set_={
                    "text": stmt.excluded.text,
                    "is_toc": stmt.excluded.is_toc,
                    "detected_page_number": stmt.excluded.detected_page_number,
                    "status": stmt.excluded.status,
                    "error": None,
                    "ocr_milestone": stmt.excluded.ocr_milestone,
                    "spell_check_milestone": stmt.excluded.spell_check_milestone,
                    "updated_by": None,
                    "last_updated": func.now(),
                },
            )
            await self.session.execute(stmt)

        if rows_to_upsert:
            await self.session.flush()

        return len(rows_to_upsert), pages_unchanged

    async def set_manual_content_pages(
        self,
        book_id: str,
        start_physical_page: int,
        start_content_page: int = 1,
    ) -> dict[str, int]:
        """Mark `start_physical_page` as printed page `start_content_page` (default 1)
        and backfill `content_page_number` across all pages of `book_id` with
        `content_page_number_manual = True`."""
        start_cp = max(1, int(start_content_page or 1))
        pages = await self.find_by_book(book_id, limit=20000)
        for p in pages:
            p.content_page_number_manual = True
            if p.page_number < start_physical_page or p.is_toc:
                p.content_page_number = None
            else:
                p.content_page_number = str(
                    p.page_number - start_physical_page + start_cp
                )

        offset = max(0, int(start_physical_page) - start_cp)
        await self.session.execute(
            update(Book).where(Book.id == book_id).values(content_page_offset=offset)
        )
        await self.session.flush()
        return await self.get_content_page_map(book_id)


def get_pages_repository(session: AsyncSession) -> PagesRepository:
    """Factory function for dependency injection"""
    return PagesRepository(session)
