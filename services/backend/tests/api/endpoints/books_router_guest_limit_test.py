import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

BACKEND_DIR = str(Path(__file__).resolve().parents[3])
BACKEND_CORE_DIR = str(
    Path(__file__).resolve().parents[5] / "packages" / "backend-core"
)


def setup_paths():
    for m in list(sys.modules.keys()):
        if m == "api" or m.startswith("api."):
            del sys.modules[m]
    for p in [BACKEND_CORE_DIR, BACKEND_DIR]:
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)


class DummyPage:
    def __init__(self, page_number: int):
        self.page_number = page_number
        self.content_page_number = str(page_number)
        self.display_page_number = str(page_number)
        self.text = f"Content of page {page_number}"
        self.status = "ready"
        self.error = None
        self.last_updated = None
        self.pipeline_step = "ocr"
        self.milestone = "succeeded"
        self.is_toc = False
        self.llm_spell_check_status = "idle"
        self.llm_spell_check_at = None


def _make_mock_book():
    mock_book = MagicMock()
    mock_book.id = "book-123"
    mock_book.status = "ready"
    mock_book.visibility = "public"
    return mock_book


@pytest.mark.asyncio
async def test_guest_user_can_read_page_within_20():
    setup_paths()
    from api.endpoints.books_router import get_book_page

    mock_session = AsyncMock()
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=_make_mock_book())

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=DummyPage(20))

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
    ):
        result = await get_book_page(
            book_id="book-123",
            page_num=20,
            current_user=None,
            session=mock_session,
        )

    assert result.page_number == 20
    mock_pages_repo.find_one.assert_awaited_once_with("book-123", 20)


@pytest.mark.asyncio
async def test_guest_user_cannot_read_page_beyond_20():
    setup_paths()
    from api.endpoints.books_router import get_book_page

    mock_session = AsyncMock()
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=_make_mock_book())

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=DummyPage(21))

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await get_book_page(
                book_id="book-123",
                page_num=21,
                current_user=None,
                session=mock_session,
            )

    assert excinfo.value.status_code == 403
    mock_pages_repo.find_one.assert_not_called()


@pytest.mark.asyncio
async def test_authenticated_user_can_read_page_beyond_20():
    setup_paths()
    from api.endpoints.books_router import get_book_page

    mock_session = AsyncMock()
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=_make_mock_book())

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_one = AsyncMock(return_value=DummyPage(25))

    mock_user = MagicMock()
    mock_user.role = "reader"

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
    ):
        result = await get_book_page(
            book_id="book-123",
            page_num=25,
            current_user=mock_user,
            session=mock_session,
        )

    assert result.page_number == 25
    mock_pages_repo.find_one.assert_awaited_once_with("book-123", 25)


@pytest.mark.asyncio
async def test_guest_user_get_pages_skip_at_or_above_20_rejected():
    setup_paths()
    from api.endpoints.books_router import get_book_pages

    mock_session = AsyncMock()
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=_make_mock_book())

    mock_pages_repo = MagicMock()

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
    ):
        with pytest.raises(HTTPException) as excinfo:
            await get_book_pages(
                book_id="book-123",
                skip=20,
                limit=1,
                current_user=None,
                session=mock_session,
            )

    assert excinfo.value.status_code == 403
    mock_pages_repo.find_by_book.assert_not_called()


@pytest.mark.asyncio
async def test_guest_user_get_pages_caps_limit_to_page_20():
    setup_paths()
    from api.endpoints.books_router import get_book_pages

    mock_session = AsyncMock()
    mock_books_repo = MagicMock()
    mock_books_repo.get = AsyncMock(return_value=_make_mock_book())

    mock_pages_repo = MagicMock()
    mock_pages_repo.find_by_book = AsyncMock(
        return_value=[DummyPage(i + 1) for i in range(20)]
    )

    with (
        patch(
            "api.endpoints.books_router.BooksRepository", return_value=mock_books_repo
        ),
        patch(
            "api.endpoints.books_router.PagesRepository", return_value=mock_pages_repo
        ),
    ):
        result = await get_book_pages(
            book_id="book-123",
            skip=0,
            limit=50,
            current_user=None,
            session=mock_session,
        )

    # limit was 50, but for guest with skip=0, capped to min(50, 20) = 20
    mock_pages_repo.find_by_book.assert_awaited_once_with("book-123", skip=0, limit=20)
    assert len(result) == 20
