"""decompose_query node — splits a multi-question input into individual sub-questions.

Heuristic first (count Arabic/Latin question marks). If > 1 is detected, a cheap
LLM call splits the input into at most 4 self-contained sub-questions. When a single
question is detected, the node is a no-op (zero LLM cost).

When decomposition happens the original HumanMessage is updated in-place (same message
ID) so that agent_step sees a numbered list of sub-questions to retrieve for.
"""
from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage
from langgraph.config import get_stream_writer

from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.decompose")

_MAX_SUB_QUESTIONS = 4

_SPLIT_PROMPT = """\
The user sent a message that may contain multiple questions. Extract each distinct question as a self-contained string.

Rules:
- Return a JSON array of question strings (no other text).
- At most {max_q} questions.
- Each question must be self-contained — include any implicit subject from context if needed.
- Keep the original language (Uyghur, English, or mixed).
- If there is only one question return a single-element array.
- IMPORTANT: If all questions concern the same entity, book, character, or event (e.g. "what is X? what is its purpose?"), they are a compound question — return a single-element array containing the full original message unchanged.
- Only split when the questions are clearly about different topics or entities.

Message: {question}

JSON array:"""


_COMPARISON_PATTERNS = re.compile(
    r"\b(commonalit|similar|differ|compar|contrast|vs\.?|versus|both|between)\b"
    r"|ئوخشاشلىق|پەرق|سېلىشتۇر|ئىككىسى",
    re.IGNORECASE,
)


def _question_mark_count(text: str) -> int:
    return text.count("؟") + text.count("?")


def _is_multi_entity_question(text: str) -> bool:
    """Return True when the question compares/contrasts multiple books/entities."""
    return bool(_COMPARISON_PATTERNS.search(text))


async def _llm_split(question: str, model_name: str) -> list[str]:
    from app.langchain.models import generate_text

    prompt = _SPLIT_PROMPT.format(max_q=_MAX_SUB_QUESTIONS, question=question)
    try:
        raw = await generate_text(prompt, model_name)
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            parts = json.loads(m.group())
            if isinstance(parts, list) and all(isinstance(p, str) for p in parts):
                return [p.strip() for p in parts if p.strip()][:_MAX_SUB_QUESTIONS]
    except Exception as exc:
        log_json(logger, logging.WARNING, "decompose LLM call failed, keeping original", error=str(exc))
    return [question]


async def decompose_query_node(state: AgentState) -> dict:
    writer = get_stream_writer()
    ctx = state["ctx"]
    question = ctx.enriched_question or ctx.question

    if _question_mark_count(question) <= 1 and not _is_multi_entity_question(question):
        return {"sub_questions": [question]}

    sub_questions = await _llm_split(question, ctx.agent_model)

    if len(sub_questions) <= 1:
        return {"sub_questions": [question]}

    log_json(logger, logging.INFO, "Query decomposed", count=len(sub_questions))
    writer({"type": "decompose", "count": len(sub_questions)})

    # Update the existing HumanMessage in-place so agent_step sees all sub-questions.
    # add_messages replaces any message whose id matches an existing one.
    original_msg = state["messages"][-1]
    numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
    updated_content = original_msg.content + f"\n\n[Sub-questions]\n{numbered}"
    updated_msg = HumanMessage(content=updated_content, id=original_msg.id)

    return {
        "messages": [updated_msg],
        "sub_questions": sub_questions,
    }
