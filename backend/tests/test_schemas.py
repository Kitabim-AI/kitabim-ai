import pytest
from pydantic import ValidationError
from datetime import datetime
from app.models.schemas import Book, ExtractionResult

def test_extraction_result_valid():
    res = ExtractionResult(pageNumber=1, status="pending")
    assert res.pageNumber == 1
    assert res.status == "pending"
    assert res.text is None

def test_book_valid():
    book = Book(
        id="id123",
        contentHash="hash",
        title="Title",
        author="Author",
        totalPages=1,
        results=[],
        status="processing",
        uploadDate=datetime.now()
    )
    assert book.id == "id123"
    assert book.status == "processing"

def test_book_invalid():
    with pytest.raises(ValidationError):
        # Missing required fields
        Book(id="123")
