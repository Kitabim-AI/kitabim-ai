# LangGraph Migration Plan — Agentic RAG

> **Note:** The `self_critique` node mentioned in this plan was ultimately dropped because it did not improve quality.

## Implementation Status

**Phases 1–3 complete.** Phase 4 (Redis checkpointing) deferred. Phase 5 partial (per-node logging exists; no DB migration for per-node latency columns yet).

---

## Goals

| Goal | Mechanism |
|------|-----------|
| Better answer quality | Query planner, context grader, self-critique loop |
| Mid-loop UX (progress events) | `StreamWriter` SSE events per node |
| True parallel tool execution | LangGraph `Send` API fan-out |
| Conversation memory without re-feeding history | Redis checkpointer (deferred — Phase 4) |
| Per-node observability | Per-node latency logged to `rag_evaluations` |

---

## Current Architecture (What We're Replacing)

```
chat.py → RAGService → HandlerRegistry → AgentRAGHandler
                                               │
                                         run_agent_loop()
                                               │
                                      for step in MAX_STEPS:
                                        LLM call
                                        asyncio.gather(tool calls)
                                        if enough_chunks: break
                                               │
                                    format_observations_as_context()
                                               │
                                    generate_answer() / generate_answer_stream()
```

The agent loop is a manual message accumulation loop in `loop.py`. Streaming only starts after the loop finishes.

---

## New Architecture

```
chat.py → RAGService → HandlerRegistry → LangGraphAgentHandler
                                               │
                                    graph.astream(state, config)
                                               │
                         ┌─────────────────────┴──────────────────────────┐
                    [plan_query]                                           │
                         │                                                │
                    [agent_step] ◄─────────────────────────────────────── │
                         │                                                │
          (conditional edge: _route_after_agent_step)                     │
                ┌─────────┴─────────┐                                     │
         tool calls?           no tool calls                              │
                │                   │                                     │
    [execute_tool ×N]       [build_context]                               │
    (parallel Send API)             │                                     │
                │              [grade_context]                            │
       [collect_tools]             │                                      │
                │             [generate_answer] ◄───────────────────────┐ │
   (conditional edge)              │                                    │ │
        ┌───────┴──────┐      [self_critique]                           │ │
   enough/max       continue       │                                    │ │
        │               │    (conditional edge)                         │ │
  [build_context]  [agent_step]    │                                    │ │
                              ┌────┴────┐                               │ │
                           passed   failed (retry)                      │ │
                              │         └────────────────────────────── ┘ │
                             END                                          │
```

**Key design notes:**
- Routing from `agent_step` is a **conditional edge function** (`_route_after_agent_step`), not a separate node. There is no `route_tools` node.
- Self-critique retry routes to **`generate_answer`**, not `agent_step`. It regenerates the answer with critique feedback injected — it does not search again.
- No Redis checkpointer is used. History is still injected via `chat_history_str` in `_build_human_message()`.

---

## State Schema

```python
# packages/backend-core/app/services/rag/agent/state.py

from __future__ import annotations
from operator import add
from typing import Annotated, Any
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

class AgentState(TypedDict):
    # ── Input (set once at graph entry) ──────────────────────────────
    ctx: Any                     # QueryContext — full object; not serialisable (no checkpointer)

    # ── LangGraph-managed message history ────────────────────────────
    messages: Annotated[list, add_messages]

    # ── Accumulated retrieval data ────────────────────────────────────
    observations: Annotated[list[dict], add]   # {"tool", "args", "result"} per tool call
    total_chunks: int
    llm_calls: int
    step_count: int

    # ── Planning output ───────────────────────────────────────────────
    query_plan: dict             # {"intent", "suggested_tools", "refined_question"}

    # ── Context & grading ────────────────────────────────────────────
    retrieved_context: str
    graded_context: str          # after low-relevance chunks are filtered

    # ── Answer quality ────────────────────────────────────────────────
    draft_answer: str
    critique_passed: bool
    critique_attempts: int
    critique_feedback: str       # injected back into instructions on retry

    # ── Final output ──────────────────────────────────────────────────
    final_answer: str
    used_book_ids: list[str]
    stop_reason: str             # "no_tools" | "enough_chunks" | "max_steps" | "critique_ok"
```

