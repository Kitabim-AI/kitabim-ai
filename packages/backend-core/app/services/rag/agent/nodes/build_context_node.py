"""build_context node — formats accumulated observations into a RAG context string."""
from __future__ import annotations

import logging

from app.services.rag.agent.context_builder import format_observations_as_context
from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.build_context")


async def build_context_node(state: AgentState) -> dict:
    context, used_book_ids, chunk_count = format_observations_as_context(state["observations"])

    log_json(
        logger, logging.INFO, "Context built",
        chunks=chunk_count,
        books=len(used_book_ids),
        chars=len(context),
    )

    return {
        "retrieved_context": context,
        "used_book_ids": used_book_ids,
    }
