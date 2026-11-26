from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.workdir import PageState
from kitabim_client.api import KitabimAPIError, KitabimClient


def _client(tmp_path: Path, app_id: str | None = "test-app-id") -> KitabimClient:
    return KitabimClient(
        base_url="http://localhost:8000",
        config_path=tmp_path / "token.json",
        app_id=app_id,
    )


def test_push_new_book_posts_multipart_with_pages_json(tmp_path: Path):
    client = _client(tmp_path)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    pages = [
        PageState(
            page_number=1, text="hi", is_toc=False, confidence=0.9, status="reviewed"
        ),
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bookId": "abc123", "status": "uploaded"}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=mock_response) as mock_post,
    ):
        result = client.push_new_book(pdf_path, pages)

    assert result == {"bookId": "abc123", "status": "uploaded"}
    call = mock_post.call_args
    assert call.kwargs["files"]["file"][0] == "book.pdf"
    assert call.kwargs["files"]["pages"][0] == "pages.json"
    assert b'"text": "hi"' in call.kwargs["files"]["pages"][1]


def test_push_new_book_uses_custom_filename_with_pdf_extension(tmp_path: Path):
    client = _client(tmp_path)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-fake")
    pages = [
        PageState(
            page_number=1, text="hi", is_toc=False, confidence=0.9, status="reviewed"
        )
    ]

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"bookId": "abc123", "status": "uploaded"}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=mock_response) as mock_post,
    ):
        result = client.push_new_book(pdf_path, pages, filename="تارىخى_رەشىدىي.pdf")

    assert result == {"bookId": "abc123", "status": "uploaded"}
    call = mock_post.call_args
    assert call.kwargs["files"]["file"][0] == "تارىخى_رەشىدىي.pdf"


def test_push_page_correction_calls_update_then_toc(tmp_path: Path):
    client = _client(tmp_path)
    page = PageState(
        page_number=5, text="corrected", is_toc=True, confidence=0.9, status="reviewed"
    )

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "page_updated"}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=mock_response) as mock_post,
    ):
        client.push_page_correction("book123", page)

    urls_called = [c.args[0] for c in mock_post.call_args_list]
    assert urls_called == [
        "http://localhost:8000/books/book123/pages/5/update",
        "http://localhost:8000/books/book123/pages/5/toc",
    ]


def test_download_book_pdf_writes_response_bytes_to_dest(tmp_path: Path):
    client = _client(tmp_path)
    dest = tmp_path / "downloaded.pdf"

    ticket_response = MagicMock()
    ticket_response.status_code = 200
    ticket_response.json.return_value = {
        "download_url": "https://storage.googleapis.com/bucket/book.pdf?sig=1"
    }

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.content = b"%PDF-1.4\nfake-pdf-body"

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch(
            "kitabim_client.api.httpx.post", return_value=ticket_response
        ) as mock_post,
        patch("kitabim_client.api.httpx.get", return_value=mock_get_resp) as mock_get,
    ):
        result = client.download_book_pdf("book123", dest)

    assert result == dest
    assert dest.read_bytes() == b"%PDF-1.4\nfake-pdf-body"
    assert (
        mock_post.call_args.args[0]
        == "http://localhost:8000/books/book123/download-ticket"
    )
    # External GCS URL must NOT send Authorization header
    assert mock_get.call_args.kwargs["headers"] == {}


def test_download_book_pdf_rejects_non_pdf_payload(tmp_path: Path):
    client = _client(tmp_path)
    dest = tmp_path / "bad.pdf"

    ticket_response = MagicMock()
    ticket_response.status_code = 200
    ticket_response.json.return_value = {
        "download_url": "/books/book123/download?token=abc"
    }

    mock_get_resp = MagicMock()
    mock_get_resp.status_code = 200
    mock_get_resp.content = b"<html>Error</html>"

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=ticket_response),
        patch("kitabim_client.api.httpx.get", return_value=mock_get_resp),
    ):
        with pytest.raises(KitabimAPIError, match="not a valid PDF"):
            client.download_book_pdf("book123", dest)

    assert not dest.exists()