**Changes from original plan:**
- `ctx_snapshot: dict` → `ctx: Any` (full `QueryContext` object, not a serialised dict; avoids Redis checkpointer requirement)
- No top-level `question: str` field — the question is read from `ctx.question` / `ctx.enriched_question`
- `stop_reason` is plain `str`, not `Literal[...]`
- `observations` uses `Annotated[list[dict], add]` so fan-out `execute_tool` nodes can append concurrently without clobbering each other

---

## Node Definitions

### 1. `plan_query` — Query Planner

**File:** `packages/backend-core/app/services/rag/agent/nodes/planner.py`

Calls a cheap fast LLM (Gemini Flash) with the question + context header. Returns:
- `intent`: one of `catalog | content_summary | content_search | current_page | follow_up`
- `suggested_tools`: ordered list of tools to try first
- `refined_question`: pronoun-resolved version if needed (replaces the `rewrite_query` cold start)

**Emits SSE event:**
```json
{"type": "planning"}
```

**Why:** The current step-by-step greedy approach commits to a tool without look-ahead. A planner lets the graph front-load the right strategy and avoids wasting steps on the wrong path.

---

### 2. `agent_step` — ReAct Step

**File:** `packages/backend-core/app/services/rag/agent/nodes/agent_step.py`

Calls the LLM with tool-calling enabled using current `state["messages"]`. Appends `AIMessage` to messages. Increments `step_count` and `llm_calls`.

**Emits SSE events:**
```json
{"type": "agent_thinking"}
{"type": "tool_call", "tool": "search_chunks"}   // one per tool call in the AIMessage
```

After this node, the conditional edge function `_route_after_agent_step` inspects the `AIMessage`:
- If no tool calls → routes to `build_context`
- If tool calls → emits one `Send("execute_tool", {"ctx": ..., "tool_call": tc})` per call (parallel fan-out)

---

### 3. `execute_tool` — Single Tool Executor (runs in parallel)

**File:** `packages/backend-core/app/services/rag/agent/nodes/execute_tool.py`

Receives `{"ctx": QueryContext, "tool_call": tc}`. Calls `dispatch_tool()`. Returns result dict appended to `observations`.

Because each `execute_tool` instance is a separate `Send` target, LangGraph runs all of them concurrently in the Pregel engine — no `asyncio.gather()` needed in application code.

**Emits SSE event on completion:**
```json
{"type": "tool_result", "found": 7}
```

---

### 4. `collect_tools` — Fan-In Aggregator

**File:** `packages/backend-core/app/services/rag/agent/nodes/collect_tools.py`

Waits for all `execute_tool` nodes to complete. Appends `ToolMessage` for each result to messages. Updates `total_chunks`.

Conditional edge `_route_after_collect_tools`:
- `total_chunks >= AGENT_ENOUGH_CHUNKS` → `build_context`
- `step_count >= AGENT_MAX_STEPS` → `build_context`
- Otherwise → `agent_step`

---

### 5. `build_context` — Observation Formatter

**File:** `packages/backend-core/app/services/rag/agent/nodes/build_context.py`

Calls existing `format_observations_as_context(observations)`. Writes `retrieved_context` and `used_book_ids` to state.

---

### 6. `grade_context` — Context Grader

**File:** `packages/backend-core/app/services/rag/agent/nodes/grade_context.py`

Scores each retrieved chunk for relevance to the question. Two-tier approach:
1. Fast keyword/embedding cosine heuristic (no LLM call) — filters obvious mismatches
2. If fewer than `MIN_CHUNKS_AFTER_GRADING` chunks survive, falls back to keeping all chunks (avoids over-filtering)

Writes `graded_context` to state.

**Emits SSE event:**
```json
{"type": "grading", "before": 12, "after": 8}
```

