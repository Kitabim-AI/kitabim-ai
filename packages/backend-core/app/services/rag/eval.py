"""Ragas evaluation runner for Kitabim.AI RAG quality assessment.

Runs offline semantic evaluation for a single RAGEvaluation record using Ragas
and a Gemini judge model (gemini-3-flash-preview) which has Uyghur language support.

Metrics evaluated:
  - faithfulness:        Are all claims in the answer grounded in the context?
  - answer_relevance:   Does the answer address the question?

Context Recall and Context Precision require a ground-truth reference answer and
are therefore only evaluated in offline batch mode (see scripts/run_ragas_eval.py).

Uyghur-specific tuning:
  The Uyghur instruction is embedded as a system instruction on the judge LLM so
  it is prepended to every Ragas metric call automatically, regardless of which
  internal prompt template Ragas uses.  This is more reliable than patching private
  Ragas attributes which change between library versions.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.utils.observability import log_json

logger = logging.getLogger("app.services.rag.eval")

# Uyghur instruction embedded into the judge LLM as a system instruction.
# It is injected at the model level so it applies to faithfulness AND
# answer_relevancy without touching Ragas internals.
_UYGHUR_JUDGE_INSTRUCTION = (
    "IMPORTANT: The question, context, and answer are written in the Uyghur language "
    "using Perso-Arabic script. Uyghur is an agglutinative Turkic language — words may "
    "carry grammatical suffixes that alter their surface form but not their meaning. "
    "Do NOT penalise morphological variations of the same word (e.g. 'كىتاب' vs 'كىتابنى'). "
    "Evaluate faithfulness and relevance purely on semantic content."
)


def _build_judge_llm(model_name: str) -> object:
    """Return a ChatGoogleGenerativeAI instance with the Uyghur system instruction baked in.

    The system_instruction parameter is supported by langchain-google-genai>=1.0.4
    and causes the instruction to be prepended to every call made through this
    LLM instance — including all internal Ragas metric prompts.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI
    from app.core.config import settings
    return ChatGoogleGenerativeAI(
        model=model_name,
        google_api_key=settings.gemini_api_key,
        temperature=0,
        system_instruction=_UYGHUR_JUDGE_INSTRUCTION,
    )


def _configure_ragas_metrics(llm) -> None:
    """Assign the judge LLM to each Ragas metric instance.

    The Uyghur instruction is already embedded in *llm* via system_instruction,
    so no further prompt patching is required.
    """
    try:
        from ragas.metrics import faithfulness, answer_relevancy
        for metric in (faithfulness, answer_relevancy):
            metric.llm = llm
    except Exception as exc:
        log_json(logger, logging.WARNING, "Ragas metric LLM assignment failed", error=str(exc))


async def run_ragas_evaluation(
    question: str,
    answer: str,
    retrieved_context: str,
    model_name: str,
) -> dict[str, Optional[float]]:
    """Run faithfulness and answer relevance evaluation for a single query.

    Returns a dict with keys:
        faithfulness_score         (float 0-1 or None if Ragas returned no score)
        answer_relevance_score     (float 0-1 or None if Ragas returned no score)

    Raises on catastrophic failures (import errors, API auth failures, etc.) so
    the caller (eval_job) can decide whether to retry.  Ragas metric-level failures
    within the evaluation run are captured by raise_exceptions=False and result in
    None scores rather than exceptions.
    """
    from datasets import Dataset
    from ragas import evaluate
    from ragas.metrics import answer_relevancy, faithfulness

    llm = _build_judge_llm(model_name)
    _configure_ragas_metrics(llm)

    # Ragas expects a HuggingFace Dataset with specific column names
    data = Dataset.from_dict({
        "question": [question],
        "answer": [answer],
        "contexts": [[retrieved_context]],
    })

    scores = evaluate(
        dataset=data,
        metrics=[faithfulness, answer_relevancy],
        llm=llm,
        raise_exceptions=False,
    )

    result: dict[str, Optional[float]] = {
        "faithfulness_score": None,
        "answer_relevance_score": None,
    }

    df = scores.to_pandas()
    if not df.empty:
        row = df.iloc[0]
        if "faithfulness" in row and row["faithfulness"] is not None:
            result["faithfulness_score"] = float(row["faithfulness"])
        if "answer_relevancy" in row and row["answer_relevancy"] is not None:
            result["answer_relevance_score"] = float(row["answer_relevancy"])

    log_json(
        logger, logging.INFO, "Ragas evaluation completed",
        faithfulness=result["faithfulness_score"],
        answer_relevance=result["answer_relevance_score"],
    )

    return result
