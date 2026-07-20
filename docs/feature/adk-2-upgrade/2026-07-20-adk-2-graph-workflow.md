# ADK 2.0 Upgrade & Graph-Based RAG Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade `google-adk` from 2.4.0 to >=2.5.0 and rewrite the `AgentRAGHandler` question-answering workflow as a graph-based deterministic pipeline using ADK 2.0's `BaseAgent` + `_run_async_impl` pattern.

**Architecture:** Replace the current monolithic `_execute_workflow_stream` method (which mixes intent detection, ADK event parsing, and context grading inline) with explicit graph nodes: `intent_detect → query_decompose → retrieval_loop (ADK sub-agent) → context_grade`. Pure-Python nodes live in `graph_nodes.py` (testable without LLM). The ADK `Agent` (ReAct) is retained as a sub-agent for tool-calling inside the retrieval loop, but the outer graph controls flow deterministically. `DeterministicRAGHandler` and `registry.py` are untouched.

**Tech Stack:** `google-adk>=2.5.0`, Python 3.11+, FastAPI, SQLAlchemy async, Gemini genai SDK

## Global Constraints

- Branch: `feature/adk-2-upgrade`
- Shared business logic → `packages/backend-core/app/` only
- Existing tool implementations in `tools.py` are reused — no new retrieval logic
- Keep `rag_service.py` public API (`answer_question`, `answer_question_stream`) unchanged
- Keep `DeterministicRAGHandler` unchanged; graph handler replaces `AgentRAGHandler` only
- Tests go in `packages/backend-core/tests/`; use `pytest-asyncio`
- After code changes, rebuild via `./deploy/local/rebuild-and-restart.sh backend`
- No placeholders or TODO stubs in final committed code

---

## Background

### Current Architecture Problems

