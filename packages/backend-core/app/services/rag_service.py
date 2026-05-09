"""RAG service facade — public API unchanged, logic delegated to handler registry."""
from __future__ import annotations

import logging
import time
from typing import AsyncIterator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.characters import CHARACTERS, DEFAULT_CHARACTER_ID
from app.models.schemas import ChatRequest
from app.services.rag.context import QueryContext
from app.services.rag.llm_resources import llm_resources
from app.services.rag.registry import get_registry
from app.services.rag.utils import format_chat_history
from app.utils.observability import log_json

logger = logging.getLogger("app.rag")


class RAGService:
    """Backward-compatible public facade.

    Callers continue to use ``answer_question`` and ``answer_question_stream``
    exactly as before.  All intent detection and retrieval logic lives in the
    handler registry under ``services/rag/handlers/``.
    """

    def __init__(self) -> None:
        self._registry = get_registry()

    async def answer_question(
        self,
        req: ChatRequest,
        session: AsyncSession,
        user_id: Optional[str] = None,
    ) -> str:
        ctx = await self._build_context(req, session, user_id)
        answer = await self._registry.dispatch(ctx)
        await self._record_eval(ctx, answer)
        return answer

    async def answer_question_stream(
        self,
        req: ChatRequest,
        session: AsyncSession,
        user_id: Optional[str] = None,
        metadata_out: Optional[dict] = None,
    ) -> AsyncIterator[str]:
        ctx = await self._build_context(req, session, user_id)
        answer_chunks: list[str] = []
        try:
            async for chunk in self._registry.dispatch_stream(ctx):
                answer_chunks.append(chunk)
                yield chunk
        finally:
            await self._record_eval(ctx, "".join(answer_chunks))
            if metadata_out is not None:
                metadata_out["used_book_ids"] = ctx.used_book_ids

    # ------------------------------------------------------------------
    # Context construction
    # ------------------------------------------------------------------

    async def _build_context(
        self,
        req: ChatRequest,
        session: AsyncSession,
        user_id: Optional[str],
    ) -> QueryContext:
        """Resolve character, load LLM models, fetch book record if needed."""
        from app.db.repositories.books import BooksRepository
        from app.db.repositories.system_configs import SystemConfigsRepository
        from app.core.i18n import t

        is_global = req.book_id == "global"
        char_id = req.character_id or DEFAULT_CHARACTER_ID
        character = CHARACTERS.get(char_id)
        persona_prompt = character.persona_prompt if character else None
        character_categories = character.categories if character else []

        log_json(
            logger, logging.INFO, "RAG request",
            book_id=req.book_id, is_global=is_global,
            char_id=char_id, categories=character_categories,
        )

        configs_repo = SystemConfigsRepository(session)
        chat_model = await configs_repo.get_value("gemini_chat_model")
        if not chat_model:
            raise RuntimeError("system_config 'gemini_chat_model' is not set")
        embedding_model = await configs_repo.get_value("gemini_embedding_model")
        if not embedding_model:
            raise RuntimeError("system_config 'gemini_embedding_model' is not set")

        book = None
        if not is_global:
            books_repo = BooksRepository(session)
            book = await books_repo.get(req.book_id)
            if not book:
                raise ValueError(t("errors.book_not_found"))

        return QueryContext(
            session=session,
            question=req.question,
            book_id=req.book_id,
            is_global=is_global,
            current_page=req.current_page,
            character_id=char_id,
            user_id=user_id,
            history=req.history or [],
            book=book,
            persona_prompt=persona_prompt,
            character_categories=character_categories,
            chat_history_str=format_chat_history(req.history or []),
            rag_chain=llm_resources.get_rag_chain(chat_model),
            rewrite_chain=llm_resources.get_rewrite_chain(chat_model),
            embeddings=llm_resources.get_embeddings(embedding_model),
            start_ts=time.monotonic(),
            context_book_ids=req.context_book_ids or [],
        )

    # ------------------------------------------------------------------
    # Eval recording
    # ------------------------------------------------------------------

    async def _record_eval(self, ctx: QueryContext, answer: str) -> None:
        if ctx.session is None:
            return
        try:
            from app.db.repositories.rag_evaluations import RAGEvaluationsRepository
            from app.db.repositories.system_configs import SystemConfigsRepository
            enabled = await SystemConfigsRepository(ctx.session).get_value("rag_eval_enabled", "false")
            if enabled != "true":
                return
            repo = RAGEvaluationsRepository(ctx.session)
            await repo.create_evaluation(
                book_id=ctx.book_id,
                is_global=ctx.is_global,
                question=ctx.question,
                current_page=ctx.current_page,
                retrieved_count=ctx.retrieved_count,
                context_chars=ctx.context_chars,
                scores=ctx.scores,
                category_filter=ctx.category_filter,
                latency_ms=int((time.monotonic() - ctx.start_ts) * 1000),
                answer_chars=len(answer),
                user_id=ctx.user_id,
                agent_steps=ctx.agent_steps,
                tools_called=ctx.agent_tools_called or None,
                retry_count=ctx.agent_retry_count,
                final_chunk_count=ctx.agent_final_chunk_count,
            )
            await ctx.session.commit()
        except Exception as exc:
            log_json(logger, logging.WARNING, "RAG eval insert failed", error=str(exc))


rag_service = RAGService()
