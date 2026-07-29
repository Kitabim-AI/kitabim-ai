"""Graph-based execution router for DeterministicRAGHandler.

Replaces execute_path()'s if/elif dispatch chain
(app/services/rag/agent/deterministic_handler.py) with a declarative
google.adk.workflow.Workflow graph. Each of the 9 real branches is its own
graph node, calling the exact same DeterministicRAGHandler._path_*() method
extracted for this purpose — no retrieval logic is duplicated here, only
the routing structure. 6 of those 9 nodes (see _FALLBACK_ROUTES) also carry
an unconditional edge into a shared `universal_fallback_node`, replacing
what used to be 6 separate inline calls to `_run_universal_fallback()`.

Progress-event bridge
----------------------
ADK 2.5's node runner allows at most one output-bearing yield per node
(see Phase 0 spike notes / PR description): any raw value a node yields
that isn't an Event/RequestInput/types.Content becomes a candidate
`ctx.output`, and a second one raises "Output already set." Since
_path_*() methods stream a dict per tool-call lifecycle stage
(tool_call, tool_result, tool_done_result) and most paths call more than
one tool, those events must be wrapped as `types.Content` (a recognized
passthrough type — see FunctionNode._to_event) before being yielded into
a node, so they never touch `ctx.output`. DeterministicRAGHandler.
execute_path() unwraps them back into the original dicts on the way out
via decode_progress_event(), reproducing today's SSE tool_call/
tool_result stream exactly.

Nodes never rely on ctx.output at all: the actual result of a run is the
`observations` list, mutated in place and read by the caller via the same
closure reference passed into build_path_selection_workflow() — mirroring
how DeterministicRAGHandler already threads `observations` through
execute_path() today.

Runner reuse
------------
Each call still builds its own Workflow graph (node closures capture the
call's specific question/signals/observations, so the graph itself can't
be shared across calls with different data) and its own ADK session (each
execute_path() run must be isolated — sharing a session across concurrent
sub-question runs would let one overwrite another's session state). What
*is* shared, when a `RunnerServices` bundle is passed in from a single
chat turn, is the in-memory session/artifact/memory *storage backends* —
avoiding rebuilding those for every sub-question in a composite question,
while remaining safe under concurrent (parallel sub-question) use, since
creating independent session ids on the same in-memory store doesn't race
under asyncio's cooperative scheduling.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, AsyncIterator

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.workflow import DEFAULT_ROUTE, Workflow, node
from google.genai import types

if TYPE_CHECKING:
    from app.services.rag.agent.deterministic_handler import DeterministicRAGHandler
    from app.services.rag.context import QueryContext

_APP_NAME = "kitabim-graph-router"


class RunnerServices:
    """Shared in-memory ADK runner service backends.

    Build one per chat turn and pass it to every execute_path() call in
    that turn (single question or composite) so each call's Runner reuses
    the same session/artifact/memory storage instead of constructing a
    fresh one — see module docstring for why this is still safe when
    sub-questions run concurrently.
    """

    __slots__ = ("session_service", "artifact_service", "memory_service")

    def __init__(self) -> None:
        self.session_service = InMemorySessionService()
        self.artifact_service = InMemoryArtifactService()
        self.memory_service = InMemoryMemoryService()


_PROGRESS_MARKER = "__wf_progress__"

# route value -> DeterministicRAGHandler._path_* method name
_ROUTE_TO_METHOD = {
    "current_page": "_path_current_page",
    "quran": "_path_quran",
    "dictionary": "_path_dictionary",
    "catalog": "_path_catalog",
    "named_title": "_path_named_title",
    "named_author": "_path_named_author",
    "volume_shift": "_path_volume_shift",
    "in_reader_only": "_path_in_reader_only",
    "context_books": "_path_context_books",
    DEFAULT_ROUTE: "_path_open",
}

# Routes whose branch always runs _run_universal_fallback() afterward —
# modeled as an unconditional graph edge into one shared node rather than
# each _path_*() method calling it inline. _path_catalog is deliberately
# excluded: its fallback call is conditional on catalog_found, which is
# branch-local business logic, not routing structure.
_FALLBACK_ROUTES = {
    "named_title",
    "named_author",
    "volume_shift",
    "context_books",
    DEFAULT_ROUTE,
}


def _to_progress_content(event: dict) -> types.Content:
    """Wraps a tool-call lifecycle dict as Content so it never sets ctx.output."""
    payload = json.dumps({_PROGRESS_MARKER: True, "event": event})
    return types.Content(role="model", parts=[types.Part.from_text(text=payload)])


def decode_progress_event(adk_event) -> dict | None:
    """Unwraps an ADK event back into the original tool-call dict, or None."""
    content = getattr(adk_event, "content", None)
    if not content or not content.parts:
        return None
    for part in content.parts:
        if not part.text:
            continue
        try:
            data = json.loads(part.text)
        except (ValueError, TypeError):
            continue
        if isinstance(data, dict) and data.get(_PROGRESS_MARKER):
            return data.get("event")
    return None


def _select_route(intent: str, signals: dict) -> str:
    """Mirrors DeterministicRAGHandler.execute_path()'s precedence chain."""
    top_intent = signals.get("top_intent")

    if top_intent == "current_page" and signals.get("in_reader"):
        return "current_page"
    if intent == "quran":
        return "quran"
    if intent == "dictionary":
        return "dictionary"
    if signals.get("has_title"):
        return "named_title"
    if intent == "catalog":
        return "catalog"
    if signals.get("has_author") and not signals.get("has_title"):
        return "named_author"
    if signals.get("is_volume_shift") and (
        signals.get("in_reader") or signals.get("has_context_books")
    ):
        return "volume_shift"
    if (
        signals.get("in_reader")
        and not signals.get("has_title")
        and not signals.get("has_author")
    ):
        return "in_reader_only"
    if signals.get("has_context_books"):
        return "context_books"
    return DEFAULT_ROUTE


