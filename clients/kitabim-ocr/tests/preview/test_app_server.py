import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import fitz
import httpx
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
    assert 'id="livePreviewModal"' in response.text
    assert "openLivePreview" in response.text
    assert 'id="previewModalText"' in response.text
    assert 'data-i18n="sessions.th_uploaded"' in response.text
    assert "ensureSessionsAutoRefresh" in response.text


def test_state_defaults_to_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    response = client.get("/api/state")

    assert response.status_code == 200
    data = response.json()
    assert data["stage"] == "landing"
    assert data["error"] is None
    assert data["sessionId"] is None
    assert data["engine"] == "surya"
    assert data["concurrency"] == 4
    assert data["activeSessionId"] is None
    assert data["queuedSessions"] == []


def test_state_with_savitr_engine(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work", engine="savitr")
    client = TestClient(app)

    response = client.get("/api/state")
    assert response.status_code == 200
    assert response.json()["engine"] == "savitr"

    html_resp = client.get("/")
    assert "Savitr OCR (MLX)" in html_resp.text


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

    response = client.get(
        "/api/books?q=tarikh&page=2&pageSize=40&sortBy=uploadDate&order=-1"
    )

    assert response.status_code == 200
    assert response.json() == {"books": [{"id": "b1", "title": "Tarikh"}], "total": 1}
    mock_client.list_books.assert_called_once_with(
        q="tarikh", page=2, page_size=40, sort_by="uploadDate", order=-1
    )


def test_serve_font_endpoint(tmp_path: Path):
    mock_client = MagicMock()
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)

    response = client.get("/fonts/alkatip-basma.woff2")
    assert response.status_code == 200
    assert response.headers["content-type"] == "font/woff2"

    not_found = client.get("/fonts/nonexistent.woff2")
    assert not_found.status_code == 404


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


def test_start_existing_route_queues_when_not_landing(tmp_path: Path):
    mock_client = MagicMock()
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [{"pageNumber": 1, "text": "hi"}]
    client.post("/api/start/existing", json={"bookId": "book123"})

    response = client.post("/api/start/existing", json={"bookId": "otherbook"})

    assert response.status_code == 200


def test_create_upload_workdir_pre_populates_pending_pages(tmp_path: Path):
    from preview.server import get_page_image_bytes

    work_root = tmp_path / "work"
    pdf_bytes = _minimal_pdf_bytes(3)

    workdir = _create_upload_workdir(pdf_bytes, work_root)

    assert workdir.total_pages == 3
    assert workdir.book_id is None
    for page_number in (1, 2, 3):
        page = workdir.get_page(page_number)
        assert page.status == "pending"
        assert page.text == ""
        img = get_page_image_bytes(workdir, page_number)
        assert len(img) > 0
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
            "preview.app_server.ocr_page",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    assert workdir.get_page(1).text == "text one"
    assert workdir.get_page(1).status == "ocrd"
    assert workdir.get_page(2).text == "text two"
    assert state.stage == "review"


async def test_run_ocr_background_uses_the_workdirs_shared_save_lock(tmp_path: Path):
    # process_one's set_page()+save() must go through workdir.save_lock (a
    # plain threading.Lock shared with the sync update_page/redo routes),
    # not a private asyncio.Lock local to this function — otherwise a
    # concurrent manual edit on FastAPI's threadpool thread could race it.
    workdir = _create_upload_workdir(_minimal_pdf_bytes(2), tmp_path / "work")
    state = AppState(client=MagicMock(), work_root=tmp_path / "work")
    state.workdir = workdir

    real_lock = workdir.save_lock
    enter_count = 0

    class CountingLock:
        def __enter__(self):
            nonlocal enter_count
            enter_count += 1
            real_lock.acquire()

        def __exit__(self, *exc_info):
            real_lock.release()

    workdir.save_lock = CountingLock()

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch(
            "preview.app_server.ocr_page",
            AsyncMock(side_effect=["text one", "text two"]),
        ),
    ):
        await _run_ocr_background(workdir, state)

    # 2 pages x 2 lock sections each ("processing" then "ocrd") = 4.
    assert enter_count == 4


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
            "preview.app_server.ocr_page",
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
    assert response.json()["stage"] == "processing"
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