[`handler.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/handler.py) `AgentRAGHandler`:
- Creates `Agent` (ReAct) via [`adk_agent.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/adk_agent.py) `build_rag_agent()`
- Runs it through `InMemoryRunner.run_async()`, parsing raw ADK events inline
- Problem: broad `except Exception` in [`tools.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/tools.py) swallows ADK 2.x framework signals like `NodeInterruptedError`
- Problem: `_grade_context`, `_extract_used_book_ids`, `_detect_intent`, `_build_human_message` are private to `handler.py` and imported by [`deterministic_handler.py`](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/deterministic_handler.py), creating tight coupling
- Problem: non-deterministic — LLM chooses tool call order in ReAct loop

### ADK 2.0 Key Changes

- **`_run_async_impl`** is the canonical custom agent entry point (AsyncGenerator[Event, None])
- **Exception handling**: broad `except Exception` can trap ADK framework signals — narrow to specific recoverable exceptions
- **Python `Workflow` DSL** is still evolving in 2.x; we use `BaseAgent._run_async_impl` pattern instead
- **`InMemoryRunner` API** is stable — `run_async()` stream unchanged
- Latest stable: **2.5.0** (project currently pins 2.4.0)

### New Graph Workflow Design

```
START
  │
  ▼
[Node 1: intent_detect]    — pure Python, keyword match → "current_page" | "content_search"
  │
  ▼
[Node 2: query_decompose]  — heuristic + optional LLM split on multi-question
  │
  ▼
[Node 4: retrieval_loop]   — ADK sub-agent (LlmAgent + tools); outer loop is deterministic
  │
  ▼
[Node 5: context_grade]    — pure Python scoring & dedup
  │
  ▼
[Node 6: answer_generate]  — streamed via ProtectedLLM (done in handler, not here)
```

---

## File Map

| Status | File | Change |
|--------|------|--------|
| Modify | `services/backend/requirements.txt` | Bump adk version |
| Modify | `services/worker/requirements.txt` | Bump adk version (if present) |
| Create | `packages/backend-core/app/services/rag/agent/graph_nodes.py` | Pure-Python node functions |
| Create | `packages/backend-core/app/services/rag/agent/graph_agent.py` | Graph workflow orchestrator |
| Modify | `packages/backend-core/app/services/rag/agent/handler.py` | Delegate to graph_agent |
| Modify | `packages/backend-core/app/services/rag/agent/tools.py` | Narrow exception handling |
| Modify | `packages/backend-core/app/services/rag/agent/deterministic_handler.py` | Fix imports |
| Create | `packages/backend-core/tests/__init__.py` | Empty init |
| Create | `packages/backend-core/tests/test_adk_version.py` | Version check test |
| Create | `packages/backend-core/tests/test_tools_exception_handling.py` | Exception fix test |
| Create | `packages/backend-core/tests/test_graph_nodes.py` | Node unit tests |
| Create | `packages/backend-core/tests/test_graph_agent.py` | Workflow integration tests |
| Create | `packages/backend-core/tests/test_agent_rag_handler.py` | Handler wiring tests |

---

## Verification Plan

### Automated Tests
```bash
source .venv/bin/activate
pytest packages/backend-core/tests/ -v
```

### Manual Verification
1. `./deploy/local/rebuild-and-restart.sh backend`
2. `docker compose logs --tail=50 backend` — no import errors
3. Send streaming chat request; verify SSE events: `planning` → `tool_call*` → `tool_result*` → `grading` → `answer_start` → `chunk*` → `answer_end`
4. Verify `DeterministicRAGHandler` still routes correctly with `use_deterministic_router=true`

---

## Task 1: Upgrade ADK Version

**Files:**
- Modify: `services/backend/requirements.txt:11`
- Modify: `services/worker/requirements.txt` (check first)

**Interfaces:**
- Consumes: nothing
- Produces: `google-adk>=2.5.0,<3.0.0` available in Docker images

- [ ] **Step 1: Check worker requirements**

  ```bash
  grep -n "google-adk" services/worker/requirements.txt || echo "not present"
  ```

- [ ] **Step 2: Write test (import + version check)**

  Create `packages/backend-core/tests/__init__.py` (empty) and:

  ```python
  # packages/backend-core/tests/test_adk_version.py
  import importlib.metadata

  def test_adk_version_is_2x():
      version = importlib.metadata.version("google-adk")
      major = int(version.split(".")[0])
      assert major == 2, f"Expected major version 2, got {version}"

  def test_adk_agents_importable():
      from google.adk.agents import Agent, BaseAgent  # noqa: F401
      from google.adk.runners import InMemoryRunner  # noqa: F401
  ```

- [ ] **Step 3: Run test to verify baseline**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_adk_version.py -v
  ```
  Expected: PASS (already on 2.x).

- [ ] **Step 4: Bump version in `services/backend/requirements.txt`**

  ```diff
  -google-adk[gcp]==2.4.0
  +google-adk[gcp]>=2.5.0,<3.0.0
  ```

- [ ] **Step 5: Bump in worker if present; skip otherwise**

- [ ] **Step 6: Commit**

  ```bash
  git add services/backend/requirements.txt services/worker/requirements.txt \
    packages/backend-core/tests/__init__.py packages/backend-core/tests/test_adk_version.py
  git commit -m "chore: bump google-adk to >=2.5.0,<3.0.0"
  ```

---

## Task 2: Fix Broad Exception Handling in Tools

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/tools.py` lines 35–79

**Interfaces:**
- Consumes: existing `_dispatch_tool_with_retry(tool_name, tool_args, ctx)`
- Produces: `_execute_and_record_tool` now re-raises non-recoverable exceptions (KeyboardInterrupt, etc.)

- [ ] **Step 1: Write the failing test**

  ```python
  # packages/backend-core/tests/test_tools_exception_handling.py
  import pytest
  from unittest.mock import MagicMock, patch

  class _FakeContext:
      def __init__(self):
          self.state = {"query_context": MagicMock(), "observations": []}

  @pytest.mark.asyncio
  async def test_execute_and_record_tool_reraises_keyboard_interrupt():
      from app.services.rag.agent.tools import _execute_and_record_tool

      async def _raise_ki(*args, **kwargs):
          raise KeyboardInterrupt("stop")

      with patch("app.services.rag.agent.tools._dispatch_tool_with_retry", new=_raise_ki):
          ctx = _FakeContext()
          with pytest.raises(KeyboardInterrupt):
              await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})

  @pytest.mark.asyncio
  async def test_execute_and_record_tool_records_db_error():
      from sqlalchemy.exc import DBAPIError
      from app.services.rag.agent.tools import _execute_and_record_tool

      async def _raise_db(*args, **kwargs):
          raise DBAPIError("stmt", "params", Exception("conn refused"))

      with patch("app.services.rag.agent.tools._dispatch_tool_with_retry", new=_raise_db):
          ctx = _FakeContext()
          result = await _execute_and_record_tool(ctx, "search_chunks", {"query": "test"})
          assert result["ok"] is False
          assert "error" in result
  ```

- [ ] **Step 2: Run test to verify it fails**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_tools_exception_handling.py -v
  ```
  Expected: FAIL — current broad `except Exception` swallows `KeyboardInterrupt`