def test_get_book_pages_loops_pagination_until_short_page(tmp_path: Path):
    client = _client(tmp_path)

    page1_response = MagicMock()
    page1_response.status_code = 200
    page1_response.json.return_value = [{"pageNumber": i} for i in range(1, 101)]

    page2_response = MagicMock()
    page2_response.status_code = 200
    page2_response.json.return_value = [{"pageNumber": 101}]

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch(
            "kitabim_client.api.httpx.get",
            side_effect=[page1_response, page2_response],
        ) as mock_get,
    ):
        result = client.get_book_pages("book123")

    assert len(result) == 101
    assert mock_get.call_count == 2


def test_list_books_gets_paginated_books_with_query_params(tmp_path: Path):
    client = _client(tmp_path)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "books": [{"id": "b1", "title": "Tarikh"}],
        "total": 1,
        "totalReady": 1,
        "page": 2,
        "pageSize": 20,
    }

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_response) as mock_get,
    ):
        result = client.list_books(q="tarikh", page=2)

    assert result["total"] == 1
    assert result["books"][0]["id"] == "b1"
    call = mock_get.call_args
    assert call.args[0] == "http://localhost:8000/books/"
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok123"
    assert call.kwargs["params"] == {
        "q": "tarikh",
        "page": 2,
        "pageSize": 40,
        "sortBy": "uploadDate",
        "order": -1,
    }


def test_error_response_raises_kitabim_api_error(tmp_path: Path):
    client = _client(tmp_path)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Book not found"

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=mock_response),
    ):
        with pytest.raises(KitabimAPIError):
            client.download_book_pdf("missing", tmp_path / "x.pdf")


def test_headers_includes_app_id_when_provided(tmp_path: Path):
    client = _client(tmp_path, app_id="custom-app-id")
    with patch("kitabim_client.api.get_valid_token", return_value="tok123"):
        headers = client._headers()

    assert headers["Authorization"] == "Bearer tok123"
    assert headers["X-Kitabim-App-Id"] == "custom-app-id"


def test_headers_reads_security_app_id_from_env(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("SECURITY_APP_ID", "sec-app-id-789")
    client = KitabimClient(
        base_url="http://localhost:8000", config_path=tmp_path / "token.json"
    )
    with patch("kitabim_client.api.get_valid_token", return_value="tok123"):
        headers = client._headers()

    assert headers["Authorization"] == "Bearer tok123"
    assert headers["X-Kitabim-App-Id"] == "sec-app-id-789"


def test_get_book_returns_dict_when_found(tmp_path: Path):
    client = _client(tmp_path)
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"id": "book123", "title": "Bustan"}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_res) as mock_get,
    ):
        result = client.get_book("book123")

    assert result == {"id": "book123", "title": "Bustan"}
    assert mock_get.call_args.args[0] == "http://localhost:8000/books/book123"


def test_get_book_returns_none_when_404(tmp_path: Path):
    client = _client(tmp_path)
    mock_res = MagicMock()
    mock_res.status_code = 404

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_res),
    ):
        result = client.get_book("missing_book")

    assert result is None


def test_book_exists_returns_true_when_200(tmp_path: Path):
    client = _client(tmp_path)
    mock_res = MagicMock()
    mock_res.status_code = 200

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_res),
    ):
        assert client.book_exists("book123") is True


def test_book_exists_returns_false_when_404(tmp_path: Path):
    client = _client(tmp_path)
    mock_res = MagicMock()
    mock_res.status_code = 404

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_res),
    ):
        assert client.book_exists("deleted_book") is False


