"""AgentRAGHandler — agentic replacement for StandardRAGHandler.

Agent model is read from system_config key `gemini_agent_model`.
If unset, falls back to the chat model used for answering.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.handler")


class AgentRAGHandler(QueryHandler):
    """Agentic RAG handler — LLM-driven retrieval loop. Fallback for all unmatched intents."""

    intent_name = "agent_rag"
    priority = 998

    def can_handle(self, _ctx: QueryContext) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def handle(self, ctx: QueryContext) -> str:
        agent_model = await self._resolve_agent_model(ctx)

        from app.services.rag.agent.loop import run_agent_loop
        from app.services.rag.agent.context_builder import format_observations_as_context
        from app.services.rag.answer_builder import generate_answer

        observations, llm_calls = await run_agent_loop(ctx, agent_model)
        context, used_book_ids, chunk_count = format_observations_as_context(observations)

        self._populate_ctx_metrics(ctx, observations, used_book_ids, llm_calls, chunk_count)

        return await generate_answer(
            context,
            ctx.enriched_question or ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        )

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        agent_model = await self._resolve_agent_model(ctx)

        from app.services.rag.agent.loop import run_agent_loop
        from app.services.rag.agent.context_builder import format_observations_as_context
        from app.services.rag.answer_builder import generate_answer_stream

        observations, llm_calls = await run_agent_loop(ctx, agent_model)
        context, used_book_ids, chunk_count = format_observations_as_context(observations)

        self._populate_ctx_metrics(ctx, observations, used_book_ids, llm_calls, chunk_count)

        async for chunk in generate_answer_stream(
            context,
            ctx.enriched_question or ctx.question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield chunk

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolve_agent_model(self, ctx: QueryContext) -> str:
        """Return the loop model name.

        Priority: gemini_agent_loop_model → gemini_agent_model → gemini_chat_model.
        Set gemini_agent_loop_model to a fast model (e.g. gemini-2.0-flash) to keep
        tool-calling decisions snappy while using a heavier model for answers.
        """
        from app.db.repositories.system_configs import SystemConfigsRepository

        configs_repo = SystemConfigsRepository(ctx.session)
        loop_model = (
            await configs_repo.get_value("gemini_agent_loop_model")
            or await configs_repo.get_value("gemini_agent_model")
            or await configs_repo.get_value("gemini_chat_model")
        )

        log_json(logger, logging.INFO, "Agent loop model resolved", loop_model=loop_model)
        return loop_model

    @staticmethod
    def _populate_ctx_metrics(
        ctx: QueryContext,
        observations: list[dict],
        used_book_ids: list[str],
        llm_calls: int,
        chunk_count: int,
    ) -> None:
        ctx.used_book_ids = used_book_ids
        all_chunks = [
            chunk
            for obs in observations
            if obs["tool"] == "search_chunks"
            for chunk in obs["result"].get("chunks", [])
        ]
        ctx.retrieved_count = len(all_chunks)
        ctx.scores = [c.get("score", 0.0) for c in all_chunks]
        ctx.agent_steps = llm_calls
        ctx.agent_tools_called = [obs["tool"] for obs in observations]
        ctx.agent_retry_count = sum(1 for obs in observations if obs["tool"] == "search_chunks")
        ctx.agent_final_chunk_count = chunk_count

