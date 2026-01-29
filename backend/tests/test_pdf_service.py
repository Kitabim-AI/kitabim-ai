import pytest
import os
from unittest.mock import MagicMock, patch
from app.services.pdf_service import process_pdf_task, RUNNING_TASKS

@pytest.mark.asyncio
@patch("app.services.pdf_service.fitz.open")
async def test_process_pdf_task_not_found(mock_fitz, mock_db):
    # Test file not found
    with patch("os.path.exists", return_value=False):
        await process_pdf_task("test-id")
        mock_db.books.update_one.assert_called_with(
            {"id": "test-id"}, {"$set": {"status": "error"}}
        )

@pytest.mark.asyncio
@patch("app.services.pdf_service.fitz.open")
async def test_process_pdf_task_success(mock_fitz, mock_db):
    book_id = "test-id"
    # Setup mocks
    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_fitz.return_value = mock_doc
    
    mock_db.books.find_one.side_effect = [
        {"id": book_id, "results": [], "status": "processing"}, # first call (L34)
        {"id": book_id, "results": [{"pageNumber": 1, "status": "pending"}], "status": "processing"}, # inside process_page (L75)
        {"id": book_id, "results": [{"pageNumber": 1, "status": "completed", "text": "text"}], "status": "processing"}, # after loop (L127)
        {"id": book_id, "results": [{"pageNumber": 1, "status": "completed", "text": "text"}], "status": "processing"} # final build (L148)
    ]
    
    # Mock os.path.exists for both PDF and cover
    def exists_side_effect(path):
        if path.endswith(".pdf"): return True
        if path.endswith(".jpg"): return False
        return False
    
    with patch("os.path.exists", side_effect=exists_side_effect):
        await process_pdf_task(book_id)
    
    # Check if 'ready' status was eventually set
    calls = [call.args[1].get("$set", {}).get("status") for call in mock_db.books.update_one.call_args_list if len(call.args) > 1]
    assert "ready" in calls

@pytest.mark.asyncio
@patch("app.services.pdf_service.fitz.open")
async def test_process_pdf_task_ocr_error(mock_fitz, mock_db, mock_gemini):
    book_id = "test-id"
    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_fitz.return_value = mock_doc
    
    mock_db.books.find_one.side_effect = [
        {"id": book_id, "results": [], "status": "processing"}, # first call
        {"id": book_id, "results": [{"pageNumber": 1, "status": "pending"}], "status": "processing"}, # inside process_page
        {"id": book_id, "results": [{"pageNumber": 1, "status": "error", "text": "[OCR Error]"}], "status": "processing"}, # after loop
        {"id": book_id, "results": [{"pageNumber": 1, "status": "error", "text": "[OCR Error]"}], "status": "processing"} # final build
    ]
    
    # Mock AI model to raise exception
    mock_gemini["client"].aio.models.generate_content.side_effect = Exception("AI Failure")
    
    with patch("os.path.exists", return_value=True):
        await process_pdf_task(book_id)
    
    # Status should be error if any page failed
    calls = [call.args[1].get("$set", {}).get("status") for call in mock_db.books.update_one.call_args_list if len(call.args) > 1]
    assert "error" in calls

@pytest.mark.asyncio
async def test_process_pdf_task_duplicate_skips(mock_db):
    book_id = "dup-id"
    RUNNING_TASKS.add(book_id)
    try:
        await process_pdf_task(book_id)
    finally:
        RUNNING_TASKS.discard(book_id)
    assert mock_db.books.find_one.await_count == 0

@pytest.mark.asyncio
@patch("app.services.pdf_service.fitz.open")
async def test_process_pdf_task_book_not_found(mock_fitz, mock_db):
    book_id = "missing-book"
    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_fitz.return_value = mock_doc
    mock_db.books.find_one.return_value = None
    
    with patch("os.path.exists", return_value=True):
        await process_pdf_task(book_id)
    
    mock_db.books.find_one.assert_awaited()

@pytest.mark.asyncio
@patch("app.services.pdf_service.fitz.open")
async def test_process_pdf_task_no_pages_to_process(mock_fitz, mock_db):
    book_id = "ready-book"
    mock_doc = MagicMock()
    mock_doc.page_count = 1
    mock_fitz.return_value = mock_doc
    mock_db.books.find_one.return_value = {
        "id": book_id,
        "results": [{"pageNumber": 1, "status": "completed", "text": "text", "embedding": [0.1]}],
        "status": "processing"
    }
    
    def exists_side_effect(path):
        if path.endswith(".pdf"):
            return True
        if path.endswith(".jpg"):
            return True
        return False
    
    with patch("os.path.exists", side_effect=exists_side_effect):
        await process_pdf_task(book_id)
    
    calls = [call.args[1].get("$set", {}).get("status") for call in mock_db.books.update_one.call_args_list if len(call.args) > 1]
    assert "ready" in calls
