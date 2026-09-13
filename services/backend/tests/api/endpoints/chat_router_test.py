import sys
from pathlib import Path

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    # Force reload of api modules to avoid cache shadowing
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


@pytest.mark.asyncio
async def test_chat_endpoint_uses_chat_orchestrator():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_api
    from app.models.schemas import ChatRequest
    from app.models.user import User

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سوئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    mock_orchestrator = AsyncMock()
    mock_orchestrator.answer.return_value = {
        "answer": "جاۋاب",
        "conversation_id": "conv-1",
        "used_book_ids": ["book-abc"],
        "eval_id": 1,
    }

    with (
        patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service),
        patch(
            "api.endpoints.chat_router.ChatOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        response = await chat_with_book_api(
            req=req,
            request=MagicMock(),
            current_user=mock_user,
            session=mock_session,
        )

    assert response["answer"] == "جاۋاب"
    assert response["usage"] == mock_usage
    mock_orchestrator.answer.assert_called_once()


@pytest.mark.asyncio
async def test_chat_stream_endpoint_uses_chat_orchestrator():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_stream
    from app.models.schemas import ChatRequest
    from app.models.user import User
    import json

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سوئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    async def mock_stream_response(*args, **kwargs):
        yield {"type": "chunk", "text": "بىرىنچى"}
        yield {"type": "chunk", "text": "ئىككىنچى"}
        yield {
            "type": "done",
            "eval_id": 42,
            "conversation_id": "conv-1",
            "used_book_ids": ["book-abc"],
        }

    mock_orchestrator = MagicMock()
    mock_orchestrator.stream_response = mock_stream_response

    chunks = []
    with (
        patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service),
        patch(
            "api.endpoints.chat_router.ChatOrchestrator",
            return_value=mock_orchestrator,
        ),
    ):
        response = await chat_with_book_stream(
            req=req,
            request=MagicMock(),
            current_user=mock_user,
            session=mock_session,
        )

        async for item in response.body_iterator:
            chunks.append(item)

    assert len(chunks) > 0
    assert f"data: {json.dumps({'chunk': 'بىرىنچى'})}\n\n" in chunks
    assert f"data: {json.dumps({'chunk': 'ئىككىنچى'})}\n\n" in chunks


@pytest.mark.asyncio
async def test_delete_conversation_endpoint_calls_repository_soft_delete():
    setup_paths()
    from api.endpoints.chat_router import delete_conversation_endpoint
    from app.models.user import User

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"

    with patch(
        "app.db.repositories.conversation_repository.ConversationRepository.delete_conversation",
        AsyncMock(return_value=True),
    ) as mock_delete:
        res = await delete_conversation_endpoint(
            conversation_id="conv-456",
            current_user=mock_user,
            session=mock_session,
        )

    assert res == {"ok": True, "id": "conv-456"}
    mock_delete.assert_called_once_with("conv-456", "user-123")


@pytest.mark.asyncio
async def test_list_conversation_messages_endpoint_returns_cost_and_feedback():
    setup_paths()
    from api.endpoints.chat_router import list_conversation_messages_endpoint
    from app.models.user import User
    from datetime import datetime, timezone

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"

    mock_conv = MagicMock()
    mock_conv.id = "conv-456"
    mock_conv.user_id = "user-123"

    mock_eval = MagicMock()
    mock_eval.input_tokens = 1500
    mock_eval.output_tokens = 350
    mock_eval.cost_usd = 0.00052
    mock_eval.user_feedback = "positive"

    mock_msg1 = MagicMock()
    mock_msg1.id = "msg-1"
    mock_msg1.conversation_id = "conv-456"
    mock_msg1.role = "user"
    mock_msg1.content = "سۇئال"
    mock_msg1.agent_steps = None
    mock_msg1.used_book_ids = None
    mock_msg1.current_page = None
    mock_msg1.eval_id = None
    mock_msg1.evaluation = None
    mock_msg1.created_at = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)

    mock_msg2 = MagicMock()
    mock_msg2.id = "msg-2"
    mock_msg2.conversation_id = "conv-456"
    mock_msg2.role = "model"
    mock_msg2.content = "جاۋاب"
    mock_msg2.agent_steps = {"llm_calls": 1}
    mock_msg2.used_book_ids = None
    mock_msg2.current_page = None
    mock_msg2.eval_id = 10
    mock_msg2.evaluation = mock_eval
    mock_msg2.created_at = datetime(2026, 9, 13, 12, 0, 1, tzinfo=timezone.utc)

    with patch(
        "app.db.repositories.conversation_repository.ConversationRepository.get_conversation",
        AsyncMock(return_value=mock_conv),
    ), patch(
        "app.db.repositories.conversation_repository.ConversationRepository.get_conversation_messages",
        AsyncMock(return_value=[mock_msg1, mock_msg2]),
    ):
        res = await list_conversation_messages_endpoint(
            conversation_id="conv-456",
            limit=100,
            current_user=mock_user,
            session=mock_session,
        )

    assert "messages" in res
    assert len(res["messages"]) == 2
    assert res["messages"][0]["cost"] is None
    assert res["messages"][0]["feedback"] is None

    assert res["messages"][1]["cost"] == {
        "inputTokens": 1500,
        "outputTokens": 350,
        "costUsd": 0.00052,
    }
    assert res["messages"][1]["feedback"] == "positive"
    assert res["messages"][1]["evalId"] == 10
