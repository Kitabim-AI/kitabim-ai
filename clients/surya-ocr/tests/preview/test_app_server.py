from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import pytest
from fastapi.testclient import TestClient

from engine.recognize import LowConfidenceOcrError
from engine.workdir import OcrWorkDir
from preview.app_server import (
    AppState,
    _create_upload_workdir,
    _run_ocr_background,
    _start_existing_book,
    create_landing_app,
)


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


def test_create_upload_workdir_pre_populates_pending_pages(tmp_path: Path):
    work_root = tmp_path / "work"
    pdf_bytes = _minimal_pdf_bytes(3)

    workdir = _create_upload_workdir(pdf_bytes, work_root)

    assert workdir.total_pages == 3
    assert workdir.book_id is None
    for page_number in (1, 2, 3):
        page = workdir.get_page(page_number)
        assert page.status == "pending"
        assert page.text == ""
        assert workdir.image_path(page_number).exists()


def test_create_upload_workdir_rejects_invalid_pdf(tmp_path: Path):
    work_root = tmp_path / "work"

    with pytest.raises(Exception):
        _create_upload_workdir(b"not a pdf", work_root)

    assert not work_root.exists()


async def test_run_ocr_background_ocrs_every_page_then_marks_review(tmp_path: Path):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(2), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir
    state.stage = "processing"

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.app_server.ocr_page_with_surya",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    assert workdir.get_page(1).text == "text one"
    assert workdir.get_page(1).status == "ocrd"
    assert workdir.get_page(2).text == "text two"
    assert state.stage == "review"


async def test_run_ocr_background_flags_failed_page_and_continues(tmp_path: Path):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(2), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.app_server.ocr_page_with_surya",
            AsyncMock(side_effect=[LowConfidenceOcrError("bad page"), "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    assert workdir.get_page(1).status == "failed"
    assert "bad page" in workdir.get_page(1).error
    assert workdir.get_page(2).text == "text two"
    assert state.stage == "review"


async def test_run_ocr_background_sets_error_stage_on_unexpected_failure(
    tmp_path: Path,
):
    workdir = _create_upload_workdir(_minimal_pdf_bytes(1), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir

    with patch(
        "preview.app_server.get_recognition_predictor",
        AsyncMock(side_effect=RuntimeError("model load failed")),
    ):
        await _run_ocr_background(workdir, state)

    assert state.stage == "error"
    assert "model load failed" in state.error


def test_start_upload_route_creates_pending_pages_and_schedules_background_task(
    tmp_path: Path,
):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    pdf_bytes = _minimal_pdf_bytes(2)

    with patch("preview.app_server._start_background_task") as mock_start:
        response = client.post(
            "/api/start/upload",
            files={"file": ("book.pdf", pdf_bytes, "application/pdf")},
        )

    assert response.status_code == 200
    assert response.json() == {"stage": "processing"}
    mock_start.assert_called_once()
    assert client.get("/api/state").json()["stage"] == "processing"
    pages = client.get("/api/pages").json()
    assert len(pages) == 2
    assert all(p["status"] == "pending" for p in pages)


def test_start_upload_route_rejects_invalid_pdf(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.post(
        "/api/start/upload",
        files={"file": ("book.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 400
    assert client.get("/api/state").json()["stage"] == "landing"


def test_start_upload_route_rejects_when_not_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    with patch("preview.app_server._start_background_task"):
        client.post(
            "/api/start/upload",
            files={"file": ("book.pdf", _minimal_pdf_bytes(1), "application/pdf")},
        )

    response = client.post(
        "/api/start/upload",
        files={"file": ("book.pdf", _minimal_pdf_bytes(1), "application/pdf")},
    )

    assert response.status_code == 409


def test_pages_routes_require_an_active_workdir(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    assert client.get("/api/pages").status_code == 409
    assert client.post("/api/pages/redo", json={"pageNumbers": [1]}).status_code == 409
    assert client.post("/api/push").status_code == 409


def test_pages_routes_work_once_a_book_is_active(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "hi", "isToc": False}
    ]
    mock_client.push_page_correction.return_value = {"status": "page_updated"}
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/start/existing", json={"bookId": "book123"})

    pages = client.get("/api/pages").json()
    assert pages[0]["text"] == "hi"

    image_response = client.get("/api/pages/1/image")
    assert image_response.status_code == 200
    assert image_response.content.startswith(b"\x89PNG")

    push_response = client.post("/api/push")
    assert push_response.status_code == 200
    mock_client.push_page_correction.assert_called_once()


def test_back_to_library_clears_active_workdir(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [{"pageNumber": 1, "text": "hi"}]
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/start/existing", json={"bookId": "book123"})

    response = client.post("/api/reset")

    assert response.status_code == 200
    assert client.get("/api/state").json()["stage"] == "landing"
    assert client.get("/api/pages").status_code == 409
