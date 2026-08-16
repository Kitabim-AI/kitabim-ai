import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import Conversation
from app.services.chat.context import ChatRequestDTO
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.rag.utils import entity_matches_question


def test_entity_matches_question_with_quoted_single_word_title():
    # Quoted single-word title should match even without a follower word
    assert entity_matches_question("بابۇرنامە", "«بابۇرنامە» تېمىسى نېمە؟") is True
    assert (
        entity_matches_question(
            "سۇنغان قىلىچ", "«سۇنغان قىلىچ» دا ئابلىز قانداق ئوبراز؟"
        )
        is True
    )


@pytest.mark.asyncio
async def test_orchestrator_catalog_first_phrase_suppression():
    orchestrator = ChatOrchestrator()
    request_dto = ChatRequestDTO(
        user_id="test-user",
        question="«سۇنغان قىلىچ» دا ئابلىز قانداق ئوبراز؟",
        is_global=True,
        exact_phrase=False,
    )
    db_session = MagicMock()
    mock_conv = Conversation(id="conv-1", user_id="test-user", title="test")

    mock_books = [
        {"id": "book-123", "title": "سۇنغان قىلىچ", "author": "ئاپتور", "volume": None}
    ]

    with patch(
        "app.services.chat.orchestrator.ConversationRepository.create_conversation",
        new=AsyncMock(return_value=mock_conv),
    ), patch(
        "app.services.chat.orchestrator.ConversationRepository.get_recent_messages",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.chat.orchestrator.ConversationRepository.add_message",
        new=AsyncMock(),
    ), patch(
        "app.services.chat.orchestrator.SystemConfigsRepository.get_value",
        new=AsyncMock(return_value="gemini-2.5-flash"),
    ), patch(
        "app.services.chat.orchestrator.find_books_by_title_in_question",
        new=AsyncMock(return_value=mock_books),
    ) as mock_find_books, patch(
        "app.services.chat.orchestrator.analyze_query_signals",
        new=AsyncMock(return_value={"intent": "open"}),
    ), patch(
        "app.services.chat.orchestrator.build_retrieval_agent"
    ) as mock_build_agent, patch(
        "app.services.chat.orchestrator.run_exact_phrase_retrieval"
    ) as mock_run_exact:
        mock_agent = MagicMock()
        mock_build_agent.return_value = mock_agent

        events = []
        async for event in orchestrator.stream_response(request_dto, db_session):
            events.append(event)
            if event.get("type") == "planning":
                break

        mock_find_books.assert_called_once()
        mock_run_exact.assert_not_called()
        assert any(
            e.get("type") == "planning" and e.get("intent") == "open" for e in events
        )


@pytest.mark.asyncio
async def test_orchestrator_catalog_first_fallback_to_phrase_when_no_book_found():
    orchestrator = ChatOrchestrator()
    request_dto = ChatRequestDTO(
        user_id="test-user",
        question="«ئەلپ ئەر تونغا» ئاتالغۇسى",
        is_global=True,
        exact_phrase=False,
    )
    db_session = MagicMock()
    mock_conv = Conversation(id="conv-1", user_id="test-user", title="test")

    with patch(
        "app.services.chat.orchestrator.ConversationRepository.create_conversation",
        new=AsyncMock(return_value=mock_conv),
    ), patch(
        "app.services.chat.orchestrator.ConversationRepository.get_recent_messages",
        new=AsyncMock(return_value=[]),
    ), patch(
        "app.services.chat.orchestrator.ConversationRepository.add_message",
        new=AsyncMock(),
    ), patch(
        "app.services.chat.orchestrator.SystemConfigsRepository.get_value",
        new=AsyncMock(return_value="10"),
    ), patch(
        "app.services.chat.orchestrator.find_books_by_title_in_question",
        new=AsyncMock(return_value=None),
    ) as mock_find_books, patch(
        "app.services.chat.orchestrator.run_exact_phrase_retrieval",
        new=AsyncMock(
            return_value=(
                [],
                {
                    "tool": "exact_phrase_search",
                    "result": {"ok": True, "data": {"chunks": []}, "found_count": 0},
                },
            )
        ),
    ) as mock_run_exact:
        events = []
        async for event in orchestrator.stream_response(request_dto, db_session):
            events.append(event)
            if event.get("type") == "tool_result":
                break

        mock_find_books.assert_called_once()
        mock_run_exact.assert_called_once()
        assert any(
            e.get("type") == "planning" and e.get("intent") == "exact_phrase"
            for e in events
        )
