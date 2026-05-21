import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from langchain_core.documents import Document

from app.services.rag.context import QueryContext
from app.services.rag.agent.handler import AgentRAGHandler
from app.services.rag.agent.nodes.grade_context import grade_context_node


@pytest.mark.asyncio
async def test_grade_context_node_preserves_metadata(monkeypatch):
    # Mock stream writer
    mock_writer = MagicMock()
    with patch("app.services.rag.agent.nodes.grade_context.get_stream_writer", return_value=mock_writer):
        # Setup observations
        # 1. Metadata tool observation (like get_book_summary or search_catalog)
        # Note: it must return a dict with result containing 'context'
        meta_obs = {
            "tool": "get_book_summary",
            "result": {
                "context": "[BookID: book1, Book: Title1] Summary context text here."
            }
        }
        # 2. Chunk documents observation
        chunk_obs = {
            "tool": "search_chunks",
            "result": {
                "chunks": [
                    {
                        "text": "Chunk content",
                        "score": 0.85,
                        "book_id": "book2",
                        "page": 25,
                        "title": "Title2",
                        "author": "Author2",
                        "volume": 1
                    }
                ]
            }
        }
        
        state = {
            "observations": [meta_obs, chunk_obs],
            "retrieved_context": "Pre-compiled context string",
            "question": "Test query"
        }
        
        res = await grade_context_node(state)
        
        # Verify both metadata block and formatted document chunk exist in graded_context
        graded_context = res["graded_context"]
        assert "[BookID: book1, Book: Title1] Summary context text here." in graded_context
        assert "Chunk content" in graded_context
        assert "BookID: book2" in graded_context
        assert "Page: 25" in graded_context


@pytest.mark.asyncio
async def test_agent_rag_handler_handle():
    handler = AgentRAGHandler()
    ctx = MagicMock()
    ctx.agent_model = "model-x"
    
    mock_graph = MagicMock()
    # Mock ainvoke to return final state
    mock_graph.ainvoke = AsyncMock(return_value={
        "final_answer": "This is the answer. [مەنبە](ref:book1:12)",
        "step_count": 3,
        "observations": [{"tool": "search_chunks"}],
        "tool_calls": [{"name": "search_chunks"}]
    })
    
    with patch("app.services.rag.agent.graph.get_or_build_graph", return_value=mock_graph), \
         patch("app.services.rag.agent.graph.build_initial_state") as mock_init, \
         patch("app.services.rag.agent.graph.populate_ctx_from_state") as mock_populate:
         
        mock_init.return_value = {}
        
        answer = await handler.handle(ctx)
        
        assert answer == "This is the answer. [مەنبە](ref:book1:12)"
        mock_graph.ainvoke.assert_called_once_with({})
        mock_populate.assert_called_once_with(ctx, mock_graph.ainvoke.return_value)


@pytest.mark.asyncio
async def test_agent_rag_handler_handle_stream():
    handler = AgentRAGHandler()
    ctx = MagicMock()
    ctx.agent_model = "model-x"
    
    mock_graph = MagicMock()
    
    # Mock astream to yield custom/values events
    async def mock_astream(*args, **kwargs):
        yield "custom", {"type": "tool_call", "name": "search_chunks"}
        yield "custom", {"type": "chunk", "text": "Answer chunk"}
        yield "values", {"final_answer": "Final", "step_count": 2}
        
    mock_graph.astream = mock_astream
    
    with patch("app.services.rag.agent.graph.get_or_build_graph", return_value=mock_graph), \
         patch("app.services.rag.agent.graph.build_initial_state") as mock_init, \
         patch("app.services.rag.agent.graph.populate_ctx_from_state") as mock_populate:
         
        mock_init.return_value = {}
        
        events = []
        async for event in handler.handle_stream(ctx):
            events.append(event)
            
        assert events == [
            {"type": "tool_call", "name": "search_chunks"},
            {"type": "chunk", "text": "Answer chunk"}
        ]
        
        # Verify terminal state populated context
        mock_populate.assert_called_once_with(ctx, {"final_answer": "Final", "step_count": 2})