- [ ] **Step 3: Implement fix in `tools.py` lines 35–79**

  Replace the current `_execute_and_record_tool` body. Add before the function:

  ```python
  # Recoverable tool-level errors — only these are caught and recorded as ok=False.
  # Do NOT use bare except Exception — ADK 2.x uses NodeInterruptedError and similar
  # framework signals that must propagate freely.
  _TOOL_RECOVERABLE_EXCEPTIONS = (
      DBAPIError,
      OperationalError,
      ServiceUnavailable,
      SessionExpired,
      httpx.HTTPError,
      socket.error,
      asyncio.TimeoutError,
      ConnectionError,
      OSError,
  )
  ```

  New function body:

  ```python
  async def _execute_and_record_tool(
      tool_context: ToolContext | None,
      tool_name: str,
      tool_args: dict,
  ) -> dict:
      if tool_context is None:
          raise ValueError(
              f"ADK ToolContext is required but was None for tool '{tool_name}'"
          )

      ctx: QueryContext = tool_context.state["query_context"]
      try:
          res = await _dispatch_tool_with_retry(tool_name, tool_args, ctx)
      except _TOOL_RECOVERABLE_EXCEPTIONS as exc:
          log_json(
              logger,
              logging.WARNING,
              "Agent tool failed after retries",
              tool=tool_name,
              error=str(exc),
          )
          res = {"ok": False, "error": str(exc)}
          if "observations" in tool_context.state:
              tool_context.state["observations"] = list(
                  tool_context.state["observations"]
              ) + [{"tool": tool_name, "args": tool_args, "result": res}]
          return res

      if "observations" in tool_context.state:
          tool_context.state["observations"] = list(
              tool_context.state["observations"]
          ) + [{"tool": tool_name, "args": tool_args, "result": res}]
      return res
  ```

- [ ] **Step 4: Run test to verify it passes**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_tools_exception_handling.py -v
  ```
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add packages/backend-core/app/services/rag/agent/tools.py \
    packages/backend-core/tests/test_tools_exception_handling.py
  git commit -m "fix: narrow exception handling in _execute_and_record_tool for ADK 2.x compat"
  ```

---

## Task 3: Extract Pure-Python Graph Nodes

**Files:**
- Create: `packages/backend-core/app/services/rag/agent/graph_nodes.py`
- Test: `packages/backend-core/tests/test_graph_nodes.py`

**Interfaces:**
- Produces:
  - `detect_intent(question: str, ctx: QueryContext) -> str` → `"current_page"` | `"content_search"`
  - `decompose_question(question: str) -> tuple[list[str], bool]` → `(sub_questions, was_split)`
  - `grade_context(observations: list[dict]) -> tuple[str, int, int]` → `(graded_text, raw_count, graded_count)`
  - `is_graph_enabled(ctx: QueryContext) -> bool`
  - `build_human_message(ctx: QueryContext, question: str) -> str`
  - `extract_used_book_ids(observations: list[dict]) -> list[str]`
  - `populate_ctx_from_observations(ctx, observations, graded_context, llm_calls) -> None`

