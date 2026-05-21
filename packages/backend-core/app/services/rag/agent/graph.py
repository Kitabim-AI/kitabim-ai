"""LangGraph agentic RAG graph — assembles all nodes and wires edges.

Topology:
  START → decompose_query → plan_query → agent_step
  agent_step  → [execute_tool ×N  (parallel Send)]  or  build_context
  execute_tool → collect_tools
  collect_tools → [agent_step  or  build_context]
  build_context → grade_context → generate_answer → END
"""
from __future__ import annotations


from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.services.rag.agent.config import AGENT_ENOUGH_CHUNKS, AGENT_MAX_STEPS
from app.services.rag.agent.state import AgentState

# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------

def _route_after_agent_step(state: AgentState):
    """Fan-out to one execute_tool per tool call, or go straight to build_context."""
    last_msg = state["messages"][-1]
    tool_calls = getattr(last_msg, "tool_calls", None) or []

    if not tool_calls:
        return "build_context"

    return [
        Send("execute_tool", {"ctx": state["ctx"], "tool_call": tc})
        for tc in tool_calls
    ]


def _route_after_collect_tools(state: AgentState) -> str:
    if state["total_chunks"] >= AGENT_ENOUGH_CHUNKS:
        return "build_context"
    if state["step_count"] >= AGENT_MAX_STEPS:
        return "build_context"
    return "agent_step"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

_graph = None


def _build_graph():
    from app.services.rag.agent.nodes.agent_step import agent_step_node
    from app.services.rag.agent.nodes.build_context import build_context_node
    from app.services.rag.agent.nodes.collect_tools import collect_tools_node
    from app.services.rag.agent.nodes.decompose import decompose_query_node
    from app.services.rag.agent.nodes.execute_tool import execute_tool_node
    from app.services.rag.agent.nodes.generate_answer import generate_answer_node
    from app.services.rag.agent.nodes.grade_context import grade_context_node
    from app.services.rag.agent.nodes.planner import plan_query_node

    builder = StateGraph(AgentState)

    builder.add_node("decompose_query", decompose_query_node)
    builder.add_node("plan_query", plan_query_node)
    builder.add_node("agent_step", agent_step_node)
    builder.add_node("execute_tool", execute_tool_node)
    builder.add_node("collect_tools", collect_tools_node)
    builder.add_node("build_context", build_context_node)
    builder.add_node("grade_context", grade_context_node)
    builder.add_node("generate_answer", generate_answer_node)

    # Entry
    builder.add_edge(START, "decompose_query")
    builder.add_edge("decompose_query", "plan_query")
    builder.add_edge("plan_query", "agent_step")

    # ReAct fan-out: agent_step → parallel execute_tool(s) or build_context
    builder.add_conditional_edges(
        "agent_step",
        _route_after_agent_step,
        ["execute_tool", "build_context"],
    )

    # Fan-in: all execute_tool instances feed collect_tools
    builder.add_edge("execute_tool", "collect_tools")

    # After fan-in: loop or exit
    builder.add_conditional_edges(
        "collect_tools",
        _route_after_collect_tools,
        ["agent_step", "build_context"],
    )

    # Answer generation pipeline
    builder.add_edge("build_context", "grade_context")
    builder.add_edge("grade_context", "generate_answer")
    builder.add_edge("generate_answer", END)

    return builder.compile()


def get_or_build_graph():
    global _graph
    if _graph is None:
        _graph = _build_graph()
    return _graph


# ---------------------------------------------------------------------------
# Initial state helper
# ---------------------------------------------------------------------------

def _build_human_message(ctx, question: str) -> str:
    lines = []
    if not ctx.is_global and ctx.book:
        book = ctx.book
        book_info = f'"{book.title}"' if book.title else "unknown title"
        if book.author:
            book_info += f" by {book.author}"
        if book.volume is not None:
            book_info += f", volume {book.volume}"
        lines.append(f"Current book: {book_info} (book_id: {ctx.book_id})")
        if ctx.current_page is not None:
            lines.append(f"Current page: {ctx.current_page}")
    elif ctx.is_global:
        if ctx.context_book_ids:
            lines.append(f"Previous response book IDs: {', '.join(ctx.context_book_ids[:10])}")
        if ctx.character_categories:
            lines.append(f"Category filter: {', '.join(ctx.character_categories)}")
    if ctx.history:
        lines.append("Chat history: Available (contains prior conversation context)")
    if not lines:
        return question
    return "[Context]\n" + "\n".join(lines) + "\n\n[Question]\n" + question


def build_initial_state(ctx) -> AgentState:
    from langchain_core.messages import HumanMessage, SystemMessage
    from app.services.rag.agent.prompts import AGENT_SYSTEM_PROMPT

    question = ctx.enriched_question or ctx.question

    return AgentState(
        ctx=ctx,
        messages=[
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=_build_human_message(ctx, question)),
        ],
        observations=[],
        total_chunks=0,
        llm_calls=0,
        step_count=0,
        query_plan={},
        retrieved_context="",
        graded_context="",
        sub_questions=[],
        final_answer="",
        used_book_ids=[],
        stop_reason="",
    )


def populate_ctx_from_state(ctx, state: AgentState) -> None:
    """Write graph final state back into QueryContext for eval recording."""
    observations = state.get("observations", [])
    all_chunks = [
        chunk
        for obs in observations
        if obs["tool"] == "search_chunks"
        for chunk in obs["result"].get("chunks", [])
    ]

    ctx.used_book_ids = state.get("used_book_ids", [])
    ctx.retrieved_count = len(all_chunks)
    ctx.scores = [c.get("score", 0.0) for c in all_chunks]
    ctx.agent_steps = state.get("llm_calls", 0)
    ctx.agent_tools_called = [obs["tool"] for obs in observations]
    ctx.agent_retry_count = sum(1 for obs in observations if obs["tool"] == "search_chunks")

    # Count graded chunks from the final context string
    context = state.get("graded_context") or state.get("retrieved_context", "")
    ctx.agent_final_chunk_count = context.count("[BookID:")

    # Persist graded context text for Ragas evaluation
    ctx.graded_context = context

