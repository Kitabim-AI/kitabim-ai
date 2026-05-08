"""AgentRAGHandler — agentic replacement for StandardRAGHandler.

Enabled via system_config key `agentic_rag_enabled` = "true".
Falls back to StandardRAGHandler when the flag is off so the registry
change is zero-risk during Phase 1.

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
    """Agentic RAG handler — LLM-driven retrieval loop.

    Priority 998 sits one slot above StandardRAGHandler (999) so it intercepts
    all unmatched intents when the feature flag is on.
    """

    intent_name = "agent_rag"
    priority = 998

    def can_handle(self, ctx: QueryContext) -> bool:
        return True

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    async def handle(self, ctx: QueryContext) -> str:
        agent_model = await self._resolve_agent_model(ctx)
        if agent_model is None:
            return await self._fallback(ctx)

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
        if agent_model is None:
            async for chunk in self._fallback_stream(ctx):
                yield chunk
            return

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

    async def _resolve_agent_model(self, ctx: QueryContext) -> str | None:
        """Return the loop model name, or None if the feature flag is off.

        Priority: gemini_agent_loop_model → gemini_agent_model → gemini_chat_model.
        Set gemini_agent_loop_model to a fast model (e.g. gemini-2.0-flash) to keep
        tool-calling decisions snappy while using a heavier model for answers.
        """
        from app.db.repositories.system_configs import SystemConfigsRepository

        configs_repo = SystemConfigsRepository(ctx.session)
        enabled = await configs_repo.get_value("agentic_rag_enabled", "false")
        if enabled != "true":
            return None

        loop_model = (
            await configs_repo.get_value("gemini_agent_loop_model")
            or await configs_repo.get_value("gemini_agent_model")
            or await configs_repo.get_value("gemini_chat_model")
        )

        log_json(logger, logging.INFO, "Agent RAG enabled", loop_model=loop_model)
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

    async def _fallback(self, ctx: QueryContext) -> str:
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        return await StandardRAGHandler().handle(ctx)

    async def _fallback_stream(self, ctx: QueryContext) -> AsyncIterator[str]:
        from app.services.rag.handlers.standard_rag import StandardRAGHandler
        async for chunk in StandardRAGHandler().handle_stream(ctx):
            yield chunk