- [ ] **Step 1: Write the failing tests**

  ```python
  # packages/backend-core/tests/test_graph_nodes.py
  from unittest.mock import MagicMock
  import pytest

  def _make_ctx(**kw):
      ctx = MagicMock()
      ctx.current_page = kw.get("current_page", None)
      ctx.is_global = kw.get("is_global", False)
      ctx.book = kw.get("book", None)
      ctx.use_knowledge_graph_in_chat = kw.get("use_knowledge_graph_in_chat", False)
      ctx.history = kw.get("history", [])
      ctx.context_book_ids = kw.get("context_book_ids", [])
      ctx.character_categories = kw.get("character_categories", [])
      ctx.book_id = kw.get("book_id", "abc")
      return ctx

  class TestDetectIntent:
      def test_default_is_content_search(self):
          from app.services.rag.agent.graph_nodes import detect_intent
          ctx = _make_ctx()
          assert detect_intent("what is the main theme", ctx) == "content_search"

      def test_current_page_when_page_set_and_keyword_match(self):
          from app.services.rag.agent.graph_nodes import detect_intent
          ctx = _make_ctx(current_page=5)
          assert detect_intent("بۇ بەتتە نېمە بار", ctx) == "current_page"

      def test_no_current_page_never_returns_current_page(self):
          from app.services.rag.agent.graph_nodes import detect_intent
          ctx = _make_ctx(current_page=None)
          assert detect_intent("بۇ بەتتە نېمە بار", ctx) == "content_search"

  class TestDecomposeQuestion:
      def test_single_question_unchanged(self):
          from app.services.rag.agent.graph_nodes import decompose_question
          subs, was_split = decompose_question("what is this book about")
          assert subs == ["what is this book about"]
          assert was_split is False

      def test_two_question_marks_triggers_split(self):
          from app.services.rag.agent.graph_nodes import decompose_question
          _, was_split = decompose_question("كىم يازغان؟ قاچان يازغان؟")
          assert was_split is True

  class TestGradeContext:
      def test_empty_returns_no_docs_string(self):
          from app.services.rag.agent.graph_nodes import grade_context
          text, before, after = grade_context([])
          assert "NO RELEVANT DOCUMENTS" in text
          assert before == 0 and after == 0

      def test_deduplicates_same_book_page(self):
          from app.services.rag.agent.graph_nodes import grade_context
          obs = [{
              "tool": "search_chunks",
              "result": {"ok": True, "data": {"chunks": [
                  {"text": "A", "title": "T", "book_id": "1", "page": 1, "score": 0.9},
                  {"text": "B", "title": "T", "book_id": "1", "page": 1, "score": 0.8},
              ]}},
          }]
          _, before, after = grade_context(obs)
          assert before == 2
          assert after == 1

  class TestIsGraphEnabled:
      def test_disabled_when_kg_feature_off(self):
          from app.services.rag.agent.graph_nodes import is_graph_enabled
          ctx = _make_ctx(use_knowledge_graph_in_chat=False)
          assert is_graph_enabled(ctx) is False

      def test_enabled_global_with_kg_on(self):
          from app.services.rag.agent.graph_nodes import is_graph_enabled
          ctx = _make_ctx(use_knowledge_graph_in_chat=True, is_global=True)
          assert is_graph_enabled(ctx) is True

      def test_single_book_requires_complete_milestone(self):
          from app.services.rag.agent.graph_nodes import is_graph_enabled
          book = MagicMock()
          book.graph_milestone = "pending"
          ctx = _make_ctx(use_knowledge_graph_in_chat=True, is_global=False, book=book)
          assert is_graph_enabled(ctx) is False
          book.graph_milestone = "complete"
          assert is_graph_enabled(ctx) is True
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_graph_nodes.py -v
  ```
  Expected: FAIL — module does not exist

