import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

@pytest.mark.asyncio
async def test_get_books_empty(client, mock_db):
    # Setup mock
    mock_db.books.count_documents.return_value = 0
    mock_db.books.find.return_value.to_list.return_value = []
    
    response = await client.get("/api/books/")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["books"] == []

@pytest.mark.asyncio
async def test_get_book_found(client, mock_db):
    mock_book = {
        "id": "test-id",
        "title": "Test Book",
        "author": "Author",
        "totalPages": 10,
        "results": [],
        "status": "ready",
        "contentHash": "hash",
        "uploadDate": datetime.now().isoformat()
    }
    mock_db.books.find_one.return_value = mock_book
    
    response = await client.get("/api/books/test-id")
    assert response.status_code == 200
    assert response.json()["title"] == "Test Book"

@pytest.mark.asyncio
async def test_get_book_not_found(client, mock_db):
    mock_db.books.find_one.return_value = None
    response = await client.get("/api/books/unknown")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_book(client, mock_db):
    mock_db.books.delete_one.return_value = MagicMock(deleted_count=1)
    
    with patch("os.path.exists", return_value=False):
        response = await client.delete("/api/books/test-id")
        assert response.status_code == 200
        assert response.json()["status"] == "deleted"

@pytest.mark.asyncio
async def test_upload_pdf_wrong_extension(client):
    files = {'file': ('test.txt', b'content', 'text/plain')}
    response = await client.post("/api/books/upload/", files=files)
    assert response.status_code == 400
    assert "Only PDF files are allowed" in response.json()["detail"]

@pytest.mark.asyncio
async def test_reprocess_book(client, mock_db):
    mock_db.books.find_one.return_value = {"id": "test-id", "status": "ready"}
    response = await client.post("/api/books/test-id/reprocess/")
    assert response.status_code == 200
    assert response.json()["status"] == "reprocessing_started"

@pytest.mark.asyncio
async def test_reset_page(client, mock_db):
    response = await client.post("/api/books/test-id/pages/1/reset/")
    assert response.status_code == 200
    assert response.json()["status"] == "page_reset_started"

@pytest.mark.asyncio
async def test_update_page_text(client, mock_db):
    payload = {"text": "new text"}
    response = await client.post("/api/books/test-id/pages/1/update/", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "page_updated"

@pytest.mark.asyncio
async def test_create_book(client, mock_db):
    from app.models.schemas import Book
    book_data = {
        "id": "new-id",
        "contentHash": "hash",
        "title": "New",
        "author": "Me",
        "totalPages": 0,
        "results": [],
        "status": "processing",
        "uploadDate": datetime.now().isoformat()
    }
    response = await client.post("/api/books/", json=book_data)
    assert response.status_code == 200
    assert response.json()["status"] == "success"

@pytest.mark.asyncio
async def test_get_book_by_hash(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "test-id", 
        "contentHash": "hash",
        "title": "Title",
        "author": "Author",
        "totalPages": 10,
        "results": [],
        "status": "ready",
        "uploadDate": datetime.now().isoformat()
    }
    response = await client.get("/api/books/hash/hash")
    assert response.status_code == 200
    assert response.json()["contentHash"] == "hash"

@pytest.mark.asyncio
async def test_update_book_details(client, mock_db):
    mock_db.books.update_one.return_value = MagicMock(matched_count=1, modified_count=1)
    payload = {"author": "New Author"}
    response = await client.put("/api/books/test-id", json=payload)
    assert response.status_code == 200
    assert response.json()["status"] == "updated"

@pytest.mark.asyncio
async def test_upload_pdf_success(client, mock_db):
    mock_db.books.find_one.return_value = None # Not existing
    files = {'file': ('test.pdf', b'%PDF-1.4 content', 'application/pdf')}
    
    with patch("os.path.exists", return_value=True), \
         patch("builtins.open", MagicMock()), \
         patch("app.api.endpoints.books.process_pdf_task"):
        response = await client.post("/api/books/upload/", files=files)
        assert response.status_code == 200
        assert response.json()["status"] == "started"

@pytest.mark.asyncio
async def test_get_books_formatting(client, mock_db):
    # Test that _id is formatted to id
    mock_db.books.count_documents.return_value = 1
    mock_db.books.find.return_value.to_list.return_value = [
        {
            "_id": "real-id", 
            "title": "T", 
            "author": "A", 
            "uploadDate": datetime.now(),
            "contentHash": "h",
            "totalPages": 1,
            "results": [],
            "status": "ready"
        }
    ]
    response = await client.get("/api/books/")
    data = response.json()
    assert data["books"][0]["id"] == "real-id"

@pytest.mark.asyncio
async def test_upload_pdf_existing(client, mock_db):
    mock_db.books.find_one.return_value = {"id": "existing-id"}
    files = {'file': ('test.pdf', b'%PDF-1.4 content', 'application/pdf')}
    response = await client.post("/api/books/upload/", files=files)
    assert response.status_code == 200
    assert response.json()["status"] == "existing"

@pytest.mark.asyncio
async def test_update_book_not_found(client, mock_db):
    mock_db.books.update_one.return_value = MagicMock(matched_count=0)
    response = await client.put("/api/books/unknown", json={})
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_delete_not_found(client, mock_db):
    mock_db.books.delete_one.return_value = MagicMock(deleted_count=0)
    response = await client.delete("/api/books/unknown")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_reprocess_already_processing(client, mock_db):
    mock_db.books.find_one.return_value = {"id": "id", "status": "processing"}
    response = await client.post("/api/books/id/reprocess/")
    assert response.status_code == 200
    assert response.json()["status"] == "already_processing"

@pytest.mark.asyncio
async def test_get_book_retrofit(client, mock_db):
    from bson import ObjectId
    oid = ObjectId()
    mock_db.books.find_one.return_value = {"_id": oid, "title": "T", "author": "A", "uploadDate": datetime.now(), "contentHash": "h", "totalPages": 1, "results": [], "status": "ready"}
    response = await client.get(f"/api/books/{str(oid)}")
    assert response.status_code == 200
    assert response.json()["id"] == str(oid)
