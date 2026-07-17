import os
import re
import pytest
import glob
from unittest.mock import patch
from google.adk.evaluation.agent_evaluator import AgentEvaluator
from google.adk.evaluation.base_eval_service import InferenceConfig

# Force sequential execution to prevent Gemini API rate limiting
InferenceConfig.model_fields["parallelism"].default = 1


# Custom ROUGE tokenizer that supports Uyghur/Arabic script characters
def custom_tokenize(text: str, stemmer=None) -> list[str]:
    text = text.lower()
    tokens = text.split()
    cleaned_tokens = []
    for token in tokens:
        # Keep alphanumeric characters and Uyghur/Arabic Unicode range letters
        cleaned = re.sub(r"^[^\w\u0600-\u06FF]+|[^\w\u0600-\u06FF]+$", "", token)
        if cleaned:
            cleaned_tokens.append(cleaned)
    return cleaned_tokens


async def _build_real_query_context(session, state: dict):
    """Build a production-equivalent QueryContext backed by the real local dev DB.

    Mirrors RAGService._build_context so eval tool dispatch hits real Postgres,
    but honors the eval case's explicit agent_model (RAGService normally sources
    agent_model from system_configs, which would make eval trajectories drift
    whenever that config changes).
    """
    from app.models.schemas import ChatRequest
    from app.services.rag_service import RAGService

    qc_state = state.get("query_context") or {}
    req = ChatRequest(
        book_id=qc_state.get("book_id", "global"),
        # Placeholder text only — ctx.question is never read by tool dispatch,
        # but ChatRequest.validate_question requires Arabic/Uyghur script.
        question="سوئال",
        history=qc_state.get("history", []),
        current_page=qc_state.get("current_page"),
    )
    ctx = await RAGService()._build_context(req, session, qc_state.get("user_id"))
    if qc_state.get("agent_model"):
        ctx.agent_model = qc_state["agent_model"]
    return ctx


current_dir = os.path.dirname(os.path.abspath(__file__))
cases_dir = os.path.join(current_dir, "cases")
eval_files = sorted(glob.glob(os.path.join(cases_dir, "*.test.json")))


@pytest.mark.asyncio
@pytest.mark.parametrize("eval_dataset_file", eval_files)
async def test_adk_agent_evaluation(eval_dataset_file):
    from google.adk.evaluation.evaluation_generator import EvaluationGenerator
    from google.adk.evaluation.base_eval_service import InferenceConfig
    import asyncio

    # Force sequential execution (parallelism = 1) to prevent Gemini API rate limiting
    InferenceConfig.model_fields["parallelism"].default = 1

    original_generate = EvaluationGenerator._generate_inferences_from_root_agent

    async def run_with_real_db(*args, **kwargs):
        from app.db.session import async_session_factory

        # Sleep for 4.0 seconds before running each case to prevent Gemini API rate limiting
        await asyncio.sleep(4.0)

        initial_session = kwargs.get("initial_session")
        if initial_session is None or not initial_session.state.get("query_context"):
            return await original_generate(*args, **kwargs)

        async with async_session_factory() as session:
            try:
                ctx = await _build_real_query_context(session, initial_session.state)
                initial_session.state["query_context"] = ctx
                return await original_generate(*args, **kwargs)
            finally:
                await session.rollback()

    # Patch the tokenizer and generator so we execute cleanly in Uyghur against real Postgres.
    with patch(
        "rouge_score.tokenize.tokenize",
        side_effect=custom_tokenize,
    ), patch(
        "google.adk.evaluation.evaluation_generator.EvaluationGenerator._generate_inferences_from_root_agent",
        side_effect=run_with_real_db,
    ):
        await AgentEvaluator.evaluate(
            agent_module="app.services.rag.agent",
            eval_dataset_file_path_or_dir=eval_dataset_file,
            num_runs=1,
            print_detailed_results=True,
        )
