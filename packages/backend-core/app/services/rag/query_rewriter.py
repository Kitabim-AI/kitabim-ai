"""QueryRewriter — LLM-based follow-up question rewriting for better embedding search."""
from __future__ import annotations

import hashlib
import logging

from app.core import cache_config
from app.core.config import settings
from app.services.cache_service import cache_service
from app.services.rag.context import QueryContext
from app.services.rag.utils import format_chat_history
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.query_rewriter")


class QueryRewriter:
    """Rewrite a follow-up question into a standalone question using the conversation history.

    The rewritten question resolves pronouns and implicit references so that the
    embedding search receives a semantically complete query rather than a fragment
    that only makes sense in context.  Falls back to the original question on any error.
    """

    async def rewrite(self, ctx: QueryContext) -> str:
        if not ctx.history or not ctx.rewrite_chain:
            return ctx.question

        history_str = format_chat_history(ctx.history)

        cache_key = cache_config.KEY_RAG_REWRITE.format(
            hash=hashlib.md5(
                (history_str + "|" + ctx.question.strip()).encode()
            ).hexdigest()
        )

        try:
            cached = await cache_service.get(cache_key)
            if cached and isinstance(cached, str):
                log_json(logger, logging.DEBUG, "Query rewrite cache hit")
                return cached
        except Exception as exc:
            log_json(logger, logging.WARNING, "Query rewrite cache read failed", error=str(exc))

        try:
            rewritten: str = await ctx.rewrite_chain.ainvoke(
                {"history": history_str, "question": ctx.question}
            )
            rewritten = rewritten.strip()
            if not rewritten:
                return ctx.question

            log_json(
                logger, logging.INFO, "Query rewritten",
                original=ctx.question[:120],
                rewritten=rewritten[:120],
            )

            try:
                await cache_service.set(cache_key, rewritten, ttl=settings.cache_ttl_rag_query)
            except Exception as exc:
                log_json(logger, logging.WARNING, "Query rewrite cache write failed", error=str(exc))

            return rewritten

        except Exception as exc:
            log_json(logger, logging.WARNING, "Query rewrite LLM failed, using original", error=str(exc))
            return ctx.question