**Why:** Vector search returns the top-K by embedding similarity, but some chunks are only topically adjacent, not actually relevant to the specific question. Filtering them reduces hallucination risk in the final answer.

---

### 7. `generate_answer` — Answer Generator (streaming)

**File:** `packages/backend-core/app/services/rag/agent/nodes/generate_answer.py`

Calls `generate_answer_stream()` using `graded_context`. Uses `get_stream_writer()` to push each token as an SSE chunk event. Writes `draft_answer` to state.

On a critique retry, the critique feedback is available in `state["critique_feedback"]` and is injected into the generation instructions before regenerating — no additional retrieval happens.

**Emits:**
```json
{"type": "answer_start"}
{"type": "chunk", "text": "بۇ ئەسەردە..."}  // per token; translated to {"chunk": text} by chat.py
{"type": "answer_end"}
```

---

### 8. `self_critique` — Faithfulness Checker

**File:** `packages/backend-core/app/services/rag/agent/nodes/self_critique.py`

After answer generation, calls a cheap LLM with:
- The question
- The graded context
- The draft answer

Checks two things:
1. **Faithfulness** — Is every factual claim in the answer supported by a passage in the context?
2. **Relevance** — Does the answer actually address the question asked?

Returns `{"passed": bool, "feedback": str}`. Increments `critique_attempts`.

**Emits SSE event:**
```json
{"type": "critique", "passed": true}
```

Conditional edge `_route_after_self_critique`:
- `passed = True` OR `critique_attempts >= MAX_CRITIQUE_ATTEMPTS` → `END` (writes `final_answer`)
- `passed = False` → injects `critique_feedback` into state, routes back to **`generate_answer`** (NOT `agent_step`)

**Important:** On retry, the graph regenerates the answer using the existing graded context with critique feedback injected into the generation prompt. It does **not** trigger new tool calls or re-search — the context is already graded and re-retrieval would add nothing.

**Why:** This is the highest-leverage quality improvement. Hallucinations slip through when the LLM generates plausible-sounding text that isn't in any retrieved chunk. The critique node catches this before the user sees it.

**Uyghur-specific tuning:** The critique prompt evaluates faithfulness in Uyghur script and handles the case where the answer is a transliteration of content in the chunk.

---

## Graph Assembly

```python
# packages/backend-core/app/services/rag/agent/graph.py

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send

builder = StateGraph(AgentState)

# Add nodes (no route_tools node — routing is a conditional edge function)
builder.add_node("plan_query", plan_query_node)
builder.add_node("agent_step", agent_step_node)
builder.add_node("execute_tool", execute_tool_node)
builder.add_node("collect_tools", collect_tools_node)
builder.add_node("build_context", build_context_node)
builder.add_node("grade_context", grade_context_node)
builder.add_node("generate_answer", generate_answer_node)
builder.add_node("self_critique", self_critique_node)

# Entry
builder.add_edge(START, "plan_query")
builder.add_edge("plan_query", "agent_step")

# ReAct fan-out: _route_after_agent_step returns Send list or "build_context"
builder.add_conditional_edges(
    "agent_step",
    _route_after_agent_step,
    ["execute_tool", "build_context"],
)

# Fan-in: all execute_tool instances converge at collect_tools
builder.add_edge("execute_tool", "collect_tools")

# After fan-in: loop or exit
builder.add_conditional_edges(
    "collect_tools",
    _route_after_collect_tools,   # "build_context" or "agent_step"
    ["build_context", "agent_step"],
)

# Answer generation pipeline
builder.add_edge("build_context", "grade_context")
builder.add_edge("grade_context", "generate_answer")
builder.add_edge("generate_answer", "self_critique")

# Self-critique: accept or regenerate (NOT re-search — routes to generate_answer)
builder.add_conditional_edges(
    "self_critique",
    _route_after_self_critique,   # END or "generate_answer"
    [END, "generate_answer"],
)

# Compile — no checkpointer (Phase 4 deferred)
graph = builder.compile()
```

---

## Streaming Events — Full SSE Protocol

