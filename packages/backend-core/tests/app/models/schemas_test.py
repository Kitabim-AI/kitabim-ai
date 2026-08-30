import pytest
from datetime import datetime, timezone
from pydantic import ValidationError
from app.models.schemas import ChatRequest, RagQuestionAdmin, OcrPageInput
from app.db.models import RAGEvaluation


def test_ocr_page_input_accepts_camel_case_payload():
    page = OcrPageInput.model_validate(
        {"pageNumber": 3, "text": "سالام دۇنيا", "isToc": True}
    )
    assert page.page_number == 3
    assert page.text == "سالام دۇنيا"
    assert page.is_toc is True


def test_ocr_page_input_is_toc_defaults_false():
    page = OcrPageInput.model_validate({"pageNumber": 1, "text": ""})
    assert page.is_toc is False


def test_chat_request_validation_valid():
    # Valid Uyghur question
    req = ChatRequest(book_id="book-abc", question="سوئال", history=[])
    assert req.question == "سوئال"


def test_chat_request_validation_too_long():
    # 501 character question
    long_question = "س" * 501
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(book_id="book-abc", question=long_question, history=[])
    assert "Question is too long" in str(exc_info.value)


def test_chat_request_validation_invalid_language():
    # English question (no Arabic script characters)
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(book_id="book-abc", question="What is the summary?", history=[])
    assert "Question must be in Uyghur (Arabic script)" in str(exc_info.value)


def test_rag_question_admin_includes_eval_scores():
    """RagQuestionAdmin must surface eval_status and the three judge scores
    so the admin Questions tab can show per-turn evaluation quality."""
    row = RAGEvaluation(
        id=1,
        question="سوئال",
        is_global=True,
        is_first_turn=True,
        show_on_homepage=False,
        eval_status="completed",
        faithfulness_score=0.9,
        answer_relevance_score=0.8,
        context_precision_score=0.7,
        ts=datetime.now(timezone.utc),
    )
    admin_view = RagQuestionAdmin.model_validate(row)

    assert admin_view.eval_status == "completed"
    assert admin_view.faithfulness_score == 0.9
    assert admin_view.answer_relevance_score == 0.8
    assert admin_view.context_precision_score == 0.7

    dumped = admin_view.model_dump(by_alias=True)
    assert dumped["evalStatus"] == "completed"
    assert dumped["faithfulnessScore"] == 0.9
    assert dumped["answerRelevanceScore"] == 0.8
    assert dumped["contextPrecisionScore"] == 0.7


def test_rag_question_admin_scores_default_to_none_for_unscored_row():
    row = RAGEvaluation(
        id=2,
        question="سوئال",
        is_global=True,
        is_first_turn=False,
        show_on_homepage=False,
        eval_status="queued",
        ts=datetime.now(timezone.utc),
    )
    admin_view = RagQuestionAdmin.model_validate(row)

    assert admin_view.eval_status == "queued"
    assert admin_view.faithfulness_score is None
    assert admin_view.answer_relevance_score is None
    assert admin_view.context_precision_score is None


def test_rag_question_admin_includes_book_title():
    row = RAGEvaluation(
        id=3,
        question="سوئال",
        is_global=False,
        book_id="book-123",
        is_first_turn=True,
        show_on_homepage=False,
        eval_status="completed",
        ts=datetime.now(timezone.utc),
    )
    row.book_title = "ئېچىلغان بولاق"  # type: ignore[attr-defined]
    admin_view = RagQuestionAdmin.model_validate(row)

    assert admin_view.book_id == "book-123"
    assert admin_view.book_title == "ئېچىلغان بولاق"
    dumped = admin_view.model_dump(by_alias=True)
    assert dumped["bookTitle"] == "ئېچىلغان بولاق"
