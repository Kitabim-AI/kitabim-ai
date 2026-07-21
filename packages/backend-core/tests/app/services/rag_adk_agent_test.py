from app.services.rag.agent.adk_agent import build_rag_agent


def _tool_names(agent):
    return {tool.__name__ for tool in agent.tools}


def test_knowledge_graph_tool_not_offered():
    agent = build_rag_agent("gemini-2.0-flash")
    assert "query_knowledge_graph" not in _tool_names(agent)


def test_lookup_synonyms_tool_included():
    agent = build_rag_agent("gemini-2.0-flash")
    assert "lookup_synonyms" in _tool_names(agent)
