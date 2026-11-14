"""Repository for two-tier book structure sections (`book_sections`)."""

from __future__ import annotations

from typing import Any, List, Optional

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import BookSection
from app.db.repositories.base_repository import BaseRepository


class BookSectionsRepository(BaseRepository[BookSection]):
    """Data access layer for `BookSection` hierarchy and short-work lookup."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, BookSection)

    async def replace_for_book(
        self, book_id: str, sections: List[dict[str, Any]]
    ) -> List[BookSection]:
        """Atomically replace all `book_sections` rows for `book_id`.

        Supports two-level hierarchy via either explicit `parent_id` or
        `parent_section_index` pointing to a level-1 section's `section_index`.
        """
        await self.session.execute(
            delete(BookSection).where(BookSection.book_id == book_id)
        )
        await self.session.flush()

        if not sections:
            return []

        created_by_index: dict[int, BookSection] = {}
        ordered_models: List[BookSection] = []

        # Pass 1: Insert level-1 sections (or sections without parent_section_index)
        for item in sorted(
            sections, key=lambda s: (int(s.get("level", 1)), int(s["section_index"]))
        ):
            parent_id = item.get("parent_id")
            parent_idx = item.get("parent_section_index")
            if parent_id is None and parent_idx is not None:
                parent_obj = created_by_index.get(int(parent_idx))
                if parent_obj is not None:
                    parent_id = parent_obj.id

            model = BookSection(
                book_id=book_id,
                parent_id=parent_id,
                section_index=int(item["section_index"]),
                level=int(item.get("level", 1)),
                section_type=str(item.get("section_type", "chapter")),
                title=str(item["title"]),
                normalized_title=str(item["normalized_title"]),
                toc_printed_page=item.get("toc_printed_page"),
                start_page=int(item["start_page"]),
                start_block_index=int(item.get("start_block_index", 0)),
                end_page=int(item["end_page"]),
                end_block_index=int(item.get("end_block_index", 999999)),
                source=str(item.get("source", "header_detected")),
                confidence=float(item.get("confidence", 1.0)),
            )
            self.session.add(model)
            await self.session.flush()
            created_by_index[model.section_index] = model
            ordered_models.append(model)

        ordered_models.sort(key=lambda m: m.section_index)
        return ordered_models

    async def list_by_book(self, book_id: str) -> List[BookSection]:
        """Return all sections for `book_id` ordered by `section_index`."""
        stmt = (
            select(BookSection)
            .where(BookSection.book_id == book_id)
            .order_by(BookSection.section_index.asc())
        )
        res = await self.session.execute(stmt)
        return list(res.scalars().all())

    async def list_leaf_sections(self, book_id: str) -> List[BookSection]:
        """Return chunkable sections in reading order (`section_index ASC`).

        Includes leaf sections (`s.id not in parent_ids`) plus any parent chapter
        that starts before its first child section (whose preamble end boundary is
        computed by `ChunkingService.chunk_book_sections` via `close_span_before_next`).
        """
        all_sections = await self.list_by_book(book_id)
        children_by_parent: dict[int, List[BookSection]] = {}
        for s in all_sections:
            if s.parent_id is not None:
                children_by_parent.setdefault(int(s.parent_id), []).append(s)

        result: List[BookSection] = []
        for s in all_sections:
            children = children_by_parent.get(int(s.id)) if s.id is not None else None
            if not children:
                result.append(s)
                continue

            first_child = min(
                children,
                key=lambda c: (
                    int(c.start_page),
                    int(getattr(c, "start_block_index", 0)),
                    int(c.section_index),
                ),
            )
            s_start = (int(s.start_page), int(getattr(s, "start_block_index", 0)))
            fc_start = (
                int(first_child.start_page),
                int(getattr(first_child, "start_block_index", 0)),
            )
            if s_start < fc_start:
                result.append(s)
        return result

    async def search_by_normalized_title(
        self,
        normalized_title: str,
        book_ids: Optional[List[str]] = None,
        author_filter: Optional[str] = None,
        limit: int = 25,
    ) -> List[dict[str, Any]]:
        """Search `book_sections` by normalized title with exact-before-fuzzy ranking.

        Orders results by:
        1. Exact `normalized_title` match before prefix/substring fuzzy match
        2. `section_type = 'work'` before `'chapter'`
        3. `confidence DESC`
        4. `Book.upload_date DESC, Book.id ASC, bs.section_index ASC`
        """
        norm = (normalized_title or "").strip()
        if not norm:
            return []
        if book_ids is not None and len(book_ids) == 0:
            return []

        escaped_norm = (
            norm.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )

        book_clause = "AND bs.book_id = ANY(:book_ids)" if book_ids else ""
        author_clause = (
            "AND b.author IS NOT NULL AND b.author ILIKE :author_pattern"
            if author_filter
            else ""
        )

        sql = text(f"""
            SELECT
                bs.id AS section_id,
                bs.book_id,
                bs.parent_id,
                bs.section_index,
                bs.level,
                bs.section_type,
                bs.title,
                bs.normalized_title,
                bs.toc_printed_page,
                bs.start_page,
                bs.start_block_index,
                bs.end_page,
                bs.end_block_index,
                bs.source,
                bs.confidence,
                parent_bs.title AS parent_title,
                b.title AS book_title,
                b.author AS book_author,
                b.volume AS book_volume,
                b.total_pages AS book_total_pages,
                p_start.content_page_number AS content_start_page,
                p_end.content_page_number AS content_end_page,
                CASE WHEN bs.normalized_title = :norm THEN 0 ELSE 1 END AS exact_rank
            FROM book_sections bs
            JOIN books b ON b.id = bs.book_id
            LEFT JOIN book_sections parent_bs ON parent_bs.id = bs.parent_id
            LEFT JOIN pages p_start
                ON p_start.book_id = bs.book_id AND p_start.page_number = bs.start_page
            LEFT JOIN pages p_end
                ON p_end.book_id = bs.book_id AND p_end.page_number = bs.end_page
            WHERE b.status != 'error'
              AND bs.section_type IN ('work', 'chapter')
              AND (
                  bs.normalized_title = :norm
                  OR (
                      char_length(:norm) >= 3
                      AND (
                          bs.normalized_title LIKE :prefix_pattern ESCAPE '\\'
                          OR bs.normalized_title LIKE :contains_pattern ESCAPE '\\'
                          OR (
                              char_length(bs.normalized_title) >= 3
                              AND :norm LIKE (
                                  replace(
                                      replace(
                                          replace(bs.normalized_title, '\\', '\\\\'),
                                          '%',
                                          '\\%'
                                      ),
                                      '_',
                                      '\\_'
                                  ) || '%'
                              ) ESCAPE '\\'
                          )
                      )
                  )
              )
              {book_clause}
              {author_clause}
            ORDER BY
                exact_rank ASC,
                CASE WHEN bs.section_type = 'work' THEN 0 ELSE 1 END ASC,
                bs.confidence DESC,
                b.upload_date DESC,
                b.id ASC,
                bs.section_index ASC
            LIMIT :limit
        """)

        params: dict[str, Any] = {
            "norm": norm,
            "prefix_pattern": f"{escaped_norm}%",
            "contains_pattern": f"% {escaped_norm}%",
            "limit": int(limit),
        }
        if book_ids:
            params["book_ids"] = [str(bid) for bid in book_ids]
        if author_filter:
            params["author_pattern"] = f"%{author_filter.strip()}%"

        res = await self.session.execute(sql, params)
        rows = res.fetchall()
        return [
            {
                "section_id": row.section_id,
                "book_id": str(row.book_id),
                "parent_id": row.parent_id,
                "parent_title": row.parent_title,
                "section_index": row.section_index,
                "level": row.level,
                "section_type": row.section_type,
                "title": row.title,
                "normalized_title": row.normalized_title,
                "toc_printed_page": row.toc_printed_page,
                "start_page": row.start_page,
                "start_block_index": row.start_block_index,
                "end_page": row.end_page,
                "end_block_index": row.end_block_index,
                "source": row.source,
                "confidence": float(row.confidence),
                "book_title": row.book_title,
                "book_author": row.book_author,
                "book_volume": row.book_volume,
                "book_total_pages": row.book_total_pages,
                "content_start_page": row.content_start_page,
                "content_end_page": row.content_end_page,
                "is_exact": row.exact_rank == 0,
            }
            for row in rows
        ]

    find_matching_short_works = search_by_normalized_title


def get_book_sections_repository(session: AsyncSession) -> BookSectionsRepository:
    """Factory function for dependency injection."""
    return BookSectionsRepository(session)
