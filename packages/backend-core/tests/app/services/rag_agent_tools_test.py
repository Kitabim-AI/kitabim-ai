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


@pytest.mark.asyncio
async def test_search_quran_returns_surah_metadata():
    from app.services.rag.agent.tools import _run_search_quran

    ctx = MagicMock()

    # Mock Quran row
    fake_verse = MagicMock()
    fake_verse.surah = 2
    fake_verse.surah_name_ug = "بەقەرە"
    fake_verse.surah_name_en = "Al-Baqara"
    fake_verse.surah_name_ar = "البقرة"
    fake_verse.ayah = 1
    fake_verse.text_ar = "الم"
    fake_verse.text_ug = "ئەلىف، لام، مىم"
    fake_verse.text_en = "Alif, Lam, Meem"

    # Mock SQL execution results
    # 1. Main query for verses
    mock_verses_result = MagicMock()
    mock_verses_result.scalars.return_value.all.return_value = [fake_verse]

    # 2. Metadata query (max ayah and names)
    mock_meta_row = MagicMock()
    mock_meta_row.surah = 2
    mock_meta_row.total_ayahs = 286
    mock_meta_row.surah_name_ug = "بەقەرە"
    mock_meta_row.surah_name_en = "Al-Baqara"
    mock_meta_row.surah_name_ar = "البقرة"

    mock_meta_result = MagicMock()
    mock_meta_result.all.return_value = [mock_meta_row]

    # Mock session
    session = AsyncMock()
    # First execute call is for verses, second execute call is for metadata
    session.execute.side_effect = [mock_verses_result, mock_meta_result]

    # Mock async context manager for db_session.async_session_factory
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = session

    with patch("app.db.session.async_session_factory", mock_factory):
        result = await _run_search_quran({"surah": 2, "ayah": 1}, ctx)

    # Check return fields
    assert "entries" in result
    assert "context" in result
    assert "surah_metadata" in result

    # Check entries
    assert len(result["entries"]) == 1
    assert result["entries"][0]["surah"] == 2
    assert result["entries"][0]["ayah"] == 1

    # Check surah_metadata dictionary
    assert "2" in result["surah_metadata"]
    assert result["surah_metadata"]["2"]["total_ayahs"] == 286
    assert result["surah_metadata"]["2"]["name_ug"] == "بەقەرە"

    # Check context text structure (should include metadata block)
    assert "[Quran Surah Metadata - Surah 2: بەقەرە (Al-Baqara)]" in result["context"]
    assert "Total Verses (Ayahs): 286" in result["context"]
    assert (
        "[Source: Holy Quran, Surah: 2 - بەقەرە (Al-Baqara), Ayah: 1]"
        in result["context"]
    )
