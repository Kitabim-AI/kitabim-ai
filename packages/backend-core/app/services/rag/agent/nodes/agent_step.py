"""agent_step node — one ReAct LLM call with tools bound."""
from __future__ import annotations

import logging

from langchain_core.messages import AIMessage
from langgraph.config import get_stream_writer

from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.agent_step")


async def agent_step_node(state: AgentState) -> dict:
    from app.langchain.models import invoke_with_tools
    from app.services.rag.agent.tools import AGENT_TOOLS

    writer = get_stream_writer()
    ctx = state["ctx"]
    step = state["step_count"]

    log_json(logger, logging.INFO, "Agent step starting", step=step, model=ctx.agent_model)
    writer({"type": "agent_thinking", "step": step + 1})

    try:
        response: AIMessage = await invoke_with_tools(ctx.agent_model, state["messages"], AGENT_TOOLS)
    except Exception as exc:
        log_json(logger, logging.WARNING, "Agent LLM call failed", step=step, error=str(exc))
        # Return a no-tool-call response so the graph exits cleanly
        return {
            "messages": [AIMessage(content="", tool_calls=[])],
            "llm_calls": 1,
            "step_count": 1,
            "stop_reason": "error",
        }

    has_tools = bool(getattr(response, "tool_calls", None))
    log_json(logger, logging.INFO, "Agent step complete", step=step, has_tool_calls=has_tools)

    return {
        "messages": [response],
        "llm_calls": 1,
        "step_count": 1,
    }