def test_start_upload_route_queues_when_not_landing(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    with patch("preview.app_server._start_background_task"):
        res1 = client.post(
            "/api/start/upload",
            files={"file": ("book1.pdf", _minimal_pdf_bytes(1), "application/pdf")},
        )
        assert res1.status_code == 200

        response = client.post(
            "/api/start/upload",
            files={"file": ("book2.pdf", _minimal_pdf_bytes(1), "application/pdf")},
        )

        assert response.status_code == 200
        assert response.json()["stage"] == "queued"


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
    assert "no-cache" in image_response.headers.get("Cache-Control", "")

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


def test_update_page_saves_text_and_toc(tmp_path: Path):
    mock_client = MagicMock()
    mock_client.download_book_pdf.side_effect = (
        lambda book_id, dest: dest.write_bytes(_minimal_pdf_bytes(1)) or dest
    )
    mock_client.get_book_pages.return_value = [
        {"pageNumber": 1, "text": "initial text", "isToc": False}
    ]
    app = create_landing_app(mock_client, tmp_path / "work")
    client = TestClient(app)
    client.post("/api/start/existing", json={"bookId": "book123"})

    res = client.post(
        "/api/pages/1/update",
        json={"text": "updated text", "isToc": True},
    )
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "pageNumber": 1}

    pages = client.get("/api/pages").json()
    assert pages[0]["text"] == "updated text"
    assert pages[0]["isToc"] is True