def build_path_selection_workflow(
    intent: str,
    signals: dict,
    question: str,
    ctx: "QueryContext",
    observations: list,
    handler: "DeterministicRAGHandler",
) -> Workflow:
    """Builds a fresh graph per call, mirroring today's per-request execute_path()."""

    async def select_path(ctx):
        ctx.route = _select_route(intent, signals)

    def _make_path_node(method_name: str):
        method = getattr(handler, method_name)

        async def _run():
            async for ev in method(intent, signals, question, ctx, observations):
                yield _to_progress_content(ev)

        return _run

    async def _run_fallback():
        async for ev in handler._run_universal_fallback(question, ctx, observations):
            yield _to_progress_content(ev)

    select_path_node = node(select_path, name="select_path")
    all_nodes_by_route = {
        route: node(_make_path_node(method_name), name=method_name.lstrip("_"))
        for route, method_name in _ROUTE_TO_METHOD.items()
    }
    universal_fallback_node = node(_run_fallback, name="run_universal_fallback")

    return Workflow(
        name="deterministic_path_selection",
        edges=[
            ("START", select_path_node),
            (select_path_node, all_nodes_by_route),
            *[
                (all_nodes_by_route[route], universal_fallback_node)
                for route in _FALLBACK_ROUTES
            ],
        ],
    )


async def run_path_selection_workflow(
    intent: str,
    signals: dict,
    question: str,
    ctx: "QueryContext",
    observations: list,
    handler: "DeterministicRAGHandler",
    services: RunnerServices | None = None,
) -> AsyncIterator[dict]:
    """Builds and runs the path-selection graph, yielding decoded progress events.

    Pass a `RunnerServices` built once per chat turn to reuse its session/
    artifact/memory backends across multiple sub-question calls; omit it
    (e.g. in standalone tests) to get a fresh, self-contained one.
    """
    workflow = build_path_selection_workflow(
        intent, signals, question, ctx, observations, handler
    )
    if services is None:
        services = RunnerServices()

    runner = Runner(
        agent=workflow,
        app_name=_APP_NAME,
        session_service=services.session_service,
        artifact_service=services.artifact_service,
        memory_service=services.memory_service,
    )
    session = await runner.session_service.create_session(
        app_name=_APP_NAME, user_id=ctx.user_id or "anon"
    )
    content = types.Content(role="user", parts=[types.Part.from_text(text=question)])

    from google.adk.agents.run_config import RunConfig, StreamingMode

    async for event in runner.run_async(
        user_id=session.user_id,
        session_id=session.id,
        new_message=content,
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    ):
        progress = decode_progress_event(event)
        if progress is not None:
            yield progress
