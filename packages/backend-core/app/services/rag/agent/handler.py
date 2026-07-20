"""AgentRAGHandler — Google ADK-backed agentic RAG.

Streams custom events: planning, decompose, tool_call, answer_start, chunk, answer_end.

The retrieval workflow is now fully owned by ``graph_agent.run_graph_workflow_stream``
— this class is a thin adapter that delegates to it.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Union

from app.services.rag.agent.graph_agent import run_graph_workflow_stream
from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.handler")


class AgentRAGHandler(QueryHandler):
    """Google ADK agentic RAG handler. Fallback for all unmatched intents."""

    intent_name = "agent_rag"

    def can_handle(self, _ctx: QueryContext) -> bool:
        return True

    async def _execute_workflow_stream(
        self, ctx: QueryContext, question: str
    ) -> AsyncIterator[dict]:
        """Delegate to the graph-based deterministic workflow in graph_agent."""
        async for event in run_graph_workflow_stream(ctx, question):
            yield event

    async def handle(self, ctx: QueryContext) -> str:
        from app.utils.citation_fixer import fix_malformed_citations
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(
            logger,
            logging.INFO,
            "ADK agent invoked (non-stream)",
            model=ctx.agent_model,
        )

        question = ctx.enriched_question or ctx.question

        sub_questions = None
        graded_context = None

        async for event in self._execute_workflow_stream(ctx, question):
            if event.get("type") == "result":
                sub_questions = event["sub_questions"]
                graded_context = event["graded_context"]

        if graded_context is None or sub_questions is None:
            log_json(
                logger,
                logging.WARNING,
                "ADK agent yielded no result events — using empty-context fallback",
            )
            graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            sub_questions = [question]

        # 5. Generate Answer
        final_question = (
            "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            if len(sub_questions) > 1
            else (ctx.enriched_question or ctx.question)
        )

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

        answer = "".join(answer_chunks)
        return fix_malformed_citations(answer)

    async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[Union[str, dict]]:
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(
            logger, logging.INFO, "ADK agent invoked (stream)", model=ctx.agent_model
        )

        question = ctx.enriched_question or ctx.question

        sub_questions = None
        graded_context = None
        before_count = 0
        after_count = 0

        async for event in self._execute_workflow_stream(ctx, question):
            if event.get("type") == "result":
                sub_questions = event["sub_questions"]
                graded_context = event["graded_context"]
                before_count = event.get("before_count", 0)
                after_count = event.get("after_count", 0)
            else:
                yield event

        if graded_context is None or sub_questions is None:
            log_json(
                logger,
                logging.WARNING,
                "ADK agent yielded no result events — using empty-context fallback",
            )
            graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
            sub_questions = [question]

        if before_count > 0:
            yield {"type": "grading", "before": before_count, "after": after_count}

        # 5. Generate Answer
        final_question = (
            "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            if len(sub_questions) > 1
            else (ctx.enriched_question or ctx.question)
        )

        yield {"type": "answer_start"}
        async for token in generate_answer_stream(
            graded_context,
            final_question,
            ctx.rag_chain,
            chat_history=ctx.chat_history_str,
            persona_prompt=ctx.persona_prompt,
            is_global=ctx.is_global,
            has_categories=bool(ctx.character_categories),
        ):
            yield {"type": "chunk", "text": token}
        yield {"type": "answer_end"}
