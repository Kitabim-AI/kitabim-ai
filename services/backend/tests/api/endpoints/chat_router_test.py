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
async def test_chat_endpoint_uses_injected_rag_service():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_api
    from app.models.schemas import ChatRequest
    from app.models.user import User

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سۇئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    mock_rag_service = AsyncMock()
    mock_rag_service.answer_question.return_value = "جاۋاب"

    with patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service):
        response = await chat_with_book_api(
            req=req,
            current_user=mock_user,
            session=mock_session,
            rag_service=mock_rag_service,
        )

    assert response["answer"] == "جاۋاب"
    assert response["usage"] == mock_usage
    mock_rag_service.answer_question.assert_called_once_with(
        req, mock_session, user_id="user-123"
    )


@pytest.mark.asyncio
async def test_chat_stream_endpoint_uses_injected_rag_service():
    setup_paths()
    from api.endpoints.chat_router import chat_with_book_stream
    from app.models.schemas import ChatRequest
    from app.models.user import User
    import json

    mock_session = AsyncMock()
    mock_user = MagicMock(spec=User)
    mock_user.id = "user-123"
    mock_user.role = "reader"

    req = ChatRequest(book_id="book-abc", question="سۇئال", history=[])

    mock_usage = {"usage": 1, "limit": 10, "has_reached_limit": False}
    mock_limit_service = AsyncMock()
    mock_limit_service.get_user_usage_status.return_value = mock_usage
    mock_limit_service.increment_usage = AsyncMock()

    # Mock async generator for stream
    async def mock_stream_chunks(*args, **kwargs):
        # We need to make sure the mutable metadata_out dictionary gets populated
        if "metadata_out" in kwargs and kwargs["metadata_out"] is not None:
            kwargs["metadata_out"]["used_book_ids"] = ["book-abc"]
            kwargs["metadata_out"]["eval_id"] = 42
        yield "بىرىنچى"
        yield "ئىككىنچى"

    mock_rag_service = MagicMock()
    mock_rag_service.answer_question_stream = mock_stream_chunks

    with patch("api.endpoints.chat_router.chat_limit_service", mock_limit_service):
        response = await chat_with_book_stream(
            req=req,
            current_user=mock_user,
            session=mock_session,
            rag_service=mock_rag_service,
        )

    # Read events from response body
    chunks = []
    async for item in response.body_iterator:
        chunks.append(item)

    assert len(chunks) > 0
    # The first event is the first yielded chunk formatted as SSE
    assert f"data: {json.dumps({'chunk': 'بىرىنچى'})}\n\n" in chunks
    assert f"data: {json.dumps({'chunk': 'ئىككىنچى'})}\n\n" in chunks
