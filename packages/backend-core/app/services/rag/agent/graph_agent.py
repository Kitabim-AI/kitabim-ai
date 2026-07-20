"""Graph-based deterministic RAG workflow using ADK 2.x InMemoryRunner.

This module provides ``run_graph_workflow_stream`` — an async generator that
implements the five-stage deterministic graph:

  Node 1: Intent Detection  (→ planning event)
  Node 2: Question Decomposition  (→ decompose event if split)
  Node 3: Agent Execution  (→ tool_call / agent_thinking / tool_result events)
  Node 4: Observation Collection  (accumulated inline during Node 3)
  Node 5: Context Grading  (→ result event)

The function is designed to be the single source of truth for the retrieval
workflow. Both ``AgentRAGHandler.handle`` and ``AgentRAGHandler.handle_stream``
delegate to this generator.

Exports:
    run_graph_workflow_stream  — the main entry point
    _llm_split_question        — exposed for mocking in tests
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, AsyncIterator

from google.adk.runners import InMemoryRunner
from google.genai import types

from app.services.rag.agent.graph_nodes import (
    build_human_message,
    decompose_question,
    extract_used_book_ids,
    grade_context,
    is_graph_enabled,
    populate_ctx_from_observations,
)
from app.utils.observability import log_json

if TYPE_CHECKING:
    from app.services.rag.context import QueryContext

logger = logging.getLogger("app.rag.agent.graph_agent")

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


async def _llm_split_question(question: str, model_name: str) -> list[str]:
    """Call an LLM to split a compound question into sub-questions.

    Exposed at module level (not as a nested function) so tests can patch it.
    Returns the original question in a single-element list on any failure.
    """
    from app.llm.models import generate_text

    prompt = _SPLIT_PROMPT.format(max_q=_MAX_SUB_QUESTIONS, question=question)
    try:
        raw = await generate_text(prompt, model_name)
        m = re.search(r"\[.*?\]", raw, re.DOTALL)
        if m:
            parts = json.loads(m.group())
            if isinstance(parts, list) and all(isinstance(p, str) for p in parts):
                return [p.strip() for p in parts if p.strip()][:_MAX_SUB_QUESTIONS]
    except Exception as exc:  # noqa: BLE001 — best-effort LLM call
        log_json(
            logger,
            logging.WARNING,
            "decompose LLM call failed, keeping original",
            error=str(exc),
        )
    return [question]


async def run_graph_workflow_stream(
    ctx: "QueryContext",
    question: str,
) -> AsyncIterator[dict]:
    """Execute the five-stage deterministic RAG graph and yield typed events.

    Stage 1 — Intent Detection:
        Immediately yields {"type": "planning", "intent": <str>}

    Stage 2 — Question Decomposition:
        If heuristics detect multiple questions, calls ``_llm_split_question``
        and yields {"type": "decompose", "count": <int>} when > 1 sub-questions.

    Stage 3 + 4 — ADK Agent Execution + Observation Collection:
        Runs the ADK LlmAgent (ReAct) as a sub-agent using InMemoryRunner.
        Yields {"type": "tool_call", ...}, {"type": "agent_thinking", ...},
        and {"type": "tool_result", ...} events inline.

    Stage 5 — Context Grading:
        Grades and deduplicates retrieved chunks from accumulated observations.
        Populates ctx eval fields and yields the final result dict.

    Args:
        ctx:       QueryContext carrying session state (mutated in place).
        question:  The current user question (pre-enriched if applicable).

    Yields:
        dicts with a "type" key; callers must handle:
        - "planning"       (intent: str)
        - "decompose"      (count: int)
        - "tool_call"      (tool: str, name: str)
        - "agent_thinking" (text: str)
        - "tool_result"    (tool: str, found: int)
        - "result"         (graded_context, sub_questions, observations,
                            before_count, after_count, llm_calls)
    """
    from app.services.rag.agent.adk_agent import build_rag_agent

    # -------------------------------------------------------------------------
    # Node 1: Intent Detection
    # -------------------------------------------------------------------------
    from app.services.rag.agent.graph_nodes import detect_intent

    intent = detect_intent(question, ctx)
    yield {"type": "planning", "intent": intent}

    # -------------------------------------------------------------------------
    # Node 2: Question Decomposition
    # -------------------------------------------------------------------------
    sub_questions = [question]
    _, should_split = decompose_question(question)
    if should_split:
        candidates = await _llm_split_question(question, ctx.agent_model)
        if len(candidates) > 1:
            sub_questions = candidates
            yield {"type": "decompose", "count": len(sub_questions)}
            numbered = "\n".join(f"{i + 1}. {q}" for i, q in enumerate(sub_questions))
            question = question + f"\n\n[Sub-questions]\n{numbered}"

    # -------------------------------------------------------------------------
    # Node 3: ADK Agent Execution
    # -------------------------------------------------------------------------
    agent = build_rag_agent(ctx.agent_model, graph_enabled=is_graph_enabled(ctx))
    runner = InMemoryRunner(agent=agent, app_name="kitabim")
    session = await runner.session_service.create_session(
        app_name="kitabim",
        user_id=ctx.user_id or "anon",
        state={"query_context": ctx, "observations": []},
    )

    human_msg = build_human_message(ctx, question)
    content = types.Content(role="user", parts=[types.Part.from_text(text=human_msg)])

    # -------------------------------------------------------------------------
    # Node 4: Observation Collection — accumulated inline from the event stream
    # -------------------------------------------------------------------------
    inline_observations: list[dict] = []
    pending_calls: dict[str, str] = {}  # call_id → tool_name

    async for event in runner.run_async(
        user_id=session.user_id, session_id=session.id, new_message=content
    ):
        # Yield tool calls (only on final non-partial events to prevent dupes)
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

        # Yield agent thinking traces (only on final events to prevent dupes)
        if not event.partial and event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    yield {"type": "agent_thinking", "text": part.text}

        # Collect observations and yield tool results
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

    # -------------------------------------------------------------------------
    # Node 5: Context Grading
    # -------------------------------------------------------------------------
    observations = inline_observations

    used_book_ids = extract_used_book_ids(observations)
    ctx.used_book_ids = used_book_ids

    graded_context, before_count, after_count = grade_context(observations)
    llm_calls = len(observations)

    populate_ctx_from_observations(ctx, observations, graded_context, llm_calls)

    yield {
        "type": "result",
        "sub_questions": sub_questions,
        "observations": observations,
        "llm_calls": llm_calls,
        "graded_context": graded_context,
        "before_count": before_count,
        "after_count": after_count,
    }
