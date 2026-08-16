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
