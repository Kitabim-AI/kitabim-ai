import os
import re
import pytest
import glob
import uuid
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


async def _build_real_query_context(session, state: dict, query: str):
    """Build a production-equivalent QueryContext backed by the real local dev DB.

    Mirrors RAGService._build_context so eval tool dispatch hits real Postgres,
    but forces deterministic router configuration.
    """
    from app.models.schemas import ChatRequest
    from app.services.rag_service import RAGService

    qc_state = state.get("query_context") or {}
    req = ChatRequest(
        book_id=qc_state.get("book_id", "global"),
        question=query,
        history=qc_state.get("history", []),
        current_page=qc_state.get("current_page"),
    )
    ctx = await RAGService()._build_context(req, session, qc_state.get("user_id"))
    ctx.use_deterministic_router = True
    if qc_state.get("agent_model"):
        ctx.agent_model = qc_state["agent_model"]
    return ctx


current_dir = os.path.dirname(os.path.abspath(__file__))
cases_dir = os.path.join(current_dir, "cases")
eval_files = sorted(glob.glob(os.path.join(cases_dir, "*.test.json")))


@pytest.mark.asyncio
@pytest.mark.parametrize("eval_dataset_file", eval_files)
async def test_deterministic_evaluation(eval_dataset_file):
    from google.adk.evaluation.base_eval_service import InferenceConfig
    import asyncio

    # Force sequential execution (parallelism = 1) to prevent Gemini API rate limiting
    InferenceConfig.model_fields["parallelism"].default = 1

    async def run_deterministic_qa(*args, **kwargs):
        from app.db.session import async_session_factory

        # Sleep for 4.0 seconds before running each case to prevent Gemini API rate limiting
        await asyncio.sleep(4.0)

        user_simulator = kwargs.get("user_simulator") or args[1]
        initial_session = kwargs.get("initial_session") or (
            args[3] if len(args) > 3 else None
        )

        if initial_session is None or not initial_session.state.get("query_context"):
            raise ValueError("Evaluation session input must contain query_context")

        # Extract query from simulator
        next_user_message = await user_simulator.get_next_user_message([])
        if not next_user_message or not next_user_message.user_message:
            return []
        query = next_user_message.user_message.parts[0].text

        async with async_session_factory() as session:
            try:
                # Build context
                ctx = await _build_real_query_context(
                    session, initial_session.state, query
                )

                # Execute deterministic handler
                from app.services.rag.agent.deterministic_handler import (
                    DeterministicRAGHandler,
                )

                handler = DeterministicRAGHandler()

                observations = []
                sub_questions = None
                graded_context = None

                # Execute workflow
                async for event in handler._execute_workflow_stream(
                    ctx, query, observations
                ):
                    if event.get("type") == "result":
                        sub_questions = event["sub_questions"]
                        graded_context = event["graded_context"]

                if graded_context is None or sub_questions is None:
                    graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
                    sub_questions = [query]

                final_question = (
                    "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
                    if len(sub_questions) > 1
                    else (ctx.enriched_question or ctx.question)
                )

                # Generate answer
                from app.services.rag.answer_builder import generate_answer_stream

                answer_chunks = []
                async for token in generate_answer_stream(
                    graded_context,
                    final_question,
                    ctx.rag_chain,
                    chat_history=ctx.chat_history_str,
                    persona_prompt=ctx.persona_prompt,
                    is_global=ctx.is_global,
                    has_categories=bool(ctx.character_categories),
                ):
                    answer_chunks.append(token)

                from app.utils.citation_fixer import fix_malformed_citations

                answer = fix_malformed_citations("".join(answer_chunks))

                # Format for ADK Invocation
                from google.genai import types as genai_types
                from google.adk.evaluation.eval_case import IntermediateData
                from google.adk.evaluation.eval_metrics import Invocation

                tool_uses = []
                tool_responses = []
                for obs in observations:
                    tool_uses.append(
                        genai_types.FunctionCall(name=obs["tool"], args=obs["args"])
                    )
                    tool_responses.append(
                        genai_types.FunctionResponse(
                            name=obs["tool"], response=obs["result"]
                        )
                    )

                intermediate_data = IntermediateData(
                    tool_uses=tool_uses, tool_responses=tool_responses
                )

                final_response = genai_types.Content(
                    role="model", parts=[genai_types.Part.from_text(text=answer)]
                )

                invocation = Invocation(
                    invocation_id=str(uuid.uuid4()),
                    user_content=genai_types.Content(
                        role="user", parts=[genai_types.Part.from_text(text=query)]
                    ),
                    final_response=final_response,
                    intermediate_data=intermediate_data,
                )

                return [invocation]
            finally:
                await session.rollback()

    # Patch the tokenizer and generator so we execute cleanly in Uyghur against real Postgres.
    with patch(
        "rouge_score.tokenize.tokenize",
        side_effect=custom_tokenize,
    ), patch(
        "google.adk.evaluation.evaluation_generator.EvaluationGenerator._generate_inferences_from_root_agent",
        side_effect=run_deterministic_qa,
    ):
        await AgentEvaluator.evaluate(
            agent_module="app.services.rag.agent",
            eval_dataset_file_path_or_dir=eval_dataset_file,
            num_runs=1,
            print_detailed_results=True,
        )
