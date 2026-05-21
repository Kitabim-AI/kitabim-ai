"""plan_query node — fast heuristic intent detection before the agent loop.

Emits a 'planning' SSE event and optionally pre-resolves obvious pronouns via
heuristics (no LLM call — zero latency). The query_plan dict informs the
agent_step prompt and the routing logic.
"""
from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.planner")

# Uyghur pronouns that signal a co-reference needing rewrite_query
_UYGHUR_PRONOUNS = {"ئۇ", "بۇ", "شۇ", "ئۇنىڭ", "بۇنىڭ", "ئۇنى", "بۇنى"}

# Patterns used for lightweight intent detection
_CATALOG_PATTERNS = {"كىم يازغان", "ئاپتورى كىم", "ئاپتور كىم", "نىمە يازغان", "قانداق كىتاب"}
_PAGE_PATTERNS = {"بۇ بەتتە", "بەتتە نېمە", "بۇ بەت", "read this page", "current page"}


def _detect_intent(question: str, ctx) -> str:
    q = question.lower()
    if ctx.current_page and any(p in q for p in _PAGE_PATTERNS):
        return "current_page"
    if any(p in q for p in _CATALOG_PATTERNS):
        return "catalog"
    return "content_search"


def _needs_rewrite(question: str, ctx) -> bool:
    if not ctx.history:
        return False
    has_pronoun = any(p in question for p in _UYGHUR_PRONOUNS)
    has_topic_shift = "چۇ" in question
    return has_pronoun or has_topic_shift


async def plan_query_node(state: AgentState) -> dict:
    writer = get_stream_writer()
    ctx = state["ctx"]
    question = ctx.enriched_question or ctx.question

    intent = _detect_intent(question, ctx)
    needs_rewrite = _needs_rewrite(question, ctx)

    log_json(logger, logging.INFO, "Query planned", intent=intent, needs_rewrite=needs_rewrite)
    writer({"type": "planning", "intent": intent})

    return {
        "query_plan": {
            "intent": intent,
            "needs_rewrite": needs_rewrite,
            "refined_question": question,
        }
    }