def test_get_backfill_candidates_calls_endpoint_with_version_and_limit(tmp_path: Path):
    client = _client(tmp_path)
    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {
        "candidates": [{"id": "b1", "title": "Book 1", "totalPages": 10}],
        "activePipelineBookCount": 2,
    }

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_res) as mock_get,
    ):
        data = client.get_backfill_candidates(ocr_version="surya-2.5-v2", limit=25)

    assert data["activePipelineBookCount"] == 2
    assert len(data["candidates"]) == 1
    assert (
        mock_get.call_args.args[0] == "http://localhost:8000/books/backfill-candidates"
    )
    assert mock_get.call_args.kwargs["params"] == {
        "ocr_version": "surya-2.5-v2",
        "limit": 25,
    }


def test_replace_book_ocr_posts_gzip_compressed_json(tmp_path: Path):
    import gzip
    import json

    client = _client(tmp_path)
    pages = [
        PageState(
            page_number=1,
            text="# باب بىر",
            is_toc=False,
            confidence=0.92,
            status="ocrd",
            detected_page_number=3,
            skipped=False,
        )
    ]

    mock_res = MagicMock()
    mock_res.status_code = 200
    mock_res.json.return_value = {"bookId": "b1", "replacedPages": 1}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.post", return_value=mock_res) as mock_post,
    ):
        result = client.replace_book_ocr("b1", pages, ocr_version="surya-2.5-v2")

    assert result == {"bookId": "b1", "replacedPages": 1}
    call = mock_post.call_args
    assert call.args[0] == "http://localhost:8000/books/b1/replace-ocr"
    assert call.kwargs["headers"]["Content-Encoding"] == "gzip"
    assert call.kwargs["headers"]["Content-Type"] == "application/json"
    decompressed = json.loads(gzip.decompress(call.kwargs["content"]).decode("utf-8"))
    assert decompressed["ocrVersion"] == "surya-2.5-v2"
    assert decompressed["pages"][0]["detectedPageNumber"] == 3
    assert decompressed["pages"][0]["skipped"] is False


def test_push_new_book_retries_on_401_after_refresh_and_rewinds_pdf(tmp_path: Path):
    client = _client(tmp_path)
    pdf_path = tmp_path / "book.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\nbody-bytes")
    pages = [
        PageState(
            page_number=1, text="hi", is_toc=False, confidence=0.9, status="reviewed"
        )
    ]

    resp_401 = MagicMock(status_code=401, text="Token expired")
    resp_200 = MagicMock(status_code=200)
    resp_200.json.return_value = {"bookId": "new-123"}
    uploaded_payloads: list[bytes] = []

    def _fake_post(url, **kwargs):
        file_obj = kwargs["files"]["file"][1]
        uploaded_payloads.append(file_obj.read())
        return resp_401 if len(uploaded_payloads) == 1 else resp_200

    with (
        patch("kitabim_client.api.get_valid_token", return_value="old_tok"),
        patch(
            "kitabim_client.api.refresh_access_token", return_value="fresh_tok"
        ) as mock_ref,
        patch("kitabim_client.api.httpx.post", side_effect=_fake_post) as mock_post,
    ):
        result = client.push_new_book(pdf_path, pages)

    assert result == {"bookId": "new-123"}
    assert mock_ref.call_count == 1
    assert mock_post.call_count == 2
    assert uploaded_payloads == [b"%PDF-1.4\nbody-bytes", b"%PDF-1.4\nbody-bytes"]
    assert (
        mock_post.call_args_list[1].kwargs["headers"]["Authorization"]
        == "Bearer fresh_tok"
    )


