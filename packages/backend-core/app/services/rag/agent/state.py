"""AgentState — single TypedDict threaded through the LangGraph agentic RAG graph."""
from __future__ import annotations

from operator import add
from typing import Annotated, Any

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict
from typing import Optional, Any


class ToolResult(TypedDict):
    ok: bool
    data: Any
    error: Optional[str]


class AgentState(TypedDict):
    # ── Input (set once, never mutated by nodes) ──────────────────────
    ctx: Any                                     # QueryContext — not serialisable; no checkpointer in Phase 1

    # ── LangGraph-managed message list ────────────────────────────────
    messages: Annotated[list, add_messages]

    # ── Tool result accumulation (appended by execute_tool fan-out) ───
    observations: Annotated[list[dict], add]     # {"tool", "args", "result"} per call

    # ── Loop counters (set by collect_tools / agent_step) ─────────────
    total_chunks: int                            # overwritten by collect_tools
    llm_calls: Annotated[int, add]               # incremented by agent_step
    step_count: Annotated[int, add]              # incremented by agent_step

    # ── Context & grading (build_context / grade_context) ─────────────
    retrieved_context: str
    graded_context: str

    # ── Query decomposition (decompose_query node) ────────────────────
    sub_questions: list[str]             # individual questions extracted from the input; single-element if not decomposed

    # ── Final output ───────────────────────────────────────────────────
    final_answer: str
    used_book_ids: list[str]
    stop_reason: str
