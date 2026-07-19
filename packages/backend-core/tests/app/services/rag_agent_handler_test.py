from unittest.mock import MagicMock

from app.services.rag.agent.handler import _is_graph_enabled


class FakeBook:
    def __init__(self, graph_milestone):
        self.graph_milestone = graph_milestone


def _ctx(is_global, book, use_knowledge_graph_in_chat):
    ctx = MagicMock()
    ctx.is_global = is_global
    ctx.book = book
    ctx.use_knowledge_graph_in_chat = use_knowledge_graph_in_chat
    return ctx


def test_graph_disabled_by_config_in_single_book_mode():
    """When the admin config flag is off, the agent must not be offered the
    knowledge-graph tool even if the book's graph is otherwise complete."""
    ctx = _ctx(False, FakeBook("complete"), use_knowledge_graph_in_chat=False)
    assert _is_graph_enabled(ctx) is False


def test_graph_disabled_by_config_in_global_mode():
    ctx = _ctx(True, None, use_knowledge_graph_in_chat=False)
    assert _is_graph_enabled(ctx) is False


def test_graph_enabled_in_single_book_mode_when_milestone_complete():
    ctx = _ctx(False, FakeBook("complete"), use_knowledge_graph_in_chat=True)
    assert _is_graph_enabled(ctx) is True


def test_graph_disabled_in_single_book_mode_when_milestone_incomplete():
    """Config is on, but this specific book's graph hasn't finished building."""
    ctx = _ctx(False, FakeBook("processing"), use_knowledge_graph_in_chat=True)
    assert _is_graph_enabled(ctx) is False


def test_graph_enabled_in_global_mode_when_config_on():
    ctx = _ctx(True, None, use_knowledge_graph_in_chat=True)
    assert _is_graph_enabled(ctx) is True
