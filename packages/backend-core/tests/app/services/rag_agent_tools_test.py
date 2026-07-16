import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.agent.tools import _run_get_book_author, _run_get_book_summary
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.book_summaries_repository import BookSummariesRepository


class FakeBook:
    def __init__(self, id, title, author, volume):
        self.id = id
        self.title = title
        self.author = author
        self.volume = volume


@pytest.mark.asyncio
async def test_get_book_summary_expands_partial_ids_to_all_sister_volumes():
    """The LLM may under-comply with the 'pass all volumes' docstring guidance
    (observed in production with gemini-3.1-flash-lite: 6 sister volumes found,
    only 5 passed to get_book_summary). The server must not trust the LLM's
    book_ids list alone — it must expand any book_id to its full sister-volume
    set via the DB, independent of what the LLM decided to send."""
    ctx = MagicMock()
    ctx.session = AsyncMock()

    all_volumes = [
        FakeBook(f"book-{i}", "باھادىرنامە", "Author X", i) for i in range(1, 7)
    ]

    async def fake_find_sister_volumes(self, book_id):
        return all_volumes

    async def fake_get_summaries_for_books(self, book_ids, text_filter=None):
        return [
            {
                "book_id": bid,
                "summary": "s",
                "title": "باھادىرنامە",
                "author": "Author X",
                "volume": i,
            }
            for i, bid in enumerate(book_ids, start=1)
        ]

    with (
        patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes),
        patch.object(
            BookSummariesRepository,
            "get_summaries_for_books",
            fake_get_summaries_for_books,
        ),
    ):
        # LLM only passed 5 of the 6 sister volumes it discovered.
        result = await _run_get_book_summary(
            {"book_ids": ["book-1", "book-2", "book-3", "book-4", "book-5"]}, ctx
        )

    returned_ids = {s["book_id"] for s in result["summaries"]}
    assert returned_ids == {f"book-{i}" for i in range(1, 7)}


@pytest.mark.asyncio
async def test_get_book_summary_does_not_expand_unrelated_books():
    """Books with no sister volumes (find_sister_volumes returns just themselves)
    must not be expanded to unrelated books."""
    ctx = MagicMock()
    ctx.session = AsyncMock()

    async def fake_find_sister_volumes(self, book_id):
        return [FakeBook(book_id, f"Title of {book_id}", "Some Author", None)]

    async def fake_get_summaries_for_books(self, book_ids, text_filter=None):
        return [
            {
                "book_id": bid,
                "summary": "s",
                "title": f"Title of {bid}",
                "author": "Some Author",
                "volume": None,
            }
            for bid in book_ids
        ]

    with (
        patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes),
        patch.object(
            BookSummariesRepository,
            "get_summaries_for_books",
            fake_get_summaries_for_books,
        ),
    ):
        result = await _run_get_book_summary(
            {"book_ids": ["book-a", "book-b", "book-c"]}, ctx
        )

    returned_ids = {s["book_id"] for s in result["summaries"]}
    assert returned_ids == {"book-a", "book-b", "book-c"}


@pytest.mark.asyncio
async def test_get_book_author_falls_back_to_current_book_on_deictic_reference():
    """ "Who is the author of this book?" names no title, so the strict title
    match in the DB finds nothing. In reader mode ("this book" / "بۇ كىتاب"),
    the tool must answer with the book the user is currently reading instead
    of reporting no match."""
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book = FakeBook("book-1", "ئانا يۇرت", "زوردۇن سابىر", None)
    ctx.character_categories = []

    async def fake_find_author_by_title_in_question(self, question, categories=None):
        return None

    with patch.object(
        BooksRepository,
        "find_author_by_title_in_question",
        fake_find_author_by_title_in_question,
    ):
        result = await _run_get_book_author(
            {"question": "who is the author of this book"}, ctx
        )

    assert result["title"] == "ئانا يۇرت"
    assert result["author"] == "زوردۇن سابىر"


@pytest.mark.asyncio
async def test_get_book_author_falls_back_on_uyghur_deictic_reference():
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book = FakeBook("book-1", "ئانا يۇرت", "زوردۇن سابىر", None)
    ctx.character_categories = []

    async def fake_find_author_by_title_in_question(self, question, categories=None):
        return None

    with patch.object(
        BooksRepository,
        "find_author_by_title_in_question",
        fake_find_author_by_title_in_question,
    ):
        result = await _run_get_book_author(
            {"question": "بۇ كىتابنىڭ ئاپتورى كىم؟"}, ctx
        )

    assert result["title"] == "ئانا يۇرت"
    assert result["author"] == "زوردۇن سابىر"


@pytest.mark.asyncio
async def test_get_book_author_no_fallback_when_naming_unmatched_title():
    """A question that names a specific (but unmatched) title must NOT fall
    back to the current book — that would misattribute authorship."""
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book = FakeBook("book-1", "ئانا يۇرت", "زوردۇن سابىر", None)
    ctx.character_categories = []

    async def fake_find_author_by_title_in_question(self, question, categories=None):
        return None

    with patch.object(
        BooksRepository,
        "find_author_by_title_in_question",
        fake_find_author_by_title_in_question,
    ):
        result = await _run_get_book_author(
            {"question": "who wrote 'The Art of War'"}, ctx
        )

    assert result["title"] is None
    assert result["author"] is None


@pytest.mark.asyncio
async def test_get_book_author_no_fallback_in_global_mode():
    """In global (library-wide) chat there is no "current book" to fall back
    to, even if the question uses deictic phrasing."""
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = True
    ctx.book = None
    ctx.character_categories = []

    async def fake_find_author_by_title_in_question(self, question, categories=None):
        return None

    with patch.object(
        BooksRepository,
        "find_author_by_title_in_question",
        fake_find_author_by_title_in_question,
    ):
        result = await _run_get_book_author(
            {"question": "who is the author of this book"}, ctx
        )

    assert result["title"] is None
    assert result["author"] is None
