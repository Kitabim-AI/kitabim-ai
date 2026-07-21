"""Unit tests for graph_router.py's own responsibilities: the route
precedence chain and the tool-event <-> types.Content progress bridge.

Full end-to-end path behavior (each branch's tool sequence) is covered by
deterministic_router_test.py, which exercises DeterministicRAGHandler.
execute_path() directly — now backed by this graph, so those 28 tests
are the regression suite for the graph wiring itself.
"""

from google.adk.workflow import DEFAULT_ROUTE
from google.genai import types

from app.services.rag.agent.graph_router import (
    _select_route,
    _to_progress_content,
    decode_progress_event,
)


def test_select_route_current_page():
    signals = {"top_intent": "current_page", "in_reader": True}
    assert _select_route("passage", signals) == "current_page"


def test_select_route_quran():
    assert _select_route("quran", {}) == "quran"


def test_select_route_dictionary():
    assert _select_route("dictionary", {}) == "dictionary"


def test_select_route_catalog():
    assert _select_route("catalog", {}) == "catalog"


def test_select_route_named_title_takes_precedence_over_author():
    signals = {"has_title": True, "has_author": True}
    assert _select_route("passage", signals) == "named_title"


def test_select_route_named_author_only():
    signals = {"has_title": False, "has_author": True}
    assert _select_route("passage", signals) == "named_author"


def test_select_route_volume_shift():
    signals = {"is_volume_shift": True, "in_reader": True}
    assert _select_route("passage", signals) == "volume_shift"

    signals = {"is_volume_shift": True, "has_context_books": True}
    assert _select_route("passage", signals) == "volume_shift"

    # Volume shift signal alone, without in_reader/has_context_books, does
    # not match — falls through to a later bucket.
    signals = {"is_volume_shift": True}
    assert _select_route("passage", signals) != "volume_shift"


def test_select_route_in_reader_only():
    signals = {"in_reader": True, "has_title": False, "has_author": False}
    assert _select_route("passage", signals) == "in_reader_only"


def test_select_route_context_books():
    signals = {"has_context_books": True}
    assert _select_route("passage", signals) == "context_books"


def test_select_route_default_open():
    signals = {
        "top_intent": "content_search",
        "has_title": False,
        "has_author": False,
        "is_volume_shift": False,
        "in_reader": False,
        "has_context_books": False,
    }
    assert _select_route("passage", signals) == DEFAULT_ROUTE


def test_progress_event_round_trip():
    event = {"type": "tool_call", "tool": "search_chunks", "name": "search_chunks"}
    content = _to_progress_content(event)
    assert isinstance(content, types.Content)

    class _FakeAdkEvent:
        pass

    fake = _FakeAdkEvent()
    fake.content = content
    assert decode_progress_event(fake) == event


def test_decode_progress_event_ignores_non_marker_content():
    class _FakeAdkEvent:
        pass

    fake = _FakeAdkEvent()
    fake.content = types.Content(
        role="model", parts=[types.Part.from_text(text="just a normal LLM reply")]
    )
    assert decode_progress_event(fake) is None


def test_decode_progress_event_handles_missing_content():
    class _FakeAdkEvent:
        pass

    fake = _FakeAdkEvent()
    fake.content = None
    assert decode_progress_event(fake) is None
