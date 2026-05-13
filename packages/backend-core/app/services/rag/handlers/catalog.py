"""CatalogHandler — answers author/catalog questions using an LLM over book metadata."""
from __future__ import annotations

import logging
from typing import AsyncIterator, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Book
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import entity_matches_question, is_author_or_catalog_query
from app.services.rag.answer_builder import generate_answer, generate_answer_stream

logger = logging.getLogger("app.rag.catalog")


class CatalogHandler(QueryHandler):
    intent_name = "catalog"
    priority = 50

    def can_handle(self, ctx: QueryContext) -> bool:
        return is_author_or_catalog_query(ctx.question)

    async def handle(self, ctx: QueryContext) -> str:
        context, retrieved_count = await self._build_catalog_context(
            ctx.question, ctx.session, ctx.character_categories
        )
        context = self._prepend_current_book(context, ctx)
        ctx.retrieved_count = retrieved_count
        ctx.context_chars = len(context)
        ctx.category_filter = ctx.character_categories

        return await generate_answer(
            context,
            ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            suppress_page_notice=True,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        )

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        context, retrieved_count = await self._build_catalog_context(
            ctx.question, ctx.session, ctx.character_categories
        )
        context = self._prepend_current_book(context, ctx)
        ctx.retrieved_count = retrieved_count
        ctx.context_chars = len(context)
        ctx.category_filter = ctx.character_categories

        async for chunk in generate_answer_stream(
            context,
            ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            suppress_page_notice=True,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield chunk

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
    ) -> Tuple[str, int]:
        """Build the most specific context from the books table.

        Priority:
        1. Known book title in question  → info about that book (+ author)
        2. Known author name in question → that author's books
        3. Fallback                      → full library catalog
        """
        q = question.strip()

        # ── 1. Try to match a book title ────────────────────────────────────
        stmt = select(Book.title).where(Book.status != "error")
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))

        title_result = await session.execute(stmt)
        titles = [row[0] for row in title_result.fetchall() if row[0]]
        matched_title = next(
            (t for t in titles if entity_matches_question(t, q)), None
        )

        if matched_title:
            stmt = select(
                Book.title, Book.author, Book.volume, Book.total_pages, Book.status
            ).where(
                Book.status != "error",
                Book.title == matched_title,
            ).order_by(Book.volume)
            result = await session.execute(stmt)
            books = result.fetchall()
            if books:
                lines = [f"Information about '{matched_title}':"]
                for book in books:
                    author = book.author or "Unknown"
                    volume = f", Volume {book.volume}" if book.volume is not None else ""
                    pages = f", {book.total_pages} pages" if book.total_pages else ""
                    status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
                    lines.append(
                        f"- Title: {book.title}{volume}, Author: {author}{pages}{status_tag}"
                    )
                return "\n".join(lines), len(books)

        # ── 2. Try to match an author name ───────────────────────────────────
        stmt = (
            select(Book.author)
            .where(Book.author.isnot(None), Book.status != "error")
            .distinct()
        )
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))

        author_result = await session.execute(stmt)
        authors = [row[0] for row in author_result.fetchall() if row[0]]
        matched_author = next(
            (a for a in authors if entity_matches_question(a, q)), None
        )

        if matched_author:
            stmt = select(
                Book.title, Book.author, Book.volume, Book.total_pages, Book.status
            ).where(
                Book.status != "error",
                Book.author == matched_author,
            ).order_by(Book.volume, Book.title)
            result = await session.execute(stmt)
            books = result.fetchall()
            lines = [f"Books by author '{matched_author}' in the library:"]
            for book in books:
                volume = f", Volume {book.volume}" if book.volume is not None else ""
                pages = f", {book.total_pages} pages" if book.total_pages else ""
                status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
                lines.append(f"- {book.title}{volume}{pages}{status_tag}")
            return "\n".join(lines), len(books)

        # ── 3. Full catalog fallback ─────────────────────────────────────────
        stmt = select(Book.title, Book.author, Book.status).where(Book.status != "error")
        if categories:
            from sqlalchemy import text as sa_text
            stmt = stmt.where(sa_text("categories && :cats").bindparams(cats=categories))
        stmt = stmt.order_by(Book.title)

        result = await session.execute(stmt)
        all_books = result.fetchall()

        if not all_books:
            return "NO BOOKS FOUND IN THE LIBRARY.", 0

        lines = ["Library catalog — available books:"]
        for book in all_books:
            title = book.title or "Unknown"
            author = book.author
            status_tag = f" [Status: {book.status}]" if book.status != "ready" else ""
            if author:
                lines.append(f"- {title} (Author: {author}){status_tag}")
            else:
                lines.append(f"- {title}{status_tag}")
        return "\n".join(lines), len(all_books)
