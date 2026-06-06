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
    ctx = state.get("ctx")
    enough_chunks = getattr(ctx, "agent_enough_chunks", AGENT_ENOUGH_CHUNKS)
    max_steps = getattr(ctx, "agent_max_steps", AGENT_MAX_STEPS)

    if state["total_chunks"] >= enough_chunks:
        return "build_context"
    if state["step_count"] >= max_steps:
        return "build_context"
    return "agent_step"


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def wrap_node_with_request_id(node_func):
    import functools
    from app.utils.observability import request_id_var

    @functools.wraps(node_func)
    async def wrapper(state, *args, **kwargs):
        ctx = None
        if isinstance(state, dict):
            ctx = state.get("ctx")
        elif hasattr(state, "ctx"):
            ctx = state.ctx

        token = None
        if ctx and hasattr(ctx, "request_id") and ctx.request_id:
            token = request_id_var.set(ctx.request_id)
        try:
            return await node_func(state, *args, **kwargs)
        finally:
            if token:
                request_id_var.reset(token)

    return wrapper


def _build_graph():
    from app.services.rag.agent.nodes.agent_step_node import agent_step_node
    from app.services.rag.agent.nodes.build_context_node import build_context_node
    from app.services.rag.agent.nodes.collect_tools_node import collect_tools_node
    from app.services.rag.agent.nodes.decompose_node import decompose_query_node
    from app.services.rag.agent.nodes.execute_tool_node import execute_tool_node
    from app.services.rag.agent.nodes.generate_answer_node import generate_answer_node
    from app.services.rag.agent.nodes.grade_context_node import grade_context_node
    from app.services.rag.agent.nodes.planner_node import plan_query_node

    builder = StateGraph(AgentState)

    builder.add_node("decompose_query", wrap_node_with_request_id(decompose_query_node))
    builder.add_node("plan_query", wrap_node_with_request_id(plan_query_node))
    builder.add_node("agent_step", wrap_node_with_request_id(agent_step_node))
    builder.add_node("execute_tool", wrap_node_with_request_id(execute_tool_node))
    builder.add_node("collect_tools", wrap_node_with_request_id(collect_tools_node))
    builder.add_node("build_context", wrap_node_with_request_id(build_context_node))
    builder.add_node("grade_context", wrap_node_with_request_id(grade_context_node))
    builder.add_node("generate_answer", wrap_node_with_request_id(generate_answer_node))

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


_graph = None


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
        graph_available = getattr(book, "graph_milestone", None) == "complete"
        lines.append(f"Graph available: {'yes' if graph_available else 'no'}")
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
        if obs["tool"] == "search_chunks" and obs["result"].get("ok", True)
        for chunk in (obs["result"].get("data") or obs["result"]).get("chunks", [])
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

