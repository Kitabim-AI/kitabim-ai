"""AuthorByTitleHandler — returns the author of a book mentioned in the question."""
from __future__ import annotations

from typing import AsyncIterator

from app.core.i18n import t
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import normalize_uyghur

_AUTHOR_KEYWORDS = [
    "مۇئەللىپى كىم", "كىم يازغان", "يازغۇچىسى كىم", "ئاپتورى كىم",
    "كىمنىڭ ئەسىرى", "كىمنىكى", "كىم تەرىپىدىن يازىلغان", "كىمنىڭ",
    "مۇئەللىپى", "يازغۇچىسى", "ئاپتورى",
]
_AUTHOR_KEYWORDS_NORM = [normalize_uyghur(k) for k in _AUTHOR_KEYWORDS]


class AuthorByTitleHandler(QueryHandler):
    """Returns structured author info for a book title mentioned in the question.

    Fires before CatalogHandler (priority 50) so the user gets a direct answer
    rather than an LLM-generated catalog response.  Falls back to CatalogHandler
    when no matching book title is found.
    """

    intent_name = "author_by_title"
    priority = 20

    def can_handle(self, ctx: QueryContext) -> bool:
        q = normalize_uyghur(ctx.question.strip())
        return any(k in q for k in _AUTHOR_KEYWORDS_NORM)

    async def handle(self, ctx: QueryContext) -> str:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        result = await repo.find_author_by_title_in_question(
            ctx.question, ctx.character_categories or None
        )
        if result:
            title, author = result
            ctx.retrieved_count = 1
            return t("rag.author_of_book", title=title, author=author)

        # Fall back to full catalog/author LLM response
        from app.services.rag.handlers.catalog import CatalogHandler
        return await CatalogHandler().handle(ctx)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        from app.db.repositories.books import BooksRepository
        repo = BooksRepository(ctx.session)
        result = await repo.find_author_by_title_in_question(
            ctx.question, ctx.character_categories or None
        )
        if result:
            title, author = result
            ctx.retrieved_count = 1
            yield t("rag.author_of_book", title=title, author=author)
            return

        from app.services.rag.handlers.catalog import CatalogHandler
        async for chunk in CatalogHandler().handle_stream(ctx):
            yield chunk
