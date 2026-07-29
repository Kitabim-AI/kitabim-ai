"""LLM-as-judge scoring for RAG chat answer quality (faithfulness/answer_relevance/context_precision)."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from google.genai import types

from app.core.prompts import RAG_JUDGE_PROMPT
from app.llm.models import build_text_llm
from app.utils.observability import log_json

logger = logging.getLogger("app.services.rag.judge")


@dataclass(frozen=True)
class JudgeScores:
    faithfulness: float
    answer_relevance: float
    context_precision: float


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


async def score_answer(
    question: str, answer: str, context: str, model: str
) -> JudgeScores:
    """Score a RAG chat turn on faithfulness, answer_relevance, and context_precision
    with a single combined LLM-judge call. Raises on malformed/missing judge output —
    callers are expected to treat that as a scoring failure, not silently default."""
    prompt = RAG_JUDGE_PROMPT.format(question=question, context=context, answer=answer)

    llm = build_text_llm(model)
    res_text = await llm.ainvoke(
        prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )

    match = re.search(r"\{.*\}", res_text, re.DOTALL)
    if not match:
        raise ValueError(f"Judge response contained no JSON object: {res_text!r}")

    data = json.loads(match.group())

    try:
        scores = JudgeScores(
            faithfulness=_clamp(float(data["faithfulness"])),
            answer_relevance=_clamp(float(data["answer_relevance"])),
            context_precision=_clamp(float(data["context_precision"])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Judge response missing/invalid score fields: {data!r}"
        ) from exc

    log_json(
        logger,
        logging.INFO,
        "RAG judge scored answer",
        faithfulness=scores.faithfulness,
        answer_relevance=scores.answer_relevance,
        context_precision=scores.context_precision,
    )
    return scores
