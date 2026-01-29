import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, AsyncMock

@pytest.mark.asyncio
async def test_chat_not_found(client, mock_db):
    mock_db.books.find_one.return_value = None
    payload = {
        "bookId": "nonexistent",
        "question": "What is this book about?"
    }
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_chat_success(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "book-id",
        "title": "Title",
        "tags": [],
        "results": [
            {"pageNumber": 1, "text": "Page context", "status": "completed", "embedding": [0.1]*768}
        ]
    }
    payload = {"bookId": "book-id", "question": "q"}
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Mocked Response" in response.json()["answer"]

@pytest.mark.asyncio
async def test_chat_global(client, mock_db):
    mock_db.books.find.return_value.to_list.return_value = [
        {"id": "b1", "title": "T1", "results": [{"pageNumber": 1, "text": "p1", "status": "completed", "embedding": [0.1]*768}]},
    ]
    payload = {"bookId": "global", "question": "q"}
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Mocked Response" in response.json()["answer"]

@pytest.mark.asyncio
async def test_chat_with_siblings(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "b1", "title": "T1", "tags": ["tag1"], "results": []
    }
    mock_db.books.find.return_value.to_list.side_effect = [
        [{"id": "b2", "title": "T2", "results": [{"pageNumber": 1, "text": "sib text", "status": "completed", "embedding": [0.1]*768}]}]
    ]
    payload = {"bookId": "b1", "question": "q"}
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Mocked Response" in response.json()["answer"]

@pytest.mark.asyncio
async def test_chat_current_page(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "b1", "title": "T1", "results": [
            {"pageNumber": 5, "text": "current context", "status": "completed", "embedding": [0.1]*768}
        ]
    }
    payload = {"bookId": "b1", "question": "q", "currentPage": 5}
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Mocked Response" in response.json()["answer"]

@pytest.mark.asyncio
async def test_chat_global_with_category_fallback(client, mock_db, mock_gemini):
    mock_db.books.distinct.return_value = ["History", "Science"]
    mock_db.books.find.return_value.to_list = AsyncMock(side_effect=[
        [],  # first query returns none -> triggers fallback
        [
            {"id": "b1", "title": "T1", "results": [{"pageNumber": 1, "text": "p1", "status": "completed", "embedding": [0.1]*768}]},
        ]
    ])
    
    cat_response = MagicMock()
    cat_response.text = "[]"
    fb_response = MagicMock()
    fb_response.text = '["History"]'
    mock_gemini["client"].aio.models.generate_content.side_effect = [
        cat_response,
        fb_response,
        mock_gemini["response"],
    ]
    
    payload = {
        "bookId": "global",
        "question": "q",
        "history": [{"role": "user", "text": "previous question"}]
    }
    response = await client.post("/api/chat/", json=payload)
    assert response.status_code == 200
    assert "Mocked Response" in response.json()["answer"]
