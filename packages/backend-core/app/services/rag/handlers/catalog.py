"""CatalogHandler — answers author/catalog questions using an LLM over book metadata."""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from sqlalchemy import or_, select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book
from app.services.rag.context import QueryContext, resolve_rag_is_staff
from app.services.rag.utils import entity_matches_question

logger = logging.getLogger("app.rag.catalog")

_CATALOG_FALLBACK_MAX_BOOKS = 100


def _book_access_clauses(is_staff: bool) -> list:
    if is_staff:
        return [Book.status != "error"]
    return [
        Book.status == "ready",
        or_(
            Book.visibility == "public",
            Book.visibility.is_(None),
            Book.visibility == "",
        ),
    ]


class CatalogHandler:
    """Helper utilities for querying catalog and book metadata."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepend_current_book(context: str, ctx: QueryContext) -> str:
        """When in book-reader mode, prepend current book info to the catalog context."""
        if ctx.is_global or not ctx.book:
            return context
        book = ctx.book
        author_info = f", Author: {book.author}" if book.author else ""
        volume_info = f", Volume {book.volume}" if book.volume is not None else ""
        pages_info = f", {book.total_pages} pages" if book.total_pages else ""
        status_info = f" [Status: {book.status}]" if book.status != "ready" else ""

        intro = "Information about the book the user is currently reading:\n"
        intro += f"- Title: {book.title or 'Unknown'}{author_info}{volume_info}{pages_info}{status_info}\n\n---\n\n"
        return intro + context

    @staticmethod
    async def _build_catalog_context(
        question: str,
        session: AsyncSession,
        categories: Optional[List[str]] = None,
        is_staff: Optional[bool] = None,
    ) -> Tuple[str, int]:
        """Build the most specific context from the books table.

        Priority:
        1. Known book title in question  → info about that book (+ author)
        2. Known author name in question → that author's books
        3. Fallback                      → full library catalog (capped)
        """
        q = question.strip()
        access_clauses = _book_access_clauses(resolve_rag_is_staff(is_staff))
        cat_clause = (
            sa_text("categories && CAST(:cats AS text[])").bindparams(cats=categories)
            if categories
            else None
        )

        # ── 1. Try to match a book title ────────────────────────────────────
        stmt = select(Book.title).where(*access_clauses)
        if cat_clause is not None:
            stmt = stmt.where(cat_clause)

        title_result = await session.execute(stmt)
        titles = [row[0] for row in title_result.fetchall() if row[0]]
        matched_title = next((t for t in titles if entity_matches_question(t, q)), None)

        if matched_title:
            stmt = (
                select(
                    Book.id,
                    Book.title,
                    Book.author,
                    Book.volume,
                    Book.total_pages,
                    Book.status,
                )
                .where(
                    *access_clauses,
                    Book.title == matched_title,
                )
                .order_by(Book.volume)
            )
            if cat_clause is not None:
                stmt = stmt.where(cat_clause)
            result = await session.execute(stmt)
            books = result.fetchall()
            if books:
                lines = [f"Information about '{matched_title}':"]
                for book in books:
                    author = book.author or "Unknown"
                    volume = (
                        f", Volume {book.volume}" if book.volume is not None else ""
                    )
                    pages = f", {book.total_pages} pages" if book.total_pages else ""
                    status_tag = (
                        f" [Status: {book.status}]" if book.status != "ready" else ""
                    )
                    # BookID lets the agent scope search_chunks to this book —
                    # without it the agent invents an ID and gets 0 results.
                    lines.append(
                        f"- BookID: {book.id}, Title: {book.title}{volume}, "
                        f"Author: {author}{pages}{status_tag}"
                    )
                return "\n".join(lines), len(books)

        # ── 2. Try to match an author name ───────────────────────────────────
        stmt = (
            select(Book.author)
            .where(Book.author.isnot(None), *access_clauses)
            .distinct()
        )
        if cat_clause is not None:
            stmt = stmt.where(cat_clause)

        author_result = await session.execute(stmt)
        authors = [row[0] for row in author_result.fetchall() if row[0]]
        matched_author = next(
            (a for a in authors if entity_matches_question(a, q)), None
        )

        if matched_author:
            stmt = (
                select(
                    Book.id,
                    Book.title,
                    Book.author,
                    Book.volume,
                    Book.total_pages,
                    Book.status,
                )
                .where(
                    *access_clauses,
                    Book.author == matched_author,
                )
                .order_by(Book.volume, Book.title)
            )
            if cat_clause is not None:
                stmt = stmt.where(cat_clause)
            result = await session.execute(stmt)
            books = result.fetchall()
            lines = [f"Books by author '{matched_author}' in the library:"]
            for book in books:
                volume = f", Volume {book.volume}" if book.volume is not None else ""
                pages = f", {book.total_pages} pages" if book.total_pages else ""
                status_tag = (
                    f" [Status: {book.status}]" if book.status != "ready" else ""
                )
                lines.append(
                    f"- BookID: {book.id}, {book.title}{volume}{pages}{status_tag}"
                )
            return "\n".join(lines), len(books)

        # ── 3. Full catalog fallback (capped to avoid flooding context) ──────
        stmt = select(Book.title, Book.author, Book.status).where(*access_clauses)
        if cat_clause is not None:
            stmt = stmt.where(cat_clause)
        stmt = stmt.order_by(Book.title)

        result = await session.execute(stmt)
        all_books = result.fetchall()

        if not all_books:
            return "NO BOOKS FOUND IN THE LIBRARY.", 0

        shown_books = all_books[:_CATALOG_FALLBACK_MAX_BOOKS]
        lines = [f"Library catalog — available books (total: {len(all_books)}):"]
        for book in shown_books:
            title = book.title or "Unknown"
            author = book.author
            status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
            if author:
                lines.append(f"- {title} (Author: {author}){status_tag}")
            else:
                lines.append(f"- {title}{status_tag}")
        remaining = len(all_books) - len(shown_books)
        if remaining > 0:
            lines.append(
                f"... and {remaining} more books in the library (ask about a specific title or author for details)."
            )
        return "\n".join(lines), len(all_books)
