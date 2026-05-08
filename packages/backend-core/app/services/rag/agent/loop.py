"""ReAct loop — runs the agent, collects tool observations, returns them for answer generation."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import List, Tuple

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.services.rag.agent.prompts import AGENT_SYSTEM_PROMPT
from app.services.rag.agent.tools import AGENT_TOOLS, dispatch_tool
from app.services.rag.context import QueryContext
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.loop")

MAX_STEPS = 4
_ENOUGH_CHUNKS = 8


async def run_agent_loop(ctx: QueryContext, agent_model_name: str) -> Tuple[List[dict], int]:
    """Drive the ReAct loop and return accumulated observations.

    Each observation is a dict: {"tool": str, "args": dict, "result": dict}.
    The loop stops when the LLM makes a response with no tool calls, when it has
    collected enough chunks, or when MAX_STEPS is reached.
    """
    from app.langchain.models import invoke_with_tools

    question = ctx.enriched_question or ctx.question
    messages = [
        SystemMessage(content=AGENT_SYSTEM_PROMPT),
        HumanMessage(content=question),
    ]

    observations: List[dict] = []
    llm_calls = 0

    for step in range(MAX_STEPS):
        log_json(logger, logging.INFO, "Agent LLM call starting", step=step, model=agent_model_name)
        try:
            response: AIMessage = await invoke_with_tools(agent_model_name, messages, AGENT_TOOLS)
        except Exception as exc:
            log_json(logger, logging.WARNING, "Agent LLM call failed", step=step, error=str(exc))
            break
        llm_calls += 1
        log_json(logger, logging.INFO, "Agent LLM call returned", step=step, has_tool_calls=bool(getattr(response, "tool_calls", None)))

        if not getattr(response, "tool_calls", None):
            log_json(logger, logging.INFO, "Agent loop ended — no tool calls", step=step)
            break

        messages.append(response)

        tool_calls = response.tool_calls
        results = await asyncio.gather(*[
            dispatch_tool(tc["name"], tc.get("args", {}), ctx)
            for tc in tool_calls
        ])

        for tc, result in zip(tool_calls, results):
            tool_name: str = tc["name"]
            tool_args: dict = tc.get("args", {})
            tool_call_id: str = tc.get("id", f"call_{step}")
            observations.append({"tool": tool_name, "args": tool_args, "result": result})
            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_call_id,
                )
            )

        total_chunks = _count_chunks(observations)
        log_json(
            logger, logging.INFO, "Agent loop step complete",
            step=step + 1, total_chunks=total_chunks,
            tools_called=[o["tool"] for o in observations],
        )

        if total_chunks >= _ENOUGH_CHUNKS:
            log_json(logger, logging.INFO, "Agent loop ended — enough chunks collected", total_chunks=total_chunks)
            break

    return observations, llm_calls


def _count_chunks(observations: List[dict]) -> int:
    return sum(
        len(o["result"].get("chunks", []))
        for o in observations
        if o["tool"] == "search_chunks"
    )
