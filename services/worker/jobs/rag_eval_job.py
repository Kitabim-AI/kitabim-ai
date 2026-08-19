"""rag_eval_job — async LLM-judge scoring of a single RAG chat turn.

Enqueued by ChatOrchestrator right after a chat turn is persisted (not a
pipeline/cron job — no page milestones, no BookMilestoneService involved).
"""

import logging

from app.db import session as db_session
from app.db.repositories.rag_evaluations_repository import RAGEvaluationsRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.rag.judge import score_answer
from app.utils.observability import log_json

logger = logging.getLogger("app.worker.rag_eval_job")


async def rag_eval_job(ctx: dict, eval_id: int) -> None:
    """Score a single rag_evaluations row. Single-attempt: on failure, mark the
    row 'failed' and do not re-raise — a stale eval_status is a fine outcome
    for a best-effort quality signal, arq retries would just add noise."""
    log_json(logger, logging.INFO, "rag_eval_job started", eval_id=eval_id)

    async with db_session.async_session_factory() as session:
        repo = RAGEvaluationsRepository(session)
        row = await repo.get(eval_id)
        if not row:
            log_json(
                logger,
                logging.WARNING,
                "rag_evaluations row not found",
                eval_id=eval_id,
            )
            return

        config_repo = SystemConfigsRepository(session)
        model = await config_repo.get_value(
            "rag_gemini_judge_model", "gemini-3.1-flash-lite"
        )

        try:
            scores = await score_answer(
                question=row.question,
                answer=row.answer or "",
                context=row.retrieved_context or "",
                model=model,
            )
            await repo.update_one(
                eval_id,
                faithfulness_score=scores.faithfulness,
                answer_relevance_score=scores.answer_relevance,
                context_precision_score=scores.context_precision,
                eval_status="completed",
            )
            await session.commit()
            log_json(logger, logging.INFO, "rag_eval_job completed", eval_id=eval_id)
        except Exception as exc:
            await repo.update_one(eval_id, eval_status="failed")
            await session.commit()
            log_json(
                logger,
                logging.ERROR,
                "rag_eval_job failed",
                eval_id=eval_id,
                error=str(exc)[:500],
            )
