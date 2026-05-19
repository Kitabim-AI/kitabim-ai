"""collect_tools node — fan-in after parallel execute_tool invocations.

Runs after all execute_tool nodes complete. Recomputes total_chunks from
the now-merged observations list and logs progress.
"""
from __future__ import annotations

import logging

from app.services.rag.agent.state import AgentState
from app.utils.observability import log_json

logger = logging.getLogger("app.rag.agent.nodes.collect_tools")


async def collect_tools_node(state: AgentState) -> dict:
    total_chunks = sum(
        len(obs["result"].get("chunks", []))
        for obs in state["observations"]
        if obs["tool"] == "search_chunks"
    )

    log_json(
        logger, logging.INFO, "Tool collection complete",
        step=state["step_count"],
        total_chunks=total_chunks,
        tools_called=[obs["tool"] for obs in state["observations"]],
    )

    return {"total_chunks": total_chunks}
