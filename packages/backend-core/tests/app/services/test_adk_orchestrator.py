"""Tests for ChatOrchestrator and ADK chat pipeline"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import Conversation
from app.services.chat.context import ChatRequestDTO
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.chat.retrieval_agent import build_retrieval_agent
from app.services.chat.answer_agent import build_answer_agent


def test_chat_request_dto_immutability():
    dto = ChatRequestDTO(
        question="يۇنۇسخان كىم؟",
        user_id="user-123",
        book_id="book-abc",
        is_global=False,
    )
    assert dto.question == "يۇنۇسخان كىم؟"
    assert dto.user_id == "user-123"
    assert dto.book_id == "book-abc"
    assert dto.is_global is False

    with pytest.raises(Exception):
        dto.question = "Another question"


def test_build_agents():
    retrieval_agent = build_retrieval_agent(model="gemini-2.5-flash")
    assert retrieval_agent.name == "KitabimRetrievalAgent"
    assert len(retrieval_agent.tools) > 0

    answer_agent = build_answer_agent(
        model="gemini-2.5-flash",
        graded_context="Sample context content",
    )
    assert answer_agent.name == "KitabimAnswerAgent"
    assert len(answer_agent.tools) == 0


@pytest.mark.asyncio
async def test_orchestrator_initialization():
    orchestrator = ChatOrchestrator(session_service=None)
    assert orchestrator.session_service is None


async def _empty_async_gen():
    return
    yield  # pragma: no cover - makes this an async generator


def _mock_adk_session():
    session = MagicMock()
    session.state = {}
    return session


@pytest.mark.asyncio
async def test_stream_response_builds_query_context_and_persists_turn():
    """Regression test: stream_response used to crash building QueryContext
    because required dataclass fields (history, book, persona_prompt, ...)
    were never supplied. This exercises the full happy path with ADK/LLM
    boundaries mocked out."""
    db_session = AsyncMock()

    conv_repo = AsyncMock()
    conv_repo.get_conversation.return_value = None
    conv_repo.create_conversation.return_value = Conversation(
        id="conv-1", user_id="user-1", book_id=None, is_global=True
    )
    conv_repo.get_recent_messages.return_value = []
    conv_repo.save_turn.return_value = (MagicMock(), MagicMock())

    eval_repo = AsyncMock()
    eval_repo.create_evaluation.return_value = MagicMock(id=42)

    inmemory_session_service = MagicMock()
    inmemory_session_service.create_session = AsyncMock(
        return_value=_mock_adk_session()
    )

    retrieval_runner = MagicMock()
    retrieval_runner.run_async = MagicMock(return_value=_empty_async_gen())

    answer_runner = MagicMock()
    answer_runner.run_async = MagicMock(return_value=_empty_async_gen())

    deterministic_handler = MagicMock()
    deterministic_handler._llm_analyze_query = AsyncMock(
        return_value={"intent": "open"}
    )

    mock_configs_repo = AsyncMock()
    mock_configs_repo.get_value = AsyncMock(return_value="text-embedding-004")

    with patch(
        "app.services.chat.orchestrator.ConversationRepository",
        return_value=conv_repo,
    ), patch(
        "app.services.chat.orchestrator.SystemConfigsRepository",
        return_value=mock_configs_repo,
    ), patch(
        "app.services.chat.orchestrator.RAGEvaluationsRepository",
        return_value=eval_repo,
    ), patch(
        "app.services.chat.orchestrator.DeterministicRAGHandler",
        return_value=deterministic_handler,
    ), patch(
        "app.services.chat.orchestrator.InMemorySessionService",
        return_value=inmemory_session_service,
    ), patch(
        "app.services.chat.orchestrator.Runner", return_value=retrieval_runner
    ), patch(
        "app.services.chat.orchestrator.InMemoryRunner", return_value=answer_runner
    ), patch(
        "app.services.chat.orchestrator._extract_used_book_ids", return_value=[]
    ), patch(
        "app.services.chat.orchestrator._grade_context",
        return_value=("", 0, 0),
    ), patch(
        "app.services.chat.orchestrator.build_retrieval_agent",
        return_value=MagicMock(),
    ), patch(
        "app.services.chat.orchestrator.build_answer_agent", return_value=MagicMock()
    ), patch(
        "app.services.chat.orchestrator.fix_malformed_citations",
        side_effect=lambda text: text,
    ):
        orchestrator = ChatOrchestrator(session_service=None)
        dto = ChatRequestDTO(
            question="يۇنۇسخان كىم؟",
            user_id="user-1",
            book_id=None,
            is_global=True,
        )

        events = [
            event async for event in orchestrator.stream_response(dto, db_session)
        ]

    done_events = [e for e in events if isinstance(e, dict) and e.get("type") == "done"]
    assert len(done_events) == 1
    assert done_events[0]["conversation_id"] == "conv-1"
    assert done_events[0]["eval_id"] == 42

    conv_repo.create_conversation.assert_awaited_once()
    conv_repo.save_turn.assert_awaited_once()
    save_turn_kwargs = conv_repo.save_turn.await_args.kwargs
    assert save_turn_kwargs["conversation_id"] == "conv-1"
    assert save_turn_kwargs["question"] == "يۇنۇسخان كىم؟"


@pytest.mark.asyncio
async def test_stream_response_reader_mode_sends_context_block_to_retrieval_agent():
    """Regression test: the retrieval agent's AGENT_SYSTEM_PROMPT routing rules
    (e.g. "if [Context] provides a current book_id, call get_book_summary
    directly") only fire when the user turn actually contains a [Context]
    block. stream_response used to send the bare question, so the agent had
    no way to know it was in reader mode and would call unnecessary
    book-discovery tools first."""
    db_session = AsyncMock()

    conv_repo = AsyncMock()
    conv_repo.get_conversation.return_value = None
    conv_repo.create_conversation.return_value = Conversation(
        id="conv-1", user_id="user-1", book_id="book-abc", is_global=False
    )
    conv_repo.get_recent_messages.return_value = []
    conv_repo.save_turn.return_value = (MagicMock(), MagicMock())

    eval_repo = AsyncMock()
    eval_repo.create_evaluation.return_value = MagicMock(id=42)

    inmemory_session_service = MagicMock()
    inmemory_session_service.create_session = AsyncMock(
        return_value=_mock_adk_session()
    )

    retrieval_runner = MagicMock()
    retrieval_runner.run_async = MagicMock(return_value=_empty_async_gen())

    answer_runner = MagicMock()
    answer_runner.run_async = MagicMock(return_value=_empty_async_gen())

    deterministic_handler = MagicMock()
    deterministic_handler._llm_analyze_query = AsyncMock(
        return_value={"intent": "summary"}
    )

    mock_configs_repo = AsyncMock()
    mock_configs_repo.get_value = AsyncMock(return_value="text-embedding-004")

    mock_book = MagicMock(title="ئانا يۇرت", author="زوردۇن سابىر", volume=1)
    mock_books_repo = AsyncMock()
    mock_books_repo.get.return_value = mock_book

    with patch(
        "app.services.chat.orchestrator.ConversationRepository",
        return_value=conv_repo,
    ), patch(
        "app.services.chat.orchestrator.SystemConfigsRepository",
        return_value=mock_configs_repo,
    ), patch(
        "app.services.chat.orchestrator.RAGEvaluationsRepository",
        return_value=eval_repo,
    ), patch(
        "app.services.chat.orchestrator.BooksRepository",
        return_value=mock_books_repo,
    ), patch(
        "app.services.chat.orchestrator.DeterministicRAGHandler",
        return_value=deterministic_handler,
    ), patch(
        "app.services.chat.orchestrator.InMemorySessionService",
        return_value=inmemory_session_service,
    ), patch(
        "app.services.chat.orchestrator.Runner", return_value=retrieval_runner
    ), patch(
        "app.services.chat.orchestrator.InMemoryRunner", return_value=answer_runner
    ), patch(
        "app.services.chat.orchestrator._extract_used_book_ids", return_value=[]
    ), patch(
        "app.services.chat.orchestrator._grade_context",
        return_value=("", 0, 0),
    ), patch(
        "app.services.chat.orchestrator.build_retrieval_agent",
        return_value=MagicMock(),
    ), patch(
        "app.services.chat.orchestrator.build_answer_agent", return_value=MagicMock()
    ), patch(
        "app.services.chat.orchestrator.fix_malformed_citations",
        side_effect=lambda text: text,
    ):
        orchestrator = ChatOrchestrator(session_service=None)
        dto = ChatRequestDTO(
            question="كىتابنىڭ ئاساسى مەزمۇنى",
            user_id="user-1",
            book_id="book-abc",
            is_global=False,
            current_page=42,
        )

        [event async for event in orchestrator.stream_response(dto, db_session)]

    retrieval_message = retrieval_runner.run_async.call_args.kwargs["new_message"]
    retrieval_text = retrieval_message.parts[0].text
    assert "[Context]" in retrieval_text
    assert "Current book:" in retrieval_text
    assert "book-abc" in retrieval_text
    assert "Current page: 42" in retrieval_text
    assert retrieval_text.endswith("[Question]\nكىتابنىڭ ئاساسى مەزمۇنى")