def test_get_sessions_lists_local_folders(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True)
    pdf_bytes = _minimal_pdf_bytes(2)

    # Create session 1: 1 of 2 pages completed with original_filename
    s1_dir = work_root / "upload-123"
    w1 = OcrWorkDir.create(
        s1_dir,
        source_pdf=s1_dir / "book.pdf",
        total_pages=2,
        original_filename="ئۇيغۇر_تارىخى.pdf",
    )
    (s1_dir / "book.pdf").write_bytes(pdf_bytes)
    w1.set_page(1, text="p1", is_toc=False, confidence=1.0, status="ocrd")
    w1.set_page(2, text="", is_toc=False, confidence=0.0, status="pending")
    w1.save()

    # Create session 2: all pages complete with book_id
    s2_dir = work_root / "book-999"
    w2 = OcrWorkDir.create(
        s2_dir, source_pdf=s2_dir / "book.pdf", total_pages=1, book_id="book-999"
    )
    (s2_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w2.set_page(1, text="p1", is_toc=False, confidence=1.0, status="ocrd")
    w2.save()

    app = create_landing_app(MagicMock(), work_root)
    client = TestClient(app)

    res = client.get("/api/sessions")
    assert res.status_code == 200
    sessions = res.json()
    assert len(sessions) == 2

    s_map = {s["id"]: s for s in sessions}
    assert s_map["upload-123"]["title"] == "ئۇيغۇر_تارىخى.pdf"
    assert s_map["upload-123"]["originalFilename"] == "ئۇيغۇر_تارىخى.pdf"
    assert s_map["upload-123"]["totalPages"] == 2
    assert s_map["upload-123"]["completedPages"] == 1
    assert s_map["upload-123"]["isComplete"] is False

    assert s_map["book-999"]["totalPages"] == 1
    assert s_map["book-999"]["completedPages"] == 1
    assert s_map["book-999"]["isComplete"] is True
    assert "book-999" in s_map["book-999"]["title"]


def test_resume_session_routes_to_processing_or_review(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True)
    pdf_bytes = _minimal_pdf_bytes(2)

    # Session 1: unfinished -> processing
    s1_dir = work_root / "upload-123"
    w1 = OcrWorkDir.create(s1_dir, source_pdf=s1_dir / "book.pdf", total_pages=2)
    (s1_dir / "book.pdf").write_bytes(pdf_bytes)
    w1.set_page(1, text="p1", is_toc=False, confidence=1.0, status="ocrd")
    w1.set_page(2, text="", is_toc=False, confidence=0.0, status="pending")
    w1.save()

    # Session 2: finished -> review
    s2_dir = work_root / "upload-456"
    w2 = OcrWorkDir.create(s2_dir, source_pdf=s2_dir / "book.pdf", total_pages=1)
    (s2_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w2.set_page(1, text="p1", is_toc=False, confidence=1.0, status="ocrd")
    w2.save()

    app = create_landing_app(MagicMock(), work_root)
    with patch("preview.app_server._start_background_task") as mock_bg:
        client = TestClient(app)
        res1 = client.post("/api/sessions/upload-123/resume")
        assert res1.status_code == 200
        assert res1.json()["stage"] == "processing"
        mock_bg.assert_called_once()

        # Resuming the same active processing session returns processing without 409
        res1_again = client.post("/api/sessions/upload-123/resume")
        assert res1_again.status_code == 200
        assert res1_again.json()["stage"] == "processing"

        # Resuming a finished session routes to review
        res_review = client.post("/api/sessions/upload-456/resume")
        assert res_review.status_code == 200
        assert res_review.json()["stage"] == "review"

    # App in review stage can seamlessly switch to another session without reset
    app2 = create_landing_app(MagicMock(), work_root)
    client2 = TestClient(app2)

    res2 = client2.post("/api/sessions/upload-456/resume")
    assert res2.status_code == 200
    assert res2.json()["stage"] == "review"


def test_delete_session(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir(parents=True)
    s_dir = work_root / "upload-to-del"
    w = OcrWorkDir.create(s_dir, source_pdf=s_dir / "book.pdf", total_pages=1)
    (s_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w.save()

    app = create_landing_app(MagicMock(), work_root)
    client = TestClient(app)

    res = client.delete("/api/sessions/upload-to-del")
    assert res.status_code == 200
    assert not (work_root / "upload-to-del").exists()

    res_404 = client.delete("/api/sessions/upload-to-del")
    assert res_404.status_code == 404


def test_locales_endpoints(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    res_ug = client.get("/api/locales/ug")
    assert res_ug.status_code == 200
    assert "header" in res_ug.json()
    assert res_ug.json()["tabs"]["sessions"] == "يەرلىكتىكى خىزمەتلەر"

    res_en = client.get("/api/locales/en")
    assert res_en.status_code == 200
    assert res_en.json()["tabs"]["sessions"] == "Local Sessions"

    res_def = client.get("/api/locales")
    assert res_def.status_code == 200
    assert res_def.json()["tabs"]["sessions"] == "يەرلىكتىكى خىزمەتلەر"


@pytest.mark.asyncio
async def test_start_background_task_retains_reference():
    from preview.app_server import _start_background_task, _BACKGROUND_TASKS

    async def simple_task():
        await asyncio.sleep(0.01)

    task = _start_background_task(simple_task())
    assert task in _BACKGROUND_TASKS
    await task
    assert task not in _BACKGROUND_TASKS


@pytest.mark.asyncio
async def test_run_ocr_background_unexpected_error(tmp_path: Path):
    from preview.app_server import _run_ocr_background, AppState

    workdir_path = tmp_path / "workdir"
    pdf_path = workdir_path / "book.pdf"
    pdf_bytes = _minimal_pdf_bytes(1)
    workdir_path.mkdir(parents=True)
    pdf_path.write_bytes(pdf_bytes)

    workdir = OcrWorkDir.create(workdir_path, source_pdf=pdf_path, total_pages=1)
    workdir.save()

    state = AppState(client=MagicMock(), work_root=tmp_path)

    with patch("preview.app_server.ocr_page", side_effect=RuntimeError("GPU crash")):
        with patch(
            "preview.app_server.get_recognition_predictor",
            new=AsyncMock(return_value=MagicMock()),
        ):
            await _run_ocr_background(workdir, state)

    assert state.stage == "review"
    page = workdir.get_page(1)
    assert page.status == "failed"
    assert "GPU crash" in page.error


@pytest.mark.asyncio
async def test_upload_can_queue_multiple_books_without_409(tmp_path: Path):
    import httpx

    mock_client = MagicMock()
    work_root = tmp_path / "work"
    work_root.mkdir()

    app = create_landing_app(mock_client, work_root)

    pause_event = asyncio.Event()

    async def paused_ocr(workdir, state):
        await pause_event.wait()

    with patch("preview.app_server._run_ocr_background", side_effect=paused_ocr):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            res1 = await ac.post(
                "/api/start/upload",
                files={"file": ("first.pdf", _minimal_pdf_bytes(1), "application/pdf")},
            )
            assert res1.status_code == 200
            data1 = res1.json()
            assert data1["isProcessing"] is True
            assert data1["queuePosition"] == 0

            res2 = await ac.post(
                "/api/start/upload",
                files={
                    "file": ("second.pdf", _minimal_pdf_bytes(1), "application/pdf")
                },
            )
            assert res2.status_code == 200
            data2 = res2.json()
            assert data2["isProcessing"] is False
            assert data2["queuePosition"] == 1

            sessions_res = await ac.get("/api/sessions")
            assert sessions_res.status_code == 200
            sessions = sessions_res.json()
            assert len(sessions) == 2
            for s in sessions:
                assert "uploaded" in s
                assert "uploadedAt" in s
                assert "queueStatus" in s
                assert "queuePosition" in s
                assert s["uploaded"] is False

        pause_event.set()


async def test_reset_while_processing_does_not_resurrect_stage_to_review(
    tmp_path: Path,
):
    import httpx

    mock_client = MagicMock()
    work_root = tmp_path / "work"
    work_root.mkdir()
    app = create_landing_app(mock_client, work_root)

    resume_ocr = asyncio.Event()

    async def slow_ocr_page(*args, **kwargs):
        await resume_ocr.wait()
        return "recognized text"

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="predictor"),
        ),
        patch("preview.app_server.ocr_page", side_effect=slow_ocr_page),
    ):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as ac:
            start_res = await ac.post(
                "/api/start/upload",
                files={"file": ("book.pdf", _minimal_pdf_bytes(1), "application/pdf")},
            )
            assert start_res.status_code == 200
            session_id = start_res.json()["sessionId"]
            assert (await ac.get("/api/state")).json()["stage"] == "processing"

            # User leaves back to the library while the job keeps running.
            reset_res = await ac.post("/api/reset")
            assert reset_res.status_code == 200
            assert (await ac.get("/api/state")).json()["stage"] == "landing"

            # Let the background job actually finish.
            resume_ocr.set()
            for _ in range(200):
                sessions = (await ac.get("/api/sessions")).json()
                session = next(s for s in sessions if s["id"] == session_id)
                if session["queueStatus"] == "completed":
                    break
                await asyncio.sleep(0.01)
            else:
                pytest.fail("background job never completed")

            # The reset must stick: no resurrection to 'review' just because
            # the abandoned job happened to finish afterwards.
            state = (await ac.get("/api/state")).json()
            assert state["stage"] == "landing"
            assert state["activeSessionId"] is None


def test_push_updates_uploaded_flag_in_workdir(tmp_path: Path):
    from preview.server import push_response

    workdir_path = tmp_path / "workdir"
    pdf_path = workdir_path / "book.pdf"
    pdf_bytes = _minimal_pdf_bytes(1)
    workdir_path.mkdir(parents=True)
    pdf_path.write_bytes(pdf_bytes)

    workdir = OcrWorkDir.create(workdir_path, source_pdf=pdf_path, total_pages=1)
    assert workdir.uploaded is False

    mock_client = MagicMock()
    mock_client.push_new_book.return_value = {
        "bookId": "cloud_999",
        "status": "uploaded",
    }

    res = push_response(workdir, mock_client)
    assert res["status"] == "uploaded"
    assert workdir.uploaded is True
    assert workdir.uploaded_at is not None
    assert workdir.book_id == "cloud_999"

    # Verify persisted to disk
    reloaded = OcrWorkDir.load(workdir_path)
    assert reloaded.uploaded is True
    assert reloaded.book_id == "cloud_999"


def test_toggle_session_uploaded_route(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir()
    s_dir = work_root / "upload-toggle"
    w = OcrWorkDir.create(
        s_dir, source_pdf=s_dir / "book.pdf", total_pages=1, book_id="book-999"
    )
    (s_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w.uploaded = True
    w.save()

    app = create_landing_app(MagicMock(), work_root)
    client = TestClient(app)

    # Toggle to false - should reset uploaded and book_id
    res = client.post("/api/sessions/upload-toggle/toggle-uploaded")
    assert res.status_code == 200
    assert res.json()["uploaded"] is False
    reloaded = OcrWorkDir.load(s_dir)
    assert reloaded.uploaded is False
    assert reloaded.book_id is None

    # Toggle to true
    res2 = client.post("/api/sessions/upload-toggle/toggle-uploaded")
    assert res2.status_code == 200
    assert res2.json()["uploaded"] is True
    assert OcrWorkDir.load(s_dir).uploaded is True

    # 404 for nonexistent session
    res_404 = client.post("/api/sessions/nonexistent/toggle-uploaded")
    assert res_404.status_code == 404


def test_open_session_route_opens_review_stage(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir()
    s_dir = work_root / "upload-review"
    w = OcrWorkDir.create(s_dir, source_pdf=s_dir / "book.pdf", total_pages=2)
    (s_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(2))
    w.set_page(1, text="Hello", is_toc=False, confidence=1.0, status="ocrd")
    w.set_page(
        2, text="", is_toc=False, confidence=0.0, status="failed", error="Low conf"
    )
    w.save()

    app = create_landing_app(MagicMock(), work_root)
    client = TestClient(app)

    res = client.post("/api/sessions/upload-review/open")
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "review"
    assert data["sessionId"] == "upload-review"

    # State now in review
    state_res = client.get("/api/state")
    assert state_res.json()["stage"] == "review"
    assert state_res.json()["sessionId"] == "upload-review"


def test_resume_session_with_failed_page_opens_review(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir()
    s_dir = work_root / "upload-failed-only"
    w = OcrWorkDir.create(s_dir, source_pdf=s_dir / "book.pdf", total_pages=2)
    (s_dir / "book.pdf").write_bytes(_minimal_pdf_bytes(2))
    w.set_page(1, text="Page 1", is_toc=False, confidence=1.0, status="ocrd")
    w.set_page(
        2, text="", is_toc=False, confidence=0.0, status="failed", error="Low conf"
    )
    w.save()

    app = create_landing_app(MagicMock(), work_root)
    client = TestClient(app)

    # Calling resume on completed run with 0 pending pages should open review, not queue
    res = client.post("/api/sessions/upload-failed-only/resume")
    assert res.status_code == 200
    data = res.json()
    assert data["stage"] == "review"
    assert data["isProcessing"] is False
    assert data["queuePosition"] is None


@pytest.mark.asyncio
async def test_reviewing_session_protected_from_concurrent_background_runner(
    tmp_path: Path,
):
    work_root = tmp_path / "work"
    work_root.mkdir()

    # Create Book A (being reviewed)
    dir_a = work_root / "book-a"
    w_a = OcrWorkDir.create(dir_a, source_pdf=dir_a / "book.pdf", total_pages=1)
    (dir_a / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w_a.set_page(1, text="Book A Text", is_toc=False, confidence=1.0, status="ocrd")
    w_a.save()

    # Create Book B (being processed in background)
    dir_b = work_root / "book-b"
    w_b = OcrWorkDir.create(dir_b, source_pdf=dir_b / "book.pdf", total_pages=1)
    (dir_b / "book.pdf").write_bytes(_minimal_pdf_bytes(1))
    w_b.save()

    app = create_landing_app(MagicMock(), work_root)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Open Book A for review
        res_open = await ac.post("/api/sessions/book-a/open")
        assert res_open.status_code == 200
        assert res_open.json()["stage"] == "review"

        # Check /api/state is review on book-a
        state_before = (await ac.get("/api/state")).json()
        assert state_before["stage"] == "review"
        assert state_before["sessionId"] == "book-a"

        # Simulate background runner for book B finishing
        state = None
        # Retrieve state from route endpoint or test directly
        from preview.app_server import _run_ocr_background, AppState

        state = AppState(
            client=MagicMock(), work_root=work_root, stage="review", workdir=w_a
        )

        with (
            patch(
                "preview.app_server.get_recognition_predictor",
                AsyncMock(return_value="pred"),
            ),
            patch("preview.app_server.ocr_page", AsyncMock(return_value="Book B Text")),
        ):
            await _run_ocr_background(w_b, state)

        # state.stage must STILL be review and state.workdir must STILL be Book A!
        assert state.stage == "review"
        assert state.workdir.root.name == "book-a"


@pytest.mark.asyncio
async def test_startup_does_not_auto_start_processing(tmp_path: Path):
    work_root = tmp_path / "work"
    work_root.mkdir()

    # Create a book left in 'processing' status from a previous run
    dir_interrupted = work_root / "interrupted-book"
    pdf = dir_interrupted / "book.pdf"
    w = OcrWorkDir.create(
        dir_interrupted,
        source_pdf=pdf,
        total_pages=5,
        queue_status="processing",
    )
    pdf.write_bytes(_minimal_pdf_bytes(5))
    w.save()

    app = create_landing_app(MagicMock(), work_root)

    # Trigger lifespan/startup handlers
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as ac:
        state_res = await ac.get("/api/state")
        assert state_res.status_code == 200
        state = state_res.json()

        # Must start in landing mode, not processing
        assert state["stage"] == "landing"
        assert state["activeSessionId"] is None
        assert state["queuedSessions"] == []

        # Interrupted book must be reset to idle on disk
        reloaded = OcrWorkDir.load(dir_interrupted)
        assert reloaded.queue_status == "idle"

        # In sessions table, it should be listed with Resume button available
        sessions_res = await ac.get("/api/sessions")
        sessions = sessions_res.json()
        assert len(sessions) == 1
        assert sessions[0]["id"] == "interrupted-book"
        assert sessions[0]["queueStatus"] == "idle"
        assert sessions[0]["isComplete"] is False


def test_create_landing_app_custom_concurrency(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work", concurrency=3)
    client = TestClient(app)
    res = client.get("/api/state")
    assert res.status_code == 200
    assert res.json()["concurrency"] == 3


def test_create_landing_app_concurrency_from_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("KITABIM_OCR_CONCURRENCY", "2")
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)
    res = client.get("/api/state")
    assert res.status_code == 200
    assert res.json()["concurrency"] == 2


def test_create_landing_app_clamps_surya_concurrency_to_four(tmp_path: Path):
    app = create_landing_app(
        MagicMock(), tmp_path / "work", engine="surya", concurrency=8
    )
    client = TestClient(app)
    res = client.get("/api/state")
    assert res.status_code == 200
    assert res.json()["concurrency"] == 4


def test_api_set_concurrency(tmp_path: Path):
    app = create_landing_app(MagicMock(), tmp_path / "work")
    client = TestClient(app)

    res = client.post("/api/concurrency", json={"concurrency": 3})
    assert res.status_code == 200
    assert res.json()["concurrency"] == 3

    # Clamped to 4 for Surya
    res = client.post("/api/concurrency", json={"concurrency": 8})
    assert res.status_code == 200
    assert res.json()["concurrency"] == 4

    # Invalid returns 400
    res = client.post("/api/concurrency", json={"concurrency": "bad"})
    assert res.status_code == 400


def test_require_active_workdir_hydrates_from_queue(tmp_path: Path):
    from preview.app_server import _require_active_workdir, AppState
    from engine.queue import BookQueueManager
    from engine.workdir import OcrWorkDir

    work_root = tmp_path / "work"
    work_root.mkdir()
    session_dir = work_root / "test-session"
    session_dir.mkdir()
    pdf_path = session_dir / "book.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes(1))
    workdir = OcrWorkDir.create(session_dir, source_pdf=pdf_path, total_pages=1)
    workdir.save()

    qm = BookQueueManager(work_root=work_root, runner=AsyncMock())
    qm._active_session_id = "test-session"

    state = AppState(
        client=MagicMock(),
        work_root=work_root,
        workdir=None,
        queue_manager=qm,
    )
    assert state.workdir is None
    _require_active_workdir(state)
    assert state.workdir is not None
    assert state.workdir.root.name == "test-session"


def test_require_active_workdir_reuses_the_queues_live_instance(tmp_path: Path):
    from preview.app_server import _require_active_workdir, AppState
    from engine.queue import BookQueueManager
    from engine.workdir import OcrWorkDir

    work_root = tmp_path / "work"
    work_root.mkdir()
    session_dir = work_root / "test-session"
    session_dir.mkdir()
    pdf_path = session_dir / "book.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes(1))
    workdir = OcrWorkDir.create(session_dir, source_pdf=pdf_path, total_pages=1)
    workdir.save()

    qm = BookQueueManager(work_root=work_root, runner=AsyncMock())
    qm._active_session_id = "test-session"
    qm._active_workdir = workdir

    state = AppState(
        client=MagicMock(),
        work_root=work_root,
        workdir=None,
        queue_manager=qm,
    )
    _require_active_workdir(state)

    # Must be the exact live instance, not a second copy loaded from disk —
    # a write through a second instance would silently diverge from (and
    # could overwrite) the runner's own in-memory changes.
    assert state.workdir is workdir


def test_require_active_workdir_raises_409_when_no_active_session(tmp_path: Path):
    from preview.app_server import _require_active_workdir, AppState
    import pytest
    from fastapi import HTTPException

    state = AppState(
        client=MagicMock(),
        work_root=tmp_path / "work",
        workdir=None,
    )
    with pytest.raises(HTTPException) as exc_info:
        _require_active_workdir(state)
    assert exc_info.value.status_code == 409


def test_open_session_reuses_the_queues_live_instance(tmp_path: Path):
    from preview.app_server import create_landing_app
    from engine.workdir import OcrWorkDir

    work_root = tmp_path / "work"
    work_root.mkdir()
    session_dir = work_root / "test-session"
    session_dir.mkdir()
    pdf_path = session_dir / "book.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes(1))
    workdir = OcrWorkDir.create(session_dir, source_pdf=pdf_path, total_pages=1)

    app = create_landing_app(client=MagicMock(), work_root=work_root)
    state = app.state.app_state
    state.queue_manager._active_session_id = "test-session"
    state.queue_manager._active_workdir = workdir

    client = TestClient(app)
    res = client.post("/api/sessions/test-session/open")
    assert res.status_code == 200
    assert res.json()["sessionId"] == "test-session"
    assert state.workdir is workdir


async def test_process_one_preserves_reviewed_page_edits(tmp_path: Path):
    from preview.app_server import _run_ocr_background, AppState
    from engine.workdir import OcrWorkDir

    work_root = tmp_path / "work"
    work_root.mkdir()
    session_dir = work_root / "sess"
    session_dir.mkdir()
    pdf_path = session_dir / "book.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes(1))
    workdir = OcrWorkDir.create(session_dir, source_pdf=pdf_path, total_pages=1)

    state = AppState(client=MagicMock(), work_root=work_root)
    state.workdir = workdir

    # When ocr_page is called, simulate user editing the page before OCR finishes!
    async def slow_ocr_page(fitz_page, predictor, **kwargs):
        with workdir.save_lock:
            workdir.set_page(
                1,
                text="manual human translation",
                is_toc=True,
                confidence=1.0,
                status="reviewed",
            )
            workdir.save()
        return "raw machine ocr text"

    with (
        patch(
            "preview.app_server.get_recognition_predictor",
            AsyncMock(return_value="pred"),
        ),
        patch("preview.app_server.ocr_page", side_effect=slow_ocr_page),
    ):
        await _run_ocr_background(workdir, state)

    # The user's manual review text and TOC flag MUST NOT be clobbered by the machine OCR
    page1 = workdir.get_page(1)
    assert page1.status == "reviewed"
    assert page1.text == "manual human translation"
    assert page1.is_toc is True


def test_push_rejected_when_pages_are_pending_or_processing(tmp_path: Path):
    from preview.server import push_response
    from engine.workdir import OcrWorkDir
    import pytest
    from fastapi import HTTPException

    work_root = tmp_path / "work"
    work_root.mkdir()
    session_dir = work_root / "sess"
    session_dir.mkdir()
    pdf_path = session_dir / "book.pdf"
    pdf_path.write_bytes(_minimal_pdf_bytes(2))
    workdir = OcrWorkDir.create(session_dir, source_pdf=pdf_path, total_pages=2)
    workdir.set_page(1, text="done", is_toc=False, confidence=1.0, status="ocrd")
    workdir.set_page(2, text="", is_toc=False, confidence=0.0, status="processing")
    workdir.save()

    mock_client = MagicMock()
    with pytest.raises(HTTPException) as exc:
        push_response(workdir, mock_client)

    assert exc.value.status_code == 409
    assert "incomplete" in exc.value.detail
