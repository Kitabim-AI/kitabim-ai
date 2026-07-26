"""End-to-end test: /api/chat/stream with use_deterministic_router=true,
running the REAL RAGService -> HandlerRegistry -> DeterministicRAGHandler
-> ADK graph chain (only external boundaries mocked: system_configs DB
reads, LLM calls, tool dispatch, DB session). Proves the tool_call/
tool_result progress events produced by the ADK graph's Content-bridge
(see graph_router.py) survive the full call chain out to the SSE response
body, not just the handler-level unit tests.
"""

import json
import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


# system_configs are read in this exact order: first the chat_router's own
# "use_adk_chat_v2" feature-flag check (returning "false" keeps this test on
# the legacy RAGService path), then by RAGService._build_context()
# (chat/embedding/agent model, agent_max_steps, agent_enough_chunks,
# use_deterministic_router) and then once more by _record_eval()
# (rag_eval_enabled). use_deterministic_router="true" routes to
# DeterministicRAGHandler instead of LLMRoutedRAGHandler; rag_eval_enabled="false"
# short-circuits eval recording (no extra DB calls).
_CONFIG_VALUES = [
    "false",
    "chat-model",
    "emb-model",
    "agent-model",
    "6",
    "8",
    "true",
    "false",
]


@pytest.mark.asyncio
async def test_chat_stream_with_deterministic_router_surfaces_tool_events():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_stream
    from app.models.schemas import ChatRequest
    from app.models.user import User
    from app.services.rag_service import RAGService

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(
        book_id="global", question="ئېگىز تاغ سىرتىدا نېمە بار؟", history=[]
    )

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    mock_chain = MagicMock()

    async def fake_astream(_payload):
        yield "Hello"
        yield " world"

    mock_chain.astream = fake_astream

    async def mock_get_value(key, default=None):
        return _CONFIG_VALUES.pop(0)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value='{"intent": "passage", "is_composite": false}'
    )

    async def mock_dispatch(tool_name, tool_args, ctx):
        assert tool_name == "search_chunks"
        return {
            "ok": True,
            "chunks": [{"text": f"chunk {i}", "score": 0.9} for i in range(4)],
            "found_count": 4,
        }

    with (
        patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service),
        patch(
            "app.db.repositories.system_configs_repository.SystemConfigsRepository.get_value",
            side_effect=mock_get_value,
        ),
        patch("app.services.rag_service.llm_resources") as mock_resources,
        patch(
            "app.services.rag.agent.deterministic_handler.find_books_by_title_in_db",
            return_value=[],
        ),
        patch(
            "app.db.repositories.books_repository.BooksRepository.find_books_by_author_in_question",
            return_value=[],
        ),
        patch(
            "app.services.rag.agent.deterministic_handler.build_text_llm",
            return_value=mock_llm,
        ),
        patch(
            "app.services.rag.agent.deterministic_handler._dispatch_tool_with_retry",
            side_effect=mock_dispatch,
        ),
    ):
        mock_resources.get_rag_chain.return_value = mock_chain
        mock_resources.get_rewrite_chain.return_value = MagicMock()
        mock_resources.get_embeddings.return_value = MagicMock()

        response = await chat_with_book_stream(
            req=req,
            request=MagicMock(),
            current_user=mock_user,
            session=mock_session,
            rag_service=RAGService(),
        )

        events = []
        async for raw in response.body_iterator:
            assert raw.startswith("data: ")
            events.append(json.loads(raw[len("data: ") : -2]))

    event_types = [e.get("type") for e in events if "type" in e]
    assert "planning" in event_types
    assert "tool_call" in event_types
    assert "tool_result" in event_types
    assert "answer_start" in event_types
    assert "answer_end" in event_types

    tool_call = next(e for e in events if e.get("type") == "tool_call")
    assert tool_call["tool"] == "search_chunks"
    tool_result = next(e for e in events if e.get("type") == "tool_result")
    assert tool_result["tool"] == "search_chunks"
    assert tool_result["found"] == 4

    # Answer tokens streamed through from the (mocked) rag_chain.
    chunks = "".join(e["chunk"] for e in events if "chunk" in e)
    assert "Hello" in chunks
    assert "world" in chunks

    # Final SSE "done" event still gets sent after the graph-backed stream.
    assert any(e.get("done") for e in events)
