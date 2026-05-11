"""AgentRAGHandler — agentic replacement for StandardRAGHandler.

Agent model is resolved at context-build time (``ctx.agent_model``), which
consolidates all model-config lookups in ``RAGService._build_context``.
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
        from app.services.rag.agent.loop import run_agent_loop
        from app.services.rag.agent.context_builder import format_observations_as_context
        from app.services.rag.answer_builder import generate_answer

        log_json(logger, logging.INFO, "Agent loop model resolved", loop_model=ctx.agent_model)
        observations, llm_calls = await run_agent_loop(ctx, ctx.agent_model)
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
        from app.services.rag.agent.loop import run_agent_loop
        from app.services.rag.agent.context_builder import format_observations_as_context
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(logger, logging.INFO, "Agent loop model resolved", loop_model=ctx.agent_model)
        observations, llm_calls = await run_agent_loop(ctx, ctx.agent_model)
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


# Module-level singleton — reused by FollowUpHandler and CurrentVolumeHandler
# so they don't instantiate a new object on every request.
agent_rag_handler = AgentRAGHandler()