- [ ] **Step 3: Create `graph_nodes.py`**

  The module extracts the following private functions that currently live in `handler.py`:
  - `_detect_intent` → exported as `detect_intent`
  - `_is_graph_enabled` → exported as `is_graph_enabled`
  - `_build_human_message` → exported as `build_human_message`
  - `_grade_context` → exported as `grade_context`
  - `_extract_used_book_ids` → exported as `extract_used_book_ids`
  - `_populate_ctx_from_observations` → exported as `populate_ctx_from_observations`

  And adds a new pure-Python node:
  - `decompose_question` → heuristic-only split detection (returns flag, not LLM split)

  The module imports: `PAGE_QUERY_PATTERNS` from `app.services.rag.keywords`; `AGENT_MAX_CONTEXT_CHUNKS`, `GRADE_RELATIVE_THRESHOLD`, `MIN_CHUNKS_AFTER_GRADING` from `agent.config`; `Document`, `format_document` from `answer_builder` (lazy import inside `grade_context`).

  > **Full code**: See [graph_nodes.py source in Task 3 step 3](file:///Users/Omarjan/Projects/kitabim-ai/packages/backend-core/app/services/rag/agent/graph_nodes.py) — create this file with all 7 exported functions as documented above; implementation is a direct extraction of the corresponding private functions in `handler.py`.

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_graph_nodes.py -v
  ```
  Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

  ```bash
  git add packages/backend-core/app/services/rag/agent/graph_nodes.py \
    packages/backend-core/tests/test_graph_nodes.py
  git commit -m "feat: extract pure-python graph node functions to graph_nodes.py"
  ```

---

## Task 4: Implement `run_graph_workflow_stream` (Graph Orchestrator)

**Files:**
- Create: `packages/backend-core/app/services/rag/agent/graph_agent.py`
- Test: `packages/backend-core/tests/test_graph_agent.py`

**Interfaces:**
- Consumes: all 7 functions from `graph_nodes`; `build_rag_agent` from `adk_agent`; `InMemoryRunner` from ADK
- Produces: `async def run_graph_workflow_stream(ctx: QueryContext, question: str) -> AsyncIterator[dict]`
  - yields `{"type": "planning", "intent": str}`
  - yields `{"type": "decompose", "count": int}` (optional)
  - yields `{"type": "tool_call", "tool": str, "name": str}` (0+)
  - yields `{"type": "agent_thinking", "text": str}` (0+)
  - yields `{"type": "tool_result", "tool": str, "found": int}` (0+)
  - yields `{"type": "result", "sub_questions": list, "observations": list, "graded_context": str, "before_count": int, "after_count": int, "llm_calls": int}` (always exactly 1, last)

- [ ] **Step 1: Write the failing tests**

  ```python
  # packages/backend-core/tests/test_graph_agent.py
  import pytest
  from unittest.mock import AsyncMock, MagicMock, patch

  def _make_ctx():
      ctx = MagicMock()
      ctx.question = "what is this book about"
      ctx.current_page = None
      ctx.is_global = False
      ctx.book = None
      ctx.use_knowledge_graph_in_chat = False
      ctx.history = []
      ctx.context_book_ids = []
      ctx.character_categories = []
      ctx.book_id = "abc"
      ctx.agent_model = "gemini-2.0-flash"
      ctx.user_id = "test-user"
      ctx.enriched_question = None
      ctx.used_book_ids = []
      return ctx

  async def _empty_runner(*args, **kwargs):
      return
      yield  # async generator that yields nothing

  @pytest.mark.asyncio
  async def test_yields_planning_event_first():
      from app.services.rag.agent.graph_agent import run_graph_workflow_stream
      ctx = _make_ctx()
      with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
          instance = Mock.return_value
          session = MagicMock()
          session.user_id = "test-user"
          session.id = "session-1"
          instance.session_service.create_session = AsyncMock(return_value=session)
          instance.run_async = _empty_runner
          events = [e async for e in run_graph_workflow_stream(ctx, ctx.question)]
      assert events[0]["type"] == "planning"

  @pytest.mark.asyncio
  async def test_always_yields_exactly_one_result_event():
      from app.services.rag.agent.graph_agent import run_graph_workflow_stream
      ctx = _make_ctx()
      with patch("app.services.rag.agent.graph_agent.InMemoryRunner") as Mock:
          instance = Mock.return_value
          session = MagicMock()
          session.user_id = "test-user"
          session.id = "session-1"
          instance.session_service.create_session = AsyncMock(return_value=session)
          instance.run_async = _empty_runner
          events = [e async for e in run_graph_workflow_stream(ctx, ctx.question)]
      result_events = [e for e in events if e.get("type") == "result"]
      assert len(result_events) == 1
      re = result_events[0]
      assert "graded_context" in re
      assert "sub_questions" in re
      assert "observations" in re
  ```

- [ ] **Step 2: Run tests to confirm they fail**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_graph_agent.py -v
  ```
  Expected: FAIL — module does not exist

- [ ] **Step 3: Create `graph_agent.py`**

  Key structure:

  ```python
  # packages/backend-core/app/services/rag/agent/graph_agent.py
  """Graph-based deterministic RAG workflow orchestrator (ADK 2.0).

  Replaces the monolithic _execute_workflow_stream in handler.py with explicit
  graph nodes. The ADK LlmAgent (ReAct) is used only as the retrieval sub-agent;
  the outer orchestrator controls flow deterministically.
  """
  from __future__ import annotations
  import logging, json, re
  from typing import TYPE_CHECKING, AsyncIterator
  from google.adk.runners import InMemoryRunner
  from google.genai import types
  from app.services.rag.agent.graph_nodes import (
      build_human_message, decompose_question, detect_intent,
      extract_used_book_ids, grade_context, is_graph_enabled,
      populate_ctx_from_observations,
  )
  from app.utils.observability import log_json
  if TYPE_CHECKING:
      from app.services.rag.context import QueryContext

  logger = logging.getLogger("app.rag.agent.graph_agent")
  _MAX_SUB_QUESTIONS = 4

  async def _llm_split_question(question: str, model_name: str) -> list[str]:
      """LLM-assisted question splitting. Falls back to [question] on error."""
      from app.llm.models import generate_text
      prompt = (
          "Extract each distinct question as a self-contained string.\n"
          f"Return a JSON array of at most {_MAX_SUB_QUESTIONS} question strings (no other text).\n"
          "If questions concern the same entity, return a single-element array.\n"
          f"Message: {question}\n\nJSON array:"
      )
      try:
          raw = await generate_text(prompt, model_name)
          m = re.search(r"\[.*?\]", raw, re.DOTALL)
          if m:
              parts = json.loads(m.group())
              if isinstance(parts, list) and all(isinstance(p, str) for p in parts):
                  return [p.strip() for p in parts if p.strip()][:_MAX_SUB_QUESTIONS]
      except Exception as exc:
          log_json(logger, logging.WARNING, "LLM split failed", error=str(exc))
      return [question]

  async def run_graph_workflow_stream(
      ctx: "QueryContext", question: str
  ) -> AsyncIterator[dict]:
      from app.services.rag.agent.adk_agent import build_rag_agent
      # Node 1: Intent Detection
      intent = detect_intent(question, ctx)
      yield {"type": "planning", "intent": intent}
      # Node 2: Question Decomposition
      sub_questions, needs_split = decompose_question(question)
      if needs_split:
          sub_questions = await _llm_split_question(question, ctx.agent_model)
          if len(sub_questions) > 1:
              yield {"type": "decompose", "count": len(sub_questions)}
              numbered = "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
              question = question + f"\n\n[Sub-questions]\n{numbered}"
      # Node 3+4: Retrieval Loop (ADK sub-agent)
      agent = build_rag_agent(ctx.agent_model, graph_enabled=is_graph_enabled(ctx))
      runner = InMemoryRunner(agent=agent, app_name="kitabim")
      session = await runner.session_service.create_session(
          app_name="kitabim",
          user_id=ctx.user_id or "anon",
          state={"query_context": ctx, "observations": []},
      )
      content = types.Content(
          role="user",
          parts=[types.Part.from_text(text=build_human_message(ctx, question))]
      )
      inline_observations: list[dict] = []
      pending_calls: dict[str, str] = {}
      async for event in runner.run_async(
          user_id=session.user_id, session_id=session.id, new_message=content
      ):
          if not event.partial and event.content and event.content.parts:
              for part in event.content.parts:
                  if part.function_call:
                      call_id = getattr(part.function_call, "id", None) or part.function_call.name
                      pending_calls[call_id] = part.function_call.name
                      yield {"type": "tool_call", "tool": part.function_call.name, "name": part.function_call.name}
                  if part.text:
                      yield {"type": "agent_thinking", "text": part.text}
          for fr in (event.get_function_responses() or []):
              response_data = fr.response or {}
              call_id = getattr(fr, "id", None) or fr.name
              tool_name = pending_calls.pop(call_id, fr.name)
              inline_observations.append({"tool": tool_name, "result": response_data})
              found = response_data.get("found_count", 0) if isinstance(response_data, dict) else 0
              yield {"type": "tool_result", "tool": tool_name, "found": found}
      # Node 5: Context Grading
      ctx.used_book_ids = extract_used_book_ids(inline_observations)
      graded_context, before_count, after_count = grade_context(inline_observations)
      populate_ctx_from_observations(ctx, inline_observations, graded_context, len(inline_observations))
      yield {
          "type": "result",
          "sub_questions": sub_questions,
          "observations": inline_observations,
          "llm_calls": len(inline_observations),
          "graded_context": graded_context,
          "before_count": before_count,
          "after_count": after_count,
      }
  ```

- [ ] **Step 4: Run tests to confirm they pass**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_graph_agent.py -v
  ```
  Expected: PASS

- [ ] **Step 5: Commit**

  ```bash
  git add packages/backend-core/app/services/rag/agent/graph_agent.py \
    packages/backend-core/tests/test_graph_agent.py
  git commit -m "feat: implement run_graph_workflow_stream graph-based RAG orchestrator (ADK 2.0)"
  ```

---

## Task 5: Wire Handler + Fix deterministic_handler.py Imports

**Files:**
- Modify: `packages/backend-core/app/services/rag/agent/handler.py` (full rewrite — slim)
- Modify: `packages/backend-core/app/services/rag/agent/deterministic_handler.py` (import fix only)
- Test: `packages/backend-core/tests/test_agent_rag_handler.py`

**Interfaces:**
- Consumes: `run_graph_workflow_stream` from `graph_agent`; `generate_answer_stream` from `answer_builder`
- Produces: `AgentRAGHandler.handle(ctx) -> str`; `AgentRAGHandler.handle_stream(ctx) -> AsyncIterator`

- [ ] **Step 1: Write the failing tests**

  ```python
  # packages/backend-core/tests/test_agent_rag_handler.py
  import pytest
  from unittest.mock import MagicMock, patch

  def _make_ctx():
      ctx = MagicMock()
      ctx.question = "what is this about"
      ctx.enriched_question = None
      ctx.agent_model = "gemini-2.0-flash"
      ctx.rag_chain = MagicMock()
      ctx.chat_history_str = ""
      ctx.persona_prompt = None
      ctx.is_global = False
      ctx.character_categories = []
      ctx.use_deterministic_router = False
      return ctx

  async def _fake_graph_stream(ctx, question):
      yield {"type": "planning", "intent": "content_search"}
      yield {
          "type": "result",
          "sub_questions": [question],
          "observations": [],
          "graded_context": "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY.",
          "before_count": 0, "after_count": 0, "llm_calls": 0,
      }

  @pytest.mark.asyncio
  async def test_handle_returns_string():
      from app.services.rag.agent.handler import AgentRAGHandler
      ctx = _make_ctx()
      async def _fake_answer(*args, **kwargs):
          yield "Hello World"
      with patch("app.services.rag.agent.handler.run_graph_workflow_stream", new=_fake_graph_stream), \
           patch("app.services.rag.agent.handler.generate_answer_stream", new=_fake_answer):
          result = await AgentRAGHandler().handle(ctx)
      assert isinstance(result, str) and len(result) > 0

  @pytest.mark.asyncio
  async def test_handle_stream_includes_all_event_types():
      from app.services.rag.agent.handler import AgentRAGHandler
      ctx = _make_ctx()
      async def _fake_answer(*args, **kwargs):
          yield "token"
      with patch("app.services.rag.agent.handler.run_graph_workflow_stream", new=_fake_graph_stream), \
           patch("app.services.rag.agent.handler.generate_answer_stream", new=_fake_answer):
          events = [e async for e in AgentRAGHandler().handle_stream(ctx)]
      types = {e.get("type") for e in events if isinstance(e, dict)}
      assert {"planning", "answer_start", "chunk", "answer_end"}.issubset(types)
  ```

- [ ] **Step 2: Run test to confirm it fails**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/test_agent_rag_handler.py -v
  ```
  Expected: FAIL — old handler does not import `run_graph_workflow_stream`

- [ ] **Step 3: Rewrite `handler.py`**

  Replace the entire file with the slim delegating version:

  ```python
  """AgentRAGHandler — delegates to graph_agent.run_graph_workflow_stream.

  The handler class interface (handle / handle_stream) is unchanged.
  All orchestration logic lives in graph_agent.py and graph_nodes.py.
  """
  from __future__ import annotations
  import logging
  from typing import AsyncIterator, Union
  from app.services.rag.agent.graph_agent import run_graph_workflow_stream
  from app.services.rag.answer_builder import generate_answer_stream
  from app.services.rag.base_handler import QueryHandler
  from app.services.rag.context import QueryContext
  from app.utils.observability import log_json

  logger = logging.getLogger("app.rag.agent.handler")


  class AgentRAGHandler(QueryHandler):
      """Graph-based RAG handler. Fallback for all unmatched intents."""

      intent_name = "agent_rag"

      def can_handle(self, _ctx: QueryContext) -> bool:
          return True

      async def handle(self, ctx: QueryContext) -> str:
          from app.utils.citation_fixer import fix_malformed_citations
          log_json(logger, logging.INFO, "Graph RAG agent invoked (non-stream)", model=ctx.agent_model)
          question = ctx.enriched_question or ctx.question
          sub_questions = graded_context = None
          async for event in run_graph_workflow_stream(ctx, question):
              if event.get("type") == "result":
                  sub_questions = event["sub_questions"]
                  graded_context = event["graded_context"]
          if graded_context is None:
              graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
              sub_questions = [question]
          final_q = (
              "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
              if len(sub_questions) > 1 else (ctx.enriched_question or ctx.question)
          )
          chunks = []
          async for token in generate_answer_stream(
              graded_context, final_q, ctx.rag_chain,
              chat_history=ctx.chat_history_str, persona_prompt=ctx.persona_prompt,
              is_global=ctx.is_global, has_categories=bool(ctx.character_categories),
          ):
              chunks.append(token)
          return fix_malformed_citations("".join(chunks))

      async def handle_stream(self, ctx: QueryContext) -> AsyncIterator[Union[str, dict]]:
          log_json(logger, logging.INFO, "Graph RAG agent invoked (stream)", model=ctx.agent_model)
          question = ctx.enriched_question or ctx.question
          sub_questions = graded_context = None
          before_count = after_count = 0
          async for event in run_graph_workflow_stream(ctx, question):
              if event.get("type") == "result":
                  sub_questions = event["sub_questions"]
                  graded_context = event["graded_context"]
                  before_count = event.get("before_count", 0)
                  after_count = event.get("after_count", 0)
              else:
                  yield event
          if graded_context is None:
              graded_context = "NO RELEVANT DOCUMENTS FOUND IN THE LIBRARY."
              sub_questions = [question]
          if before_count > 0:
              yield {"type": "grading", "before": before_count, "after": after_count}
          final_q = (
              "\n".join(f"{i+1}. {q}" for i, q in enumerate(sub_questions))
              if len(sub_questions) > 1 else (ctx.enriched_question or ctx.question)
          )
          yield {"type": "answer_start"}
          async for token in generate_answer_stream(
              graded_context, final_q, ctx.rag_chain,
              chat_history=ctx.chat_history_str, persona_prompt=ctx.persona_prompt,
              is_global=ctx.is_global, has_categories=bool(ctx.character_categories),
          ):
              yield {"type": "chunk", "text": token}
          yield {"type": "answer_end"}
  ```

- [ ] **Step 4: Fix `deterministic_handler.py` import**

  Find and replace this import block in `deterministic_handler.py`:

  ```diff
  -from app.services.rag.agent.handler import (
  -    _grade_context,
  -    _extract_used_book_ids,
  -    _populate_ctx_from_observations,
  -)
  +from app.services.rag.agent.graph_nodes import (
  +    grade_context as _grade_context,
  +    extract_used_book_ids as _extract_used_book_ids,
  +    populate_ctx_from_observations as _populate_ctx_from_observations,
  +)
  ```

- [ ] **Step 5: Run all tests**

  ```bash
  source .venv/bin/activate && pytest packages/backend-core/tests/ -v
  ```
  Expected: All tests PASS

- [ ] **Step 6: Commit**

  ```bash
  git add packages/backend-core/app/services/rag/agent/handler.py \
    packages/backend-core/app/services/rag/agent/deterministic_handler.py \
    packages/backend-core/tests/test_agent_rag_handler.py
  git commit -m "feat: wire AgentRAGHandler to graph workflow; fix deterministic_handler imports"
  ```

---

## Task 6: Docker Rebuild & Manual Verification

**Files:** No code changes — build and smoke test only.

- [ ] **Step 1: Rebuild backend Docker image**

  ```bash
  ./deploy/local/rebuild-and-restart.sh backend
  ```
  Expected: Build success, `google-adk>=2.5.0` installed

- [ ] **Step 2: Check startup logs**

  ```bash
  docker compose logs --tail=60 backend
  ```
  Expected: No `ImportError`, `ModuleNotFoundError`, or `AttributeError`

- [ ] **Step 3: Smoke test streaming chat (with `use_deterministic_router=false`)**

  Send a chat question via the app at `http://localhost:30080`.

  Expected SSE event order:
  1. `{"type": "planning", "intent": "content_search"}`
  2. `{"type": "tool_call", "tool": "search_chunks", ...}` (1+)
  3. `{"type": "tool_result", ...}` (1+)
  4. `{"type": "grading", "before": N, "after": M}` (if chunks found)
  5. `{"type": "answer_start"}`
  6. `{"type": "chunk", "text": "..."}` (repeated)
  7. `{"type": "answer_end"}`

- [ ] **Step 4: Smoke test deterministic handler (with `use_deterministic_router=true`)**

  Enable in system config admin panel. Check logs for `"Intent matched": "deterministic_rag"`.

- [ ] **Step 5: Final commit**

  ```bash
  git commit --allow-empty -m "chore: ADK 2.0 graph workflow verified in Docker"
  ```

---

## Open Questions

> [!IMPORTANT]
> **Session state serialization warning**: ADK 2.x warns when `session.state` contains non-serializable objects. We store `QueryContext` (which holds `AsyncSession`) in session state. If serialization warnings appear after upgrade, wrap the context in a proxy that excludes non-serializable fields, or move `query_context` out of session state and pass it via a closure/global context instead.

> [!NOTE]
> **`google-adk[gcp]` extra**: The `[gcp]` extra adds Vertex AI session/artifact services. Kept for potential future use with Vertex AI Session Services. No impact on the current `InMemoryRunner` usage.

> [!NOTE]
> **Worker service**: `services/worker/requirements.txt` should be checked for `google-adk` — the worker does not use ADK directly but the shared `backend-core` package may pull it transitively. Explicit pinning prevents version conflicts.
