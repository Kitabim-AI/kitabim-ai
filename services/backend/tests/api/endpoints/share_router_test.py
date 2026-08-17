import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)
for _p in (BACKEND_CORE_DIR, BACKEND_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core.config import settings  # noqa: E402 — needs the sys.path insert above


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


def make_request(user_agent: str, url: str = "https://kitabim.ai/api/share/page/b1/5"):
    request = MagicMock()
    request.headers = {"user-agent": user_agent}
    request.url = url
    return request


def make_book(status="ready", visibility="public", title="Test Book"):
    return SimpleNamespace(status=status, visibility=visibility, title=title)


def make_page(text="Some page content."):
    return SimpleNamespace(text=text)


@pytest.mark.asyncio
async def test_share_page_redirects_non_scraper():
    setup_paths()
    from api.endpoints.share_router import share_page

    result = await share_page(
        book_id="b1",
        page_number=5,
        request=make_request("Mozilla/5.0"),
        quote=None,
        session=MagicMock(),
    )

    assert result.status_code == 302
    assert result.headers["location"] == f"{settings.frontend_base_url}/books/b1/5"


@pytest.mark.asyncio
async def test_share_page_redirects_non_scraper_with_quote():
    setup_paths()
    from api.endpoints.share_router import share_page

    result = await share_page(
        book_id="b1",
        page_number=5,
        request=make_request("Mozilla/5.0"),
        quote="a highlighted quote",
        session=MagicMock(),
    )

    assert result.status_code == 302
    assert (
        result.headers["location"]
        == f"{settings.frontend_base_url}/books/b1/5?quote=a%20highlighted%20quote"
    )


@pytest.mark.asyncio
async def test_share_page_scraper_returns_og_html_from_page_text():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return make_page(
            "Answer text [link](ref:427a5621d325:summary) (BookID: abc-123)"
        )

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch(
        "api.endpoints.share_router.BooksRepository", return_value=mock_books_repo
    ), patch(
        "api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo
    ):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    body = result.body.decode()
    assert "og:title" in body
    assert "Test Book" in body
    assert "link" in body
    assert "ref:427a5621d325" not in body
    assert "BookID" not in body


@pytest.mark.asyncio
async def test_share_page_quote_overrides_page_text_in_description():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return make_page("This is the full page text, not the quote.")

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch(
        "api.endpoints.share_router.BooksRepository", return_value=mock_books_repo
    ), patch(
        "api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo
    ):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("twitterbot"),
            quote="a specific highlighted quote",
            session=MagicMock(),
        )

    body = result.body.decode()
    assert "a specific highlighted quote" in body
    assert "This is the full page text" not in body


@pytest.mark.asyncio
async def test_share_page_redirects_when_book_private():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book(visibility="private")

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get

    with patch(
        "api.endpoints.share_router.BooksRepository", return_value=mock_books_repo
    ):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    assert result.status_code == 302


@pytest.mark.asyncio
async def test_share_page_redirects_when_page_missing():
    setup_paths()
    from api.endpoints.share_router import share_page

    async def fake_get(*args, **kwargs):
        return make_book()

    async def fake_find_one(*args, **kwargs):
        return None

    mock_books_repo = MagicMock()
    mock_books_repo.get = fake_get
    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = fake_find_one

    with patch(
        "api.endpoints.share_router.BooksRepository", return_value=mock_books_repo
    ), patch(
        "api.endpoints.share_router.PagesRepository", return_value=mock_pages_repo
    ):
        result = await share_page(
            book_id="b1",
            page_number=5,
            request=make_request("facebookexternalhit/1.1"),
            quote=None,
            session=MagicMock(),
        )

    assert result.status_code == 302
