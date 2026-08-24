import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.chat.context_grading import _build_human_message


@pytest.mark.asyncio
async def test_build_human_message_includes_book_titles_for_context_book_ids():
    """Global-mode follow-ups must surface the previous turn's book titles (not just
    opaque IDs) so the retrieval agent can judge topic continuity for itself."""
    ctx = MagicMock()
    ctx.is_global = True
    ctx.book = None
    ctx.context_book_ids = ["b1", "b2"]
    ctx.character_categories = []
    ctx.history = []
    ctx.session = AsyncMock()

    with patch("app.db.repositories.books_repository.BooksRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_titles_by_ids = AsyncMock(
            return_value=[
                {"id": "b1", "title": "Tarikhname", "author": "Author A", "volume": 1},
                {"id": "b2", "title": "Divan", "author": None, "volume": None},
            ]
        )
        message = await _build_human_message(ctx, "what happened next?")

    assert '"Tarikhname" by Author A (book_id: b1)' in message
    assert '"Divan" (book_id: b2)' in message
    assert "Previous response books:" in message
    assert "[Question]\nwhat happened next?" in message


@pytest.mark.asyncio
async def test_build_human_message_falls_back_to_ids_when_titles_not_found():
    ctx = MagicMock()
    ctx.is_global = True
    ctx.book = None
    ctx.context_book_ids = ["b1", "b2"]
    ctx.character_categories = []
    ctx.history = []
    ctx.session = AsyncMock()

    with patch("app.db.repositories.books_repository.BooksRepository") as mock_repo_cls:
        mock_repo = mock_repo_cls.return_value
        mock_repo.find_titles_by_ids = AsyncMock(return_value=[])
        message = await _build_human_message(ctx, "what happened next?")

    assert "Previous response book IDs: b1, b2" in message


@pytest.mark.asyncio
async def test_build_human_message_reader_mode_unaffected():
    """Reader-mode (single current book) context must not attempt a titles lookup —
    only the global follow-up branch touches context_book_ids."""
    book = MagicMock()
    book.title = "Current Book"
    book.author = "Author X"
    book.volume = None

    ctx = MagicMock()
    ctx.is_global = False
    ctx.book = book
    ctx.book_id = "current-book-id"
    ctx.current_page = 5
    ctx.history = []

    message = await _build_human_message(ctx, "what is on this page?")

    assert (
        'Current book: "Current Book" by Author X (book_id: current-book-id)' in message
    )
    assert "Current page: 5" in message


@pytest.mark.asyncio
async def test_build_human_message_no_context_returns_bare_question():
    ctx = MagicMock()
    ctx.is_global = True
    ctx.book = None
    ctx.context_book_ids = []
    ctx.character_categories = []
    ctx.history = []

    message = await _build_human_message(ctx, "hello")

    assert message == "hello"