All events are emitted by nodes via `get_stream_writer()` and forwarded by `chat.py` to the client. The `chunk` event payload is translated by `chat.py` from `{"text": "..."}` to `{"chunk": "..."}` for backward compatibility.

| Event type | Payload | Emitted by |
|-----------|---------|------------|
| `planning` | `{}` | `plan_query` |
| `agent_thinking` | `{}` | `agent_step` |
| `tool_call` | `{"tool": "search_chunks"}` | `agent_step` (one per tool call) |
| `tool_result` | `{"found": 7}` | `execute_tool` |
| `grading` | `{"before": 12, "after": 8}` | `grade_context` |
| `answer_start` | `{}` | `generate_answer` |
| `chunk` | `{"text": "..."}` → `{"chunk": "..."}` | `generate_answer` (per token) |
| `answer_end` | `{}` | `generate_answer` |
| `critique` | `{"passed": bool}` | `self_critique` |
| `correction` | `{"correction": "..."}` | `chat.py` (if citation fix applied) |
| `done` | `{"usage": {...}, "contextBookIds": [...]}` | `chat.py` (stream end) |

**Frontend rendering (`AgentThinkingSteps`):**
- A fixed `AgentThinkingSteps` component renders the progress events as a step list (always `w-full` — not collapsible).
- Each tool call and result appears as a list item as events arrive.
- When a `critique` event with `passed: false` arrives, an `isRetrying` state is set, which dims the current draft answer to 40% opacity until the regenerated answer starts streaming.
- The thinking step list and the answer appear in a single unified bubble — no separate panel.

---

## Redis Checkpointing (Deferred — Phase 4)

**Status: Not implemented.** The design below is preserved as a reference for future implementation.

```python
# Future Phase 4 implementation sketch
from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from app.core.config import settings

checkpointer = AsyncRedisSaver.from_conn_string(settings.redis_url)
graph = builder.compile(checkpointer=checkpointer)
```

**Planned thread ID scheme:** `f"{user_id}:{book_id or 'global'}"` — one thread per user per book context.

**What this would replace:** The current `chat_history_str` injection in `_build_human_message()`. With checkpointing, LangGraph would maintain message history across invocations automatically. The `history` field on `QueryContext` could be phased out over time.

**Blocker:** `ctx: QueryContext` is not serialisable (it holds live DB sessions and non-JSON-able objects). Before checkpointing can be enabled, either `ctx` must be replaced with a serialisable snapshot, or the graph must be restructured to receive `ctx` outside of checkpointed state.

**New capability (when implemented):** The graph could be resumed from mid-loop state — useful for debugging (replay a specific conversation turn) and future human-in-the-loop features.

**New dependency (when implemented):** `langgraph-checkpoint-redis` — add to `packages/backend-core/requirements.txt`.

---

## Answer Quality Improvements Summary

| Improvement | Current | With LangGraph |
|-------------|---------|----------------|
| Query planning | Step-by-step greedy | Upfront intent + tool sequence plan |
| Context quality | All top-K chunks passed to LLM | Graded, filtered for relevance |
| Hallucination detection | None | Self-critique with regenerate retry |
| Tool parallelism | `asyncio.gather()` within step | Graph-level parallel via Send API |
| Conversation memory | Re-injected history string | Re-injected history string (checkpointer deferred) |
| Observability | Single eval record at end | Per-node latency logged; no DB columns yet |

---

## Files Created / Modified

### New Files

```
packages/backend-core/app/services/rag/agent/
├── state.py                  # AgentState TypedDict
├── graph.py                  # Graph assembly + compile
└── nodes/
    ├── __init__.py
    ├── planner.py             # plan_query node
    ├── agent_step.py          # agent_step node
    ├── execute_tool.py        # single tool executor (parallel Send target)
    ├── collect_tools.py       # fan-in aggregator
    ├── build_context.py       # wraps format_observations_as_context
    ├── grade_context.py       # chunk relevance grader
    ├── generate_answer.py     # streams answer via StreamWriter
    └── self_critique.py       # faithfulness + relevance check
```

