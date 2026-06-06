"""execute_tool node — runs a single tool call.

Invoked in parallel for each tool call via LangGraph Send API.
Each invocation appends one observation and one ToolMessage to the parent state.
"""
from __future__ import annotations

import json
import logging

from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer

from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.execute_tool")


async def execute_tool_node(state: dict) -> dict:
    """state contains: ctx, tool_call (a LangChain tool call dict)."""
    from app.services.rag.agent.tools import dispatch_tool

    writer = get_stream_writer()
    ctx = state["ctx"]
    tc: dict = state["tool_call"]

    tool_name: str = tc["name"]
    tool_args: dict = tc.get("args", {})
    tool_call_id: str = tc.get("id", f"call_{tool_name}")

    log_json(logger, logging.INFO, "Executing tool", tool=tool_name)
    writer({"type": "tool_call", "tool": tool_name, "args": tool_args})

    result = await dispatch_tool(tool_name, tool_args, ctx)

    found_count = 0
    if result.get("ok", True):
        data = result.get("data") or result
        if isinstance(data, dict):
            found_count = data.get("found_count", 0)

    log_json(logger, logging.INFO, "Tool executed", tool=tool_name, found=found_count)
    if not result.get("ok", True):
        writer({"type": "error", "code": "tool_failure", "recoverable": True})
    writer({"type": "tool_result", "tool": tool_name, "found": found_count})

    obs = {"tool": tool_name, "args": tool_args, "result": result}
    tool_msg = ToolMessage(
        content=json.dumps(result, ensure_ascii=False),
        tool_call_id=tool_call_id,
    )

    return {
        "observations": [obs],
        "messages": [tool_msg],
    }
