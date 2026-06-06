"""generate_answer node — streams answer tokens via StreamWriter."""
from __future__ import annotations

import logging

from langgraph.config import get_stream_writer

from app.services.rag.agent.state import AgentState
from app.services.rag.answer_builder import generate_answer_stream
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.generate_answer")


async def generate_answer_node(state: AgentState) -> dict:
    writer = get_stream_writer()
    ctx = state["ctx"]

    # Prefer graded context (Phase 3); fall back to raw retrieved context
    context = state.get("graded_context") or state.get("retrieved_context", "")
    sub_questions = state.get("sub_questions", [])
    if len(sub_questions) > 1:
        question = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
    else:
        question = ctx.enriched_question or ctx.question

    log_json(logger, logging.INFO, "Generating answer", context_chars=len(context))
    writer({"type": "answer_start"})

    full_answer = ""
    async for token in generate_answer_stream(
        context,
        question,
        ctx.rag_chain,
        chat_history=ctx.chat_history_str,
        persona_prompt=ctx.persona_prompt,
        is_global=ctx.is_global,
        has_categories=bool(ctx.character_categories),
    ):
        writer({"type": "chunk", "text": token})
        full_answer += token

    writer({"type": "answer_end"})
    log_json(logger, logging.INFO, "Answer generated", chars=len(full_answer))

    return {"final_answer": full_answer}
