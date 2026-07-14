import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.agent.tools import _run_get_book_summary
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
