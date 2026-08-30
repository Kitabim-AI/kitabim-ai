from pathlib import Path
from unittest.mock import MagicMock

import fitz
from fastapi.testclient import TestClient

from engine.workdir import OcrWorkDir
from preview.app_server import _start_existing_book, create_landing_app


def _minimal_pdf_bytes(num_pages: int = 2) -> bytes:
    doc = fitz.open()
    for _ in range(num_pages):
        doc.new_page()
    return doc.tobytes()


def test_index_returns_landing_page_html(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    assert 'id="landing"' in response.text
    assert 'id="processing"' in response.text
    assert 'id="review"' in response.text


def test_state_defaults_to_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing", "error": None}


def test_reset_from_landing_is_a_no_op(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert response.json() == {"stage": "landing"}


def test_list_books_route_proxies_to_client(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.list_books.return_value = {
        "books": [{"id": "b1", "title": "Tarikh"}],
        "total": 1,
    }
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/books?q=tarikh&page=2")

    assert response.status_code == 200
    assert response.json() == {"books": [{"id": "b1", "title": "Tarikh"}], "total": 1}
    mock_client.list_books.assert_called_once_with(q="tarikh", page=2)


def test_start_existing_book_downloads_and_seeds_workdir_when_new(tmp_path: Path):
    work_root = tmp_path / "work"
    pdf_bytes = _minimal_pdf_bytes(2)
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(pdf_bytes) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "existing one", "isToc": False},
        {"pageNumber": 2, "text": "existing two", "isToc": True},
    ]

    workdir = _start_existing_book("book123", mock_client, work_root)

    assert workdir.book_id == "book123"
    assert workdir.total_pages == 2
    assert workdir.get_page(1).text == "existing one"
    assert workdir.get_page(1).status == "from_kitabim"
    assert workdir.get_page(2).is_toc is True
    assert workdir.image_path(1).exists()
    mock_client.download_book_pdf.assert_called_once()


def test_start_existing_book_resumes_without_redownloading(tmp_path: Path):
    work_root = tmp_path / "work"
    out_dir = work_root / "book123"
    wd = OcrWorkDir.create(
        out_dir, source_pdf=out_dir / "book.pdf", total_pages=1, book_id="book123"
    )
    wd.set_page(
        1, text="already here", is_toc=False, confidence=1.0, status="from_kitabim"
    )
    wd.save()
    mock_client = MagicMock()

    workdir = _start_existing_book("book123", mock_client, work_root)

    assert workdir.get_page(1).text == "already here"
    mock_client.download_book_pdf.assert_not_called()
    mock_client.get_book_pages.assert_not_called()


def test_start_existing_route_flips_stage_to_review(tmp_path: Path):
    pdf_bytes = _minimal_pdf_bytes(1)
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(pdf_bytes) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "hi", "isToc": False}
    ]
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)

    response = client.post("/api/start/existing", json={"bookId": "book123"})

    assert response.status_code == 200
    assert response.json() == {"stage": "review"}
    assert client.get("/api/state").json()["stage"] == "review"


def test_start_existing_route_rejects_when_not_landing(tmp_path: Path):
    mock_client = MagicMock()
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [{"pageNumber": 1, "text": "hi"}]
    client.post("/api/start/existing", json={"bookId": "book123"})

    response = client.post("/api/start/existing", json={"bookId": "otherbook"})

    assert response.status_code == 409
