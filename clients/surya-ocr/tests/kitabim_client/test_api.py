from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from engine.workdir import PageState
from kitabim_client.api import KitabimAPIError, KitabimClient


def _client(tmp_path: Path) -> KitabimClient:
    return KitabimClient(
        base_url="http://localhost:8000", config_path=tmp_path / "token.json"
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
    assert call.args[0] == "http://localhost:8000/books/upload-ocrd"
    assert call.kwargs["headers"]["Authorization"] == "Bearer tok123"
    assert "pages" in call.kwargs["data"]


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

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"%PDF-content"

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_response),
    ):
        result = client.download_book_pdf("book123", dest)

    assert result == dest
    assert dest.read_bytes() == b"%PDF-content"


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


def test_error_response_raises_kitabim_api_error(tmp_path: Path):
    client = _client(tmp_path)

    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_response.text = "Book not found"

    with (
        patch("kitabim_client.api.get_valid_token", return_value="tok123"),
        patch("kitabim_client.api.httpx.get", return_value=mock_response),
    ):
        with pytest.raises(KitabimAPIError):
            client.download_book_pdf("missing", tmp_path / "x.pdf")
