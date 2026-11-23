import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.db.models import RAGEvaluation
from app.services.chat.context import ChatRequestDTO
from app.services.chat.orchestrator import ChatOrchestrator


@pytest.mark.asyncio
async def test_stream_response_uses_stored_sample_answer_when_evals_at_least_80_percent():
    db_session = AsyncMock()
    conv_repo = AsyncMock()
    mock_conv = MagicMock()
    mock_conv.id = "conv-sample-1"
    conv_repo.create_conversation.return_value = mock_conv

    stored_eval = RAGEvaluation(
        id=77,
        question="يۈسۈپ خاس ھاجىپ كىم؟",
        answer="يۈسۈپ خاس ھاجىپ «قۇتادغۇ بىلىك» داستانىنىڭ مۇئەللىپى. [5-بەت](ref:book-kb:5)",
        show_on_homepage=True,
        eval_status="completed",
        faithfulness_score=0.92,
        answer_relevance_score=0.88,
        context_precision_score=0.80,
        input_tokens=1800,
        output_tokens=420,
        cost_usd=0.00068,
    )

    mock_eval_repo = AsyncMock()
    mock_eval_repo.get_qualifying_sample_evaluation.return_value = stored_eval
    mock_eval_repo.resolve_sample_used_book_ids.return_value = ["book-kb"]

    dto = ChatRequestDTO(
        question="يۈسۈپ خاس ھاجىپ كىم؟",
        user_id="user-1",
        book_id="global",
        is_global=True,
        from_sample_question=True,
        sample_eval_id=77,
    )

    orchestrator = ChatOrchestrator(conversation_repo=conv_repo)

    events = []
    with (
        patch(
            "app.services.chat.orchestrator.RAGEvaluationsRepository",
            return_value=mock_eval_repo,
        ),
        patch(
            "app.services.chat.orchestrator.analyze_query_signals",
            side_effect=AssertionError("LLM signal analysis should not be called"),
        ),
        patch(
            "app.services.chat.orchestrator.build_retrieval_agent",
            side_effect=AssertionError("Retrieval agent should not be called"),
        ),
        patch(
            "app.services.chat.orchestrator.build_answer_agent",
            side_effect=AssertionError("Answer agent should not be called"),
        ),
    ):
        async for ev in orchestrator.stream_response(dto, db_session):
            events.append(ev)

    chunk_texts = [
        e["text"] for e in events if isinstance(e, dict) and e.get("type") == "chunk"
    ]
    assert "".join(chunk_texts) == stored_eval.answer

    done_events = [e for e in events if isinstance(e, dict) and e.get("type") == "done"]
    assert len(done_events) == 1
    assert done_events[0]["cached"] is True
    assert done_events[0]["conversation_id"] == "conv-sample-1"
    assert done_events[0]["used_book_ids"] == ["book-kb"]
    assert done_events[0]["eval_id"] is None
    assert done_events[0]["cost"] == {
        "input_tokens": 1800,
        "output_tokens": 420,
        "cost_usd": 0.00068,
    }
    mock_eval_repo.create_evaluation.assert_not_called()
    conv_repo.save_turn.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_response_regenerates_via_llm_when_sample_eval_below_80_percent():
    db_session = AsyncMock()
    conv_repo = AsyncMock()
    mock_conv = MagicMock()
    mock_conv.id = "conv-sample-miss"
    conv_repo.create_conversation.return_value = mock_conv
    conv_repo.get_recent_messages.return_value = []

    mock_eval_repo = AsyncMock()
    mock_eval_repo.get_qualifying_sample_evaluation.return_value = None
    mock_eval_record = MagicMock()
    mock_eval_record.id = 99
    mock_eval_record.eval_status = "skipped"
    mock_eval_repo.create_evaluation.return_value = mock_eval_record

    mock_configs_repo = AsyncMock()
    mock_configs_repo.get_value = AsyncMock(
        side_effect=lambda key, default=None: "false"
        if key == "rag_judge_scoring_enabled"
        else default
    )

    dto = ChatRequestDTO(
        question="يۈسۈپ خاس ھاجىپ كىم؟",
        user_id="user-1",
        book_id="global",
        is_global=True,
        from_sample_question=True,
        sample_eval_id=78,
    )

    orchestrator = ChatOrchestrator(conversation_repo=conv_repo)
    called_signals = {"count": 0}

    async def fake_signals(_q, _ctx):
        called_signals["count"] += 1
        return {
            "intent": "catalog",
            "catalog_subtype": "author_of",
            "has_title": True,
            "matched_books": [
                {"id": "b1", "title": "قۇتادغۇ بىلىك", "author": "يۈسۈپ خاس ھاجىپ"}
            ],
        }

    with (
        patch(
            "app.services.chat.orchestrator.RAGEvaluationsRepository",
            return_value=mock_eval_repo,
        ),
        patch(
            "app.services.chat.orchestrator.SystemConfigsRepository",
            return_value=mock_configs_repo,
        ),
        patch(
            "app.services.chat.orchestrator.get_model_pricing_from_repo",
            AsyncMock(return_value=({}, (0.0, 0.0))),
        ),
        patch("app.services.chat.orchestrator.llm_resources", MagicMock()),
        patch(
            "app.services.chat.orchestrator.analyze_query_signals",
            side_effect=fake_signals,
        ),
    ):
        events = [ev async for ev in orchestrator.stream_response(dto, db_session)]

    assert called_signals["count"] == 1
    done_events = [e for e in events if isinstance(e, dict) and e.get("type") == "done"]
    assert len(done_events) == 1
    assert not done_events[0].get("cached")
    mock_eval_repo.create_evaluation.assert_awaited_once()
