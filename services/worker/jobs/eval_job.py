"""
Evaluation Job — runs Ragas semantic evaluation on a sampled RAG query.

Triggered by rag_service._record_eval when a query is selected for grading
(based on rag_eval_sampling_rate system config), or immediately by the
feedback endpoint when a user submits a thumbs-down rating.

Receives: eval_id (int) — the RAGEvaluation.id to score.

Retry behaviour:
  arq retries this job (up to max_tries) whenever it raises an exception.
  Transient failures (Gemini rate-limits, network errors) will be retried
  automatically.  After all retries are exhausted the row is marked 'failed'.
"""
from __future__ import annotations

import logging

from sqlalchemy import update

from app.db import session as db_session
from app.db.models import RAGEvaluation
from app.db.repositories.system_configs import SystemConfigsRepository
from app.services.rag.eval import run_ragas_evaluation
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.eval_job")


async def evaluate_rag_query(ctx, eval_id: int) -> None:
    """Fetch a RAGEvaluation row, run Ragas evaluation, and persist scores.

    arq passes ctx.job_try (1-based attempt counter).  We re-raise on
    transient failures so arq schedules a retry.  After the final attempt
    the row is marked eval_status='failed' instead of being left as 'queued'.
    """
    log_json(logger, logging.INFO, "RAG eval job started",
             eval_id=eval_id, attempt=ctx["job_try"])

    # ── 1. Load the evaluation record ────────────────────────────────────────
    async with db_session.async_session_factory() as session:
        result = await session.get(RAGEvaluation, eval_id)
        if result is None:
            log_json(logger, logging.WARNING, "RAGEvaluation not found", eval_id=eval_id)
            return

        question = result.question
        answer = result.answer
        retrieved_context = result.retrieved_context

        if not answer or not retrieved_context:
            # Permanent skip — missing data cannot be fixed by retrying.
            log_json(logger, logging.WARNING,
                     "RAG eval skipped — missing answer or context", eval_id=eval_id)
            await session.execute(
                update(RAGEvaluation)
                .where(RAGEvaluation.id == eval_id)
                .values(eval_status="skipped")
            )
            await session.commit()
            return

        configs = SystemConfigsRepository(session)
        eval_model = await configs.get_value("gemini_eval_model", "gemini-3-flash-preview")

    # ── 2. Run Ragas evaluation (slow — outside session scope) ───────────────
    # run_ragas_evaluation raises on catastrophic failures (auth, import errors,
    # total API outage).  arq will retry the job up to max_tries on any raise.
    try:
        scores = await run_ragas_evaluation(
            question=question,
            answer=answer,
            retrieved_context=retrieved_context,
            model_name=eval_model,
        )
    except Exception as exc:
        is_final_attempt = ctx["job_try"] >= evaluate_rag_query.max_tries
        log_json(
            logger,
            logging.ERROR if is_final_attempt else logging.WARNING,
            "RAG eval failed" + (" — no more retries" if is_final_attempt else ", will retry"),
            eval_id=eval_id,
            attempt=ctx["job_try"],
            max_tries=evaluate_rag_query.max_tries,
            error=str(exc),
        )
        if is_final_attempt:
            async with db_session.async_session_factory() as session:
                await session.execute(
                    update(RAGEvaluation)
                    .where(RAGEvaluation.id == eval_id)
                    .values(eval_status="failed")
                )
                await session.commit()
            return
        raise  # let arq schedule the retry

    # ── 3. Persist scores ─────────────────────────────────────────────────────
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(RAGEvaluation)
            .where(RAGEvaluation.id == eval_id)
            .values(
                faithfulness_score=scores.get("faithfulness_score"),
                answer_relevance_score=scores.get("answer_relevance_score"),
                eval_status="completed",
            )
        )
        await session.commit()

    log_json(
        logger, logging.INFO, "RAG eval job completed",
        eval_id=eval_id,
        **{k: v for k, v in scores.items() if v is not None},
    )


# arq checks for a max_tries attribute on the coroutine function.
# 3 attempts: immediate + 2 retries for transient Gemini/network errors.
evaluate_rag_query.max_tries = 3
