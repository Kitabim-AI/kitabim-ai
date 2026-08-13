"""LLMRoutedRAGHandler — LLM-driven ADK ReAct retrieval loop.

Unlike DeterministicRAGHandler (fixed Python precedence over a set of
extracted signals), this handler lets an LLM agent decide which tools to
call and in what order, guided by AGENT_SYSTEM_PROMPT. Both handlers use
Google ADK — this one for a free-form ReAct loop, the other as a fixed
Workflow graph — so "ADK-backed" no longer distinguishes them.

Streams custom events: planning, decompose, tool_call, answer_start, chunk, answer_end.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncIterator, Union

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.services.rag.base_handler import QueryHandler
from app.services.rag.context import QueryContext
from app.utils.observability import log_json
from app.services.chat.context_grading import (
    _build_human_message,
    _grade_context,
    _extract_used_book_ids,
)

logger = logging.getLogger("app.rag.agent.llm_routed_handler")

from app.services.rag.keywords import (
    PAGE_QUERY_PATTERNS,
)

_MAX_SUB_QUESTIONS = 4

_SPLIT_PROMPT = """\
The user sent a message that may contain multiple questions. Extract each distinct question as a self-contained string.

Rules:
- Return a JSON array of question strings (no other text).
- At most {max_q} questions.
- Each question must be self-contained — include any implicit subject from context if needed.
- Maintain standard Uyghur (Arabic script) for each extracted question.
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
    from app.llm.models import generate_text

    prompt = _SPLIT_PROMPT.format(max_q=_MAX_SUB_QUESTIONS, question=question)
    try:
        raw = await generate_text(prompt, model_name)
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            parts = json.loads(m.group())
            if isinstance(parts, list) and all(isinstance(p, str) for p in parts):
                return [p.strip() for p in parts if p.strip()][:_MAX_SUB_QUESTIONS]
    except Exception as exc:
        log_json(
            logger,
            logging.WARNING,
            "decompose LLM call failed, keeping original",
            error=str(exc),
        )
    return [question]


def _detect_intent(question: str, ctx: QueryContext) -> str:
    q = question.lower()
    if ctx.current_page is not None and any(p in q for p in PAGE_QUERY_PATTERNS):
        return "current_page"
    return "content_search"


def _populate_ctx_from_observations(
    ctx: QueryContext, observations: list[dict], graded_context: str, llm_calls: int
) -> None:
    all_chunks = [
        chunk
        for obs in observations
        if obs.get("tool") == "search_chunks"
        for chunk in (obs.get("result", {}).get("data") or obs.get("result", {})).get(
            "chunks", []
        )
    ]

    ctx.retrieved_count = len(all_chunks)
    ctx.scores = [c.get("score", 0.0) for c in all_chunks]
    ctx.agent_steps = llm_calls
    ctx.agent_tools_called = [
        obs.get("tool", "") for obs in observations if obs.get("tool")
    ]
    ctx.agent_retry_count = sum(
        1 for obs in observations if obs.get("tool") == "search_chunks"
    )
    ctx.agent_final_chunk_count = graded_context.count("[BookID:")
    ctx.graded_context = graded_context


class LLMRoutedRAGHandler(QueryHandler):
    """LLM-driven ADK ReAct RAG handler. Fallback for all unmatched intents."""

    intent_name = "llm_routed_rag"

    def can_handle(self, _ctx: QueryContext) -> bool:
        return True

    async def _execute_workflow_stream(
        self, ctx: QueryContext, question: str
    ) -> AsyncIterator[dict]:
        from app.services.rag.agent.adk_agent import build_rag_agent

        # 1. Intent Detection
        intent = _detect_intent(question, ctx)
        yield {"type": "planning", "intent": intent}

        # 2. Query Decomposition
        sub_questions = [question]
        if _question_mark_count(question) > 1 or _is_multi_entity_question(question):
            sub_questions = await _llm_split(question, ctx.agent_model)
            if len(sub_questions) > 1:
                yield {"type": "decompose", "count": len(sub_questions)}
                numbered = "\n".join(
                    f"{i + 1}. {q}" for i, q in enumerate(sub_questions)
                )
                question = question + f"\n\n[Sub-questions]\n{numbered}"

        # 3. Agent Execution
        agent = build_rag_agent(ctx.agent_model)
        runner = InMemoryRunner(agent=agent, app_name="kitabim")
        session = await runner.session_service.create_session(
            app_name="kitabim",
            user_id=ctx.user_id or "anon",
            state={"query_context": ctx, "observations": []},
        )

        human_msg = _build_human_message(ctx, question)
        content = types.Content(
            role="user", parts=[types.Part.from_text(text=human_msg)]
        )

        # Collect observations inline from the event stream — more reliable than reading
        # session.state after the run, which ADK's InMemoryRunner does not always persist.
        inline_observations: list[dict] = []
        pending_calls: dict[str, str] = {}  # call_id → tool_name

        from google.adk.agents.run_config import RunConfig, StreamingMode

        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=content,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        ):
            # 1. Yield tool calls (only on final non-partial events to prevent duplicates)
            if not event.partial and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.function_call:
                        call_id = (
                            getattr(part.function_call, "id", None)
                            or part.function_call.name
                        )
                        pending_calls[call_id] = part.function_call.name
                        yield {
                            "type": "tool_call",
                            "tool": part.function_call.name,
                            "name": part.function_call.name,
                        }

            # 2. Yield agent thinking traces (only on final events to prevent duplicates)
            if not event.partial and event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        yield {"type": "agent_thinking", "text": part.text}

            # 3. Collect observations and yield tool results
            function_responses = event.get_function_responses()
            if function_responses:
                for fr in function_responses:
                    response_data = fr.response or {}
                    call_id = getattr(fr, "id", None) or fr.name
                    tool_name = pending_calls.pop(call_id, fr.name)
                    inline_observations.append(
                        {
                            "tool": tool_name,
                            "result": response_data,
                        }
                    )
                    found = (
                        response_data.get("found_count", 0)
                        if isinstance(response_data, dict)
                        else 0
                    )
                    yield {
                        "type": "tool_result",
                        "tool": tool_name,
                        "found": found,
                    }

        # 4. Context & Grading post-processing using inline observations
        observations = inline_observations

        # Finding 8 - Minimal extraction of used book IDs
        used_book_ids = _extract_used_book_ids(observations)
        ctx.used_book_ids = used_book_ids

        # Finding 8 - unified context grading
        graded_context, before_count, after_count = _grade_context(observations)

        # Count actual agent steps (number of tool calls / observations)
        llm_calls = len(observations)

        _populate_ctx_from_observations(ctx, observations, graded_context, llm_calls)

        yield {
            "type": "result",
            "sub_questions": sub_questions,
            "observations": observations,
            "llm_calls": llm_calls,
            "graded_context": graded_context,
            "before_count": before_count,
            "after_count": after_count,
        }

    async def handle(self, ctx: QueryContext) -> str:
        from app.utils.citation_fixer import fix_malformed_citations
        from app.services.rag.answer_builder import generate_answer_stream

        log_json(
            logger,
            logging.INFO,
            "LLM-routed RAG handler invoked (non-stream)",
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
                "LLM-routed RAG handler yielded no result events — using empty-context fallback",
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
            logger,
            logging.INFO,
            "LLM-routed RAG handler invoked (stream)",
            model=ctx.agent_model,
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
                "LLM-routed RAG handler yielded no result events — using empty-context fallback",
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
