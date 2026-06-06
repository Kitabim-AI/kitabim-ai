"""plan_query node — fast heuristic intent detection before the agent loop.

Emits a 'planning' SSE event (no LLM call — zero latency).
"""
from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.planner")

_CATALOG_PATTERNS = {"كىم يازغان", "ئاپتورى كىم", "ئاپتور كىم", "نىمە يازغان", "قانداق كىتاب"}
_PAGE_PATTERNS = {"بۇ بەتتە", "بەتتە نېمە", "بۇ بەت", "read this page", "current page"}


def _detect_intent(question: str, ctx) -> str:
    q = question.lower()
    if ctx.current_page and any(p in q for p in _PAGE_PATTERNS):
        return "current_page"
    if any(p in q for p in _CATALOG_PATTERNS):
        return "catalog"
    return "content_search"


async def plan_query_node(state: AgentState) -> dict:
    writer = get_stream_writer()
    ctx = state["ctx"]
    question = ctx.enriched_question or ctx.question

    intent = _detect_intent(question, ctx)

    log_json(logger, logging.INFO, "Query planned", intent=intent)
    writer({"type": "planning", "intent": intent})

    return {}