Note: `route_tools.py` was not created — the fan-out routing is a conditional edge function inside `graph.py`.

### Deleted Files

| File | Reason |
|------|--------|
| `agent/loop.py` | Replaced by LangGraph graph; `_build_human_message()` moved into `graph.py` |

### Modified Files

| File | Change |
|------|--------|
| `agent/handler.py` | Replace `run_agent_loop()` call with `graph.astream()` |
| `agent/config.py` | Add `AGENT_MAX_CRITIQUE_ATTEMPTS`, `MIN_CHUNKS_AFTER_GRADING` |
| `rag_service.py` | Updated to work with graph-based handler |
| `services/backend/api/endpoints/chat.py` | Routes new SSE event types to client; translates `chunk.text` → `chunk.chunk` |
| `apps/frontend/src/components/chat/AgentThinkingSteps.tsx` | New component — renders tool progress as a step list |
| `apps/frontend/src/hooks/useChat.ts` | Handles `agent_thinking`, `tool_call`, `tool_result`, `critique` events |

---

## Implementation Phases

### Phase 1 — Core Graph (parity with current behavior) ✅ Complete
- Define `AgentState`
- Implement `agent_step`, `execute_tool`, `collect_tools`, `build_context`, `generate_answer`
- Wire graph with conditional edges
- Replace `AgentRAGHandler.handle()` and `handle_stream()` — all existing tests pass
- No new quality features; structural rewrite only

**Exit criteria met:** Structural parity achieved; graph handler live in production.

### Phase 2 — Mid-Loop Streaming ✅ Complete
- Add `StreamWriter` calls to all nodes
- Update `chat.py` to route new event types
- Update frontend to render `AgentThinkingSteps` step list
- Graceful fallback: `chunk` events still work for clients that ignore new event types

**Exit criteria met:** Users see tool progress events before answer starts streaming.

### Phase 3 — Answer Quality Nodes ✅ Complete
- Add `plan_query` node
- Add `grade_context` node
- Add `self_critique` node with regenerate retry (routes to `generate_answer`, not `agent_step`)
- Tuned prompts for Uyghur content

**Exit criteria met:** Critique loop live; self-critique retry regenerates answer rather than re-searching.

### Phase 4 — Redis Checkpointing ⏸ Deferred
- Wire `AsyncRedisSaver`
- Define thread ID scheme
- Test conversation continuity across requests
- Phase out `chat_history_str` injection

**Blocker:** `ctx: QueryContext` is not serialisable — must be restructured before checkpointing can be enabled.

**Exit criteria:** Multi-turn conversations work without re-injecting history.

### Phase 5 — Observability 🔄 Partial
- Per-node logging via `log_json()` exists
- Per-node start/end timestamps are not yet stored in `AgentState`
- No DB migration for per-node latency columns in `rag_evaluations` yet

**Exit criteria:** Each `rag_evaluations` row shows per-node latency breakdown (planner, agent steps, grading, critique).

---

## Risks & Mitigations

| Risk | Status | Mitigation |
|------|--------|-----------|
| `execute_tool` parallel fan-out increases DB connection pressure | Monitored — no issues observed | Cap concurrent tool nodes to 3; pool-aware dispatch |
| Self-critique adds 1-2s latency per turn | Resolved — using Gemini Flash | Use cheapest model (Gemini Flash) |
| Redis checkpointer adds state storage overhead | N/A — deferred | Set TTL on checkpoint keys (e.g. 24h); monitor Redis memory |
| LangGraph graph errors are harder to debug than plain Python | Resolved — `loop.py` deleted; `_build_human_message` moved into `graph.py` | Use LangGraph's built-in tracing; graph is the sole execution path |
| Critique prompt hallucinations in Uyghur | Mitigated — Uyghur-specific faithfulness examples in prompt | Seed critique prompt with Uyghur-specific faithfulness examples |
| `ctx: QueryContext` not serialisable blocks checkpointing | Active blocker for Phase 4 | Restructure ctx or extract a serialisable snapshot for Phase 4 |
