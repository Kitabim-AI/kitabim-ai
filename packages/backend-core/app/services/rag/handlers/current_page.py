"""CurrentPageHandler — restricts answer context to the current page only."""
from __future__ import annotations

from typing import AsyncIterator

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.services.rag.utils import is_current_page_query
from app.services.rag.answer_builder import generate_answer, generate_answer_stream


class CurrentPageHandler(QueryHandler):
    intent_name = "current_page"
    priority = 40

    def can_handle(self, ctx: QueryContext) -> bool:
        if ctx.is_global:
            return False
        return is_current_page_query(ctx.question)

    async def _get_page_context(self, ctx: QueryContext) -> str:
        if not ctx.current_page or not ctx.book:
            return ""
        from app.db.repositories.pages import PagesRepository
        from app.utils.markdown import strip_markdown

        pages_repo = PagesRepository(ctx.session)
        page_rec = await pages_repo.find_one(ctx.book_id, ctx.current_page)
        if page_rec and page_rec.text:
            page_text = strip_markdown(page_rec.text or "")
            book = ctx.book
            author_info = f", Author: {book.author}" if book.author else ""
            volume_info = f", Volume {book.volume}" if book.volume is not None else ""
            return (
                f"[BookID: {ctx.book_id}, Book: {book.title or 'Unknown'}"
                f"{author_info}{volume_info}, Page {ctx.current_page}]\n"
                f"{page_text}"
            )
        return ""

    async def handle(self, ctx: QueryContext) -> str:
        context = await self._get_page_context(ctx) or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
        ctx.context_chars = len(context)
        return await generate_answer(
            context,
            ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        )

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        context = await self._get_page_context(ctx) or "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
        ctx.context_chars = len(context)
        async for chunk in generate_answer_stream(
            context,
            ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield chunk
