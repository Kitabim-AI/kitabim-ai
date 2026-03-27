"""BooksByAuthorHandler — returns a list of books by an author named in the question."""
from __future__ import annotations

from typing import AsyncIterator

from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur

_BOOKS_BY_AUTHOR_KEYWORDS = [
    "نىڭ كىتابلىرى", "نىڭ قاندان ئەسەرلىرى",
    "ئەسەرلىرى قايسىلار", "كىتابلىرى قايسىلار",
    "قانچە كىتاب يازغان", "نەچچە ئەسەر يازغان",
    "يازغان كىتابلار", "يازغان ئەسەرلەر",
]
_BOOKS_BY_AUTHOR_KEYWORDS_NORM = [normalize_uyghur(k) for k in _BOOKS_BY_AUTHOR_KEYWORDS]


class BooksByAuthorHandler(QueryHandler):
    """Returns a structured list of books by an author named in the question.

    Falls back to CatalogHandler when no matching author is found.
    """

    intent_name = "books_by_author"
    priority = 21

    def can_handle(self, ctx: QueryContext) -> bool:
        q = normalize_uyghur(ctx.question.strip())
        return any(k in q for k in _BOOKS_BY_AUTHOR_KEYWORDS_NORM)

    async def handle(self, ctx: QueryContext) -> str:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        books = await repo.find_books_by_author_in_question(
            ctx.question, ctx.character_categories or None
        )
        if books:
            ctx.retrieved_count = len(books)
            return self._format(books)

        from app.services.rag.handlers.catalog import CatalogHandler
        return await CatalogHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        books = await repo.find_books_by_author_in_question(
            ctx.question, ctx.character_categories or None
        )
        if books:
            ctx.retrieved_count = len(books)
            yield self._format(books)
            return

        from app.services.rag.handlers.catalog import CatalogHandler
        async for chunk in CatalogHandler().handle_stream(ctx):
            yield chunk

    @staticmethod
    def _format(books) -> str:
        author = books[0].author or "نامەلۇم"
        lines = [t("rag.books_by_author_header", author=author)]
        for b in books:
            vol = f" ({t('rag.volume_label', volume=b.volume)})" if b.volume is not None else ""
            pages = t("rag.pages_suffix", pages=b.total_pages) if b.total_pages else ""
            lines.append(f"- {b.title}{vol}{pages}")
        return "\n".join(lines)