def test_push_page_correction_and_get_book_pages_and_list_books_retry_on_401(
    tmp_path: Path,
):
    client = _client(tmp_path)
    page = PageState(
        page_number=2, text="fixed", is_toc=True, confidence=1.0, status="reviewed"
    )

    r401 = MagicMock(status_code=401, text="expired")
    r200_ok = MagicMock(status_code=200)
    r200_ok.json.return_value = {"status": "ok"}

    with (
        patch("kitabim_client.api.get_valid_token", return_value="old_tok"),
        patch("kitabim_client.api.refresh_access_token", return_value="fresh_tok"),
        patch(
            "kitabim_client.api.httpx.post",
            side_effect=[r401, r200_ok, r401, r200_ok],
        ) as mock_post,
    ):
        assert client.push_page_correction("b1", page) == {"status": "ok"}
    assert mock_post.call_count == 4

    batch1 = MagicMock(status_code=200)
    batch1.json.return_value = [{"pageNumber": i} for i in range(1, 101)]
    batch2 = MagicMock(status_code=200)
    batch2.json.return_value = [{"pageNumber": 101}]

    with (
        patch("kitabim_client.api.get_valid_token", return_value="old_tok"),
        patch("kitabim_client.api.refresh_access_token", return_value="fresh_tok"),
        patch(
            "kitabim_client.api.httpx.get",
            side_effect=[batch1, r401, batch2],
        ) as mock_get,
    ):
        pages = client.get_book_pages("b1")
    assert len(pages) == 101
    assert mock_get.call_count == 3


def test_book_exists_retries_on_401_and_never_returns_false_on_persistent_401(
    tmp_path: Path,
):
    from kitabim_client.api import KitabimAuthError

    client = KitabimClient(
        base_url="http://localhost:8000",
        config_path=tmp_path / "token.json",
        app_id="test-app-id",
        headless=True,
    )
    r401 = MagicMock(status_code=401, text="expired")
    r200 = MagicMock(status_code=200)

    # Recovers on 401 after refresh
    with (
        patch("kitabim_client.api.get_valid_token", return_value="old_tok"),
        patch("kitabim_client.api.refresh_access_token", return_value="fresh_tok"),
        patch("kitabim_client.api.httpx.get", side_effect=[r401, r200]),
    ):
        assert client.book_exists("b1") is True

    # On persistent 401, raises KitabimAuthError instead of falsely returning False
    with (
        patch("kitabim_client.api.get_valid_token", return_value="old_tok"),
        patch("kitabim_client.api.refresh_access_token", return_value=None),
        patch("kitabim_client.api.httpx.get", return_value=r401),
    ):
        with pytest.raises(KitabimAuthError):
            client.book_exists("b1")


def test_download_book_pdf_remints_expired_download_ticket_on_401(tmp_path: Path):
    client = _client(tmp_path)
    dest = tmp_path / "book.pdf"

    ticket_1 = MagicMock(status_code=200)
    ticket_1.json.return_value = {"download_url": "https://gcs.example/expired"}
    ticket_2 = MagicMock(status_code=200)
    ticket_2.json.return_value = {"download_url": "https://gcs.example/fresh"}

    dl_403 = MagicMock(status_code=403, text="Signature expired")
    dl_200 = MagicMock(status_code=200, content=b"%PDF-1.4\nok")

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch(
            "kitabim_client.api.httpx.post", side_effect=[ticket_1, ticket_2]
        ) as mock_post,
        patch("kitabim_client.api.httpx.get", side_effect=[dl_403, dl_200]) as mock_get,
    ):
        out = client.download_book_pdf("book123", dest)

    assert out == dest
    assert dest.read_bytes() == b"%PDF-1.4\nok"
    assert mock_post.call_count == 2
    assert mock_get.call_count == 2


def test_interactive_client_relogs_in_on_401_when_refresh_fails(tmp_path: Path):
    client = _client(tmp_path)
    assert client.headless is False
    assert client.as_headless().headless is True

    r401 = MagicMock(status_code=401, text="expired")
    r200 = MagicMock(status_code=200)
    r200.json.return_value = {"books": [], "total": 0}

    with (
        patch(
            "kitabim_client.api.get_valid_token",
            side_effect=["old_tok", "relogged_tok"],
        ) as mock_tok,
        patch("kitabim_client.api.refresh_access_token", return_value=None),
        patch("kitabim_client.api.httpx.get", side_effect=[r401, r200]) as mock_get,
    ):
        res = client.list_books()

    assert res == {"books": [], "total": 0}
    assert mock_tok.call_count == 2
    assert (
        mock_get.call_args_list[1].kwargs["headers"]["Authorization"]
        == "Bearer relogged_tok"
    )
