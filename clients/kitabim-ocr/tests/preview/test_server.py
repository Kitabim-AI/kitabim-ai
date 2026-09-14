import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch


from fastapi.testclient import TestClient

from engine.workdir import OcrWorkDir
from kitabim_client.api import KitabimAPIError
from preview.server import UpdatePageRequest, create_app, update_page_response


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
    assert wd.get_page(2).is_toc is True


def test_redo_pages_route_passes_the_configured_engine(tmp_path: Path, monkeypatch):
    # The standalone preview server has no per-session engine state, so it
    # must forward the actually configured engine to redo_pages_response
    # rather than leaving it blank (which used to silently clamp concurrency
    # as if the engine were always 'surya').
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)
    monkeypatch.setenv("KITABIM_OCR_ENGINE", "savitr")

    with patch(
        "preview.server.redo_pages_response", AsyncMock(return_value=[])
    ) as mock_redo:
        response = client.post("/api/pages/redo", json={"pageNumbers": [1]})

    assert response.status_code == 200
    mock_redo.assert_called_once()
    assert mock_redo.call_args.kwargs.get("engine") == "savitr"


def test_redo_pages_uses_the_workdirs_shared_save_lock(tmp_path: Path):
    # redo_one's set_page()+save() must go through workdir.save_lock rather
    # than a private asyncio.Lock, so it can't race a concurrent manual page
    # edit (which runs on FastAPI's threadpool thread) on the same workdir.
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    real_lock = wd.save_lock
    enter_count = 0

    class CountingLock:
        def __enter__(self):
            nonlocal enter_count
            enter_count += 1
            real_lock.acquire()

        def __exit__(self, *exc_info):
            real_lock.release()

    wd.save_lock = CountingLock()

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

        response = client.post("/api/pages/redo", json={"pageNumbers": [1, 2]})

    assert response.status_code == 200
    assert enter_count == 2


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
    mock_client = MagicMock()
    mock_client.push_page_correction = lambda book_id, page: calls.append(
        (book_id, page.page_number)
    )

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert calls == [("existingbook", 1), ("existingbook", 2)]


def test_push_recovers_and_pushes_as_new_book_when_book_deleted_on_cloud(
    tmp_path: Path,
):
    wd = _workdir(tmp_path, book_id="deleted_book_123")
    (tmp_path / "book.pdf").write_bytes(b"%PDF-fake")

    mock_client = AsyncMock()
    mock_client.book_exists = lambda book_id: False
    mock_client.push_new_book = lambda pdf_path, pages, filename=None: {
        "bookId": "brand_new_book_456",
        "status": "uploaded",
    }

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert response.json() == {"bookId": "brand_new_book_456", "status": "uploaded"}
    assert wd.book_id == "brand_new_book_456"
    assert wd.uploaded is True


def test_push_recovers_when_page_correction_fails_with_404_and_book_missing(
    tmp_path: Path,
):
    wd = _workdir(tmp_path, book_id="deleted_book_123")
    (tmp_path / "book.pdf").write_bytes(b"%PDF-fake")

    mock_client = MagicMock()
    # Simulate book_exists returning True initially (e.g. race condition or no pre-check),
    # but pushing page correction raises 404
    first_call = True

    def mock_book_exists(book_id):
        nonlocal first_call
        if first_call:
            first_call = False
            return True
        return False

    mock_client.book_exists = mock_book_exists
    mock_client.push_page_correction = MagicMock(
        side_effect=KitabimAPIError(
            "404 from Kitabim API: {'detail': 'Page not found'}"
        )
    )
    mock_client.push_new_book = lambda pdf_path, pages, filename=None: {
        "bookId": "resubmitted_book_789",
        "status": "uploaded",
    }

    app = create_app(wd, client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/api/push")

    assert response.status_code == 200
    assert response.json() == {"bookId": "resubmitted_book_789", "status": "uploaded"}
    assert wd.book_id == "resubmitted_book_789"
    assert wd.uploaded is True


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


def test_update_page_response_holds_the_shared_workdir_lock(tmp_path: Path):
    # update_page_response runs on FastAPI's threadpool while the background
    # OCR job (and redo) run on the asyncio event-loop thread. Both must
    # serialize on the same workdir.save_lock, or a completed page's edit can
    # race the background job's own set_page()+save() for another page.
    wd = _workdir(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    original_save = wd.save

    def blocking_save():
        entered.set()
        assert release.wait(timeout=2), "test setup did not release in time"
        original_save()

    wd.save = blocking_save

    t = threading.Thread(
        target=update_page_response,
        args=(wd, 1, UpdatePageRequest(text="edited while locked")),
    )
    t.start()
    assert entered.wait(timeout=2), "update_page_response never reached save()"

    # A concurrent caller (standing in for the background job's own
    # set_page()+save() critical section) must not be able to acquire the
    # same lock while the edit is mid-save.
    assert wd.save_lock.acquire(blocking=False) is False

    release.set()
    t.join(timeout=2)
    assert not t.is_alive()

    # Lock is released once update_page_response completes.
    assert wd.save_lock.acquire(blocking=False) is True
    wd.save_lock.release()
    assert wd.get_page(1).text == "edited while locked"


def test_serve_font_endpoint(tmp_path: Path):
    wd = _workdir(tmp_path)
    app = create_app(wd, client=None)
    client = TestClient(app)

    response = client.get("/fonts/alkatip-basma.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"

    not_found = client.get("/fonts/nonexistent.woff2")
    assert not_found.status_code == 404
