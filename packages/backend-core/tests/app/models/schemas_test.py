import pytest
from pydantic import ValidationError
from app.models.schemas import ChatRequest


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
