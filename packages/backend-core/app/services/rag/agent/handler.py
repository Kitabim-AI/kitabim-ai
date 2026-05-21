"""AgentRAGHandler — LangGraph-backed agentic RAG.

handle()        → graph.ainvoke()  (non-streaming; collects all events internally)
handle_stream() → graph.astream()  (streams custom events: tool_call, chunk, etc.)

Yields from handle_stream() are str | dict:
  str  — raw text chunk (legacy fast-handler compat; not used by graph handler)
  dict — typed event: {"type": "chunk", "text": "..."} | {"type": "tool_call", ...} | etc.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator, Union

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.handler")


class AgentRAGHandler(QueryHandler):
    """LangGraph agentic RAG handler. Fallback for all unmatched intents."""

    intent_name = "agent_rag"
    priority = 998

    def can_handle(self, _ctx: QueryContext) -> bool:
        return True

    # ------------------------------------------------------------------
    # Non-streaming
    # ------------------------------------------------------------------

    async def handle(self, ctx: QueryContext) -> str:
        from app.services.rag.agent.graph import build_initial_state, get_or_build_graph, populate_ctx_from_state
        from app.utils.citation_fixer import fix_malformed_citations

        log_json(logger, logging.INFO, "LangGraph agent invoked (non-stream)", model=ctx.agent_model)

        graph = get_or_build_graph()
        initial_state = build_initial_state(ctx)

        final_state = await graph.ainvoke(initial_state)
        populate_ctx_from_state(ctx, final_state)

        answer = final_state.get("final_answer", "")
        return fix_malformed_citations(answer)

    # ------------------------------------------------------------------
    # Streaming — yields dicts (custom events) mixed with nothing else;
    # text chunks arrive as {"type": "chunk", "text": "..."}
    # ------------------------------------------------------------------

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[Union[str, dict]]:
        from app.services.rag.agent.graph import build_initial_state, get_or_build_graph, populate_ctx_from_state

        log_json(logger, logging.INFO, "LangGraph agent invoked (stream)", model=ctx.agent_model)

        graph = get_or_build_graph()
        initial_state = build_initial_state(ctx)

        final_state: dict = {}

        async for mode, data in graph.astream(
            initial_state, stream_mode=["custom", "values"]
        ):
            if mode == "custom":
                yield data
            elif mode == "values":
                final_state = data  # keep updating; last one is the terminal state

        if final_state:
            populate_ctx_from_state(ctx, final_state)

