import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime
from app.services.spell_check_service import PageSpellCheck, SpellCorrection
import sys

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

@pytest.mark.asyncio
async def test_get_books_group_by_work_sort(client, mock_db):
    mock_db.books.count_documents.side_effect = [4, 2]
    mock_db.books.find.return_value.to_list.return_value = [
        {
            "_id": "work-new",
            "title": "Work",
            "author": "A",
            "uploadDate": "2024-01-10T00:00:00Z",
            "contentHash": "h1",
            "totalPages": 1,
            "results": [],
            "status": "ready"
        },
        {
            "id": "work-old",
            "title": "Work",
            "author": "A",
            "uploadDate": datetime(2024, 1, 9),
            "contentHash": "h2",
            "totalPages": 1,
            "results": [],
            "status": "ready"
        },
        {
            "id": "no-title",
            "title": "",
            "author": "",
            "uploadDate": datetime(2024, 1, 6),
            "contentHash": "h3",
            "totalPages": 1,
            "results": [],
            "status": "ready"
        },
        {
            "id": "other",
            "title": "Other",
            "author": "B",
            "uploadDate": datetime(2024, 1, 5),
            "contentHash": "h4",
            "totalPages": 1,
            "results": [],
            "status": "ready"
        }
    ]
    response = await client.get("/api/books/?groupByWork=true&sortBy=uploadDate&order=-1")
    assert response.status_code == 200
    ordered = [b["id"] for b in response.json()["books"]]
    assert ordered == ["work-new", "work-old", "no-title", "other"]

@pytest.mark.asyncio
async def test_upload_cover_not_found(client, mock_db):
    mock_db.books.find_one.return_value = None
    files = {"file": ("cover.png", b"fake", "image/png")}
    data = {"title": "Missing"}
    mock_pil = MagicMock()
    mock_image_module = MagicMock()
    mock_pil.Image = mock_image_module
    with patch.dict(sys.modules, {"PIL": mock_pil, "PIL.Image": mock_image_module}):
        response = await client.post("/api/books/upload-cover", data=data, files=files)
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_upload_cover_invalid_type(client, mock_db):
    mock_db.books.find_one.return_value = {"id": "book-id", "title": "T"}
    files = {"file": ("cover.txt", b"fake", "text/plain")}
    data = {"title": "T"}
    mock_pil = MagicMock()
    mock_image_module = MagicMock()
    mock_pil.Image = mock_image_module
    with patch.dict(sys.modules, {"PIL": mock_pil, "PIL.Image": mock_image_module}):
        response = await client.post("/api/books/upload-cover", data=data, files=files)
        assert response.status_code == 400

@pytest.mark.asyncio
async def test_upload_cover_success(client, mock_db):
    mock_db.books.find_one.return_value = {"id": "book-id", "title": "T"}
    files = {"file": ("cover.png", b"fake", "image/png")}
    data = {"title": "T"}
    
    mock_img = MagicMock()
    mock_img.mode = "RGBA"
    mock_converted = MagicMock()
    mock_img.convert.return_value = mock_converted
    
    mock_pil = MagicMock()
    mock_image_module = MagicMock()
    mock_image_module.open.return_value = mock_img
    mock_pil.Image = mock_image_module
    with patch.dict(sys.modules, {"PIL": mock_pil, "PIL.Image": mock_image_module}):
        response = await client.post("/api/books/upload-cover", data=data, files=files)
        assert response.status_code == 200
        assert response.json()["bookId"] == "book-id"

@pytest.mark.asyncio
async def test_check_book_spelling_success(client, mock_db):
    correction = SpellCorrection(original="a", corrected="b", confidence=0.9, reason="typo")
    page_check = PageSpellCheck(pageNumber=1, corrections=[correction], totalIssues=1, checkedAt="2024-01-01T00:00:00")
    with patch("app.api.endpoints.books.spell_check_service.check_book", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = {1: page_check}
        response = await client.post("/api/books/book-id/spell-check")
        assert response.status_code == 200
        data = response.json()
        assert data["totalPagesWithIssues"] == 1
        assert data["results"]["1"]["totalIssues"] == 1

@pytest.mark.asyncio
async def test_check_book_spelling_not_found(client, mock_db):
    with patch("app.api.endpoints.books.spell_check_service.check_book", new_callable=AsyncMock) as mock_check:
        mock_check.side_effect = ValueError("Book not found")
        response = await client.post("/api/books/book-id/spell-check")
        assert response.status_code == 404

@pytest.mark.asyncio
async def test_check_page_spelling_no_text(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "book-id",
        "results": [{"pageNumber": 2, "text": ""}]
    }
    response = await client.post("/api/books/book-id/pages/2/spell-check")
    assert response.status_code == 200
    assert response.json()["totalIssues"] == 0

@pytest.mark.asyncio
async def test_check_page_spelling_success(client, mock_db):
    mock_db.books.find_one.return_value = {
        "id": "book-id",
        "results": [{"pageNumber": 2, "text": "text"}]
    }
    correction = SpellCorrection(original="a", corrected="b", confidence=0.9, reason="typo")
    page_check = PageSpellCheck(pageNumber=2, corrections=[correction], totalIssues=1, checkedAt="2024-01-01T00:00:00")
    with patch("app.api.endpoints.books.spell_check_service.check_page_text", new_callable=AsyncMock) as mock_check:
        mock_check.return_value = page_check
        response = await client.post("/api/books/book-id/pages/2/spell-check")
        assert response.status_code == 200
        assert response.json()["totalIssues"] == 1

@pytest.mark.asyncio
async def test_apply_spelling_corrections_no_payload(client, mock_db):
    response = await client.post("/api/books/book-id/pages/2/apply-corrections", json={})
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_apply_spelling_corrections_success(client, mock_db):
    with patch("app.api.endpoints.books.spell_check_service.apply_corrections", new_callable=AsyncMock) as mock_apply, \
         patch("app.api.endpoints.books.process_pdf_task") as mock_task:
        mock_apply.return_value = True
        payload = {"corrections": [{"original": "a", "corrected": "b"}]}
        response = await client.post("/api/books/book-id/pages/2/apply-corrections", json=payload)
        assert response.status_code == 200
        assert response.json()["correctionsApplied"] == 1
