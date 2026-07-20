from app.services.rag.agent.adk_agent import build_rag_agent


def _tool_names(agent):
    return {tool.__name__ for tool in agent.tools}


def test_knowledge_graph_tool_included_by_default():
    agent = build_rag_agent("gemini-2.0-flash")
    assert "query_knowledge_graph" in _tool_names(agent)


def test_knowledge_graph_tool_excluded_when_graph_disabled():
    """The tool must not even be offered to the agent when the graph feature
    is disabled — relying on a prompt instruction alone lets the LLM call it
    anyway and waste a tool round-trip."""
    agent = build_rag_agent("gemini-2.0-flash", graph_enabled=False)
    assert "query_knowledge_graph" not in _tool_names(agent)


def test_other_tools_unaffected_by_graph_flag():
    agent = build_rag_agent("gemini-2.0-flash", graph_enabled=False)
    assert "search_chunks" in _tool_names(agent)
