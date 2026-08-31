from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from engine.workdir import OcrWorkDir
from preview.server import create_app


def _workdir(tmp_path: Path, book_id=None) -> OcrWorkDir:
    wd = OcrWorkDir.create(
        tmp_path / "work",
        source_pdf=tmp_path / "book.pdf",
        total_pages=2,
        book_id=book_id,
    )
    wd.set_page(1, text="page one", is_toc=False, confidence=0.9, status="ocrd")
    wd.set_page(2, text="page two", is_toc=True, confidence=0.8, status="ocrd")
    wd.image_path(1).parent.mkdir(exist_ok=True)
    wd.image_path(1).write_bytes(b"\x89PNG\r\n fake")
    wd.image_path(2).write_bytes(b"\x89PNG\r\n fake2")
    wd.save()
    return wd


def test_list_pages_returns_all_pages_in_order(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/api/pages")

    assert response.status_code == 200
    body = response.json()
    assert [p["pageNumber"] for p in body] == [1, 2]
    assert body[0]["text"] == "page one"


def test_get_page_image_returns_png_bytes(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/api/pages/1/image")

    assert response.status_code == 200
    assert response.content == b"\x89PNG\r\n fake"
    assert "no-cache" in response.headers.get("Cache-Control", "")


def test_redo_pages_reruns_ocr_on_selected_pages_only(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    with (
        patch(
            "preview.server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.server.ocr_page",
            AsyncMock(return_value="re-ocr'd text"),
        ),
        patch("preview.server.fitz.open") as mock_fitz_open,
    ):
        mock_doc = mock_fitz_open.return_value
        mock_doc.load_page.return_value = "fake-fitz-page"

        response = client.post("/api/pages/redo", json={"pageNumbers": [2]})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["pageNumber"] == 1 and body[0]["text"] == "page one"  # untouched
    assert body[1]["pageNumber"] == 2 and body[1]["text"] == "re-ocr'd text"
    assert wd.get_page(1).text == "page one"
    assert wd.get_page(2).text == "re-ocr'd text"


def test_redo_pages_flags_failed_page_instead_of_crashing(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    from engine.recognize import LowConfidenceOcrError

    with (
        patch(
            "preview.server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.server.ocr_page",
            AsyncMock(side_effect=LowConfidenceOcrError("confidence too low")),
        ),
        patch("preview.server.fitz.open") as mock_fitz_open,
    ):
        mock_doc = mock_fitz_open.return_value
        mock_doc.load_page.return_value = "fake-fitz-page"

        response = client.post("/api/pages/redo", json={"pageNumbers": [2]})

    assert response.status_code == 200
    body = response.json()
    failed_page = next(p for p in body if p["pageNumber"] == 2)
    assert failed_page["status"] == "failed"
    assert "confidence too low" in failed_page["error"]
    assert wd.get_page(2).status == "failed"


def test_push_new_book_calls_client_push_new_book(tmp_path: Path):
    wd = _workdir(tmp_path)  # book_id=None -> new-book mode
    (tmp_path / "book.pdf").write_bytes(b"%PDF-fake")
    mock_client = AsyncMock()
    mock_client.push_new_book = lambda pdf_path, pages, filename=None: {
        "bookId": "new1",
        "status": "uploaded",
    }

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert response.json() == {"bookId": "new1", "status": "uploaded"}


def test_push_corrections_calls_client_push_page_correction_per_page(tmp_path: Path):
    wd = _workdir(tmp_path, book_id="existingbook")  # correction mode
    calls = []
    mock_client = AsyncMock()
    mock_client.push_page_correction = lambda book_id, page: calls.append(
        (book_id, page.page_number)
    )

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert calls == [("existingbook", 1), ("existingbook", 2)]


def test_update_page_endpoint(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.post(
        "/api/pages/1/update",
        json={"text": "new text content", "isToc": True},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "pageNumber": 1}
    assert wd.get_page(1).text == "new text content"
    assert wd.get_page(1).is_toc is True
    assert wd.get_page(1).status == "reviewed"


def test_serve_font_endpoint(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/fonts/alkatip-basma.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"

    not_found = client.get("/fonts/nonexistent.woff2")
    assert not_found.status_code == 404
