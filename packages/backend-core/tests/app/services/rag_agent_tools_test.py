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


@pytest.mark.asyncio
async def test_get_book_summary_falls_back_to_current_book_in_reader_mode():
    """When book_ids is omitted or empty in reader mode (ctx.is_global=False),
    get_book_summary must fall back to using ctx.book_id."""
    from app.services.rag.agent.tools import _run_get_book_summary

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book_id = "book-123"

    async def fake_find_sister_volumes(self, book_id):
        return [FakeBook("book-123", "ئانا يۇرت", "زوردۇن سابىر", None)]

    async def fake_get_summaries_for_books(self, book_ids, text_filter=None):
        return [
            {
                "book_id": "book-123",
                "summary": "This is the summary of Ana Yurt.",
                "title": "ئانا يۇرت",
                "author": "زوردۇن سابىر",
                "volume": None,
            }
        ]

    with (
        patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes),
        patch.object(
            BookSummariesRepository,
            "get_summaries_for_books",
            fake_get_summaries_for_books,
        ),
    ):
        # Empty args passed
        result = await _run_get_book_summary({}, ctx)

    assert len(result["summaries"]) == 1
    assert result["summaries"][0]["book_id"] == "book-123"
    assert "This is the summary of Ana Yurt." in result["context"]


@pytest.mark.asyncio
async def test_get_sister_volumes_falls_back_to_current_book_in_reader_mode():
    """When book_id is omitted or empty in reader mode, get_sister_volumes must fall back to ctx.book_id."""
    from app.services.rag.agent.tools import _run_get_sister_volumes

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book_id = "book-123"

    async def fake_find_sister_volumes(self, book_id):
        return [FakeBook("book-123", "ئانا يۇرت", "زوردۇن سابىر", 1)]

    with patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes):
        result = await _run_get_sister_volumes({}, ctx)

    assert result["book_ids"] == ["book-123"]
    assert "ئانا يۇرت" in result["context"]


@pytest.mark.asyncio
async def test_get_book_summary_falls_back_to_intro_excerpt_when_precomputed_summary_missing():
    """When a book does not have a precomputed BookSummary record in DB,
    get_book_summary must fall back to reading the first pages / intro excerpt."""
    from app.services.rag.agent.tools import _run_get_book_summary
    from app.db.repositories.pages_repository import PagesRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book_id = "book-456"

    async def fake_find_sister_volumes(self, book_id):
        return [FakeBook("book-456", "كەچكەن كۈنلەر", "ئاپتور Y", None)]

    async def fake_get_summaries_for_books(self, book_ids, text_filter=None):
        return []  # No summary in DB

    async def fake_get_book(self, book_id):
        return FakeBook("book-456", "كەچكەن كۈنلەر", "ئاپتور Y", None)

    fake_page = MagicMock()
    fake_page.text = "بۇ كىتابنىڭ كىرىش سۆزى..."

    async def fake_find_by_book(self, book_id, skip=0, limit=3):
        return [fake_page]

    with (
        patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes),
        patch.object(BooksRepository, "get", fake_get_book),
        patch.object(
            BookSummariesRepository,
            "get_summaries_for_books",
            fake_get_summaries_for_books,
        ),
        patch.object(PagesRepository, "find_first_pages_with_text", fake_find_by_book),
    ):
        result = await _run_get_book_summary({"book_ids": ["book-456"]}, ctx)

    assert "INTRO EXCERPT" in result["context"]
    assert "كەچكەن كۈنلەر" in result["context"]
    assert "بۇ كىتابنىڭ كىرىش سۆزى..." in result["context"]


@pytest.mark.asyncio
async def test_search_chunks_falls_back_to_current_book_in_reader_mode():
    """When in reader mode (ctx.is_global=False) and the LLM omits book_ids,
    search_chunks must scope the search to [ctx.book_id] instead of doing a global search."""
    from app.services.rag.agent.tools import _run_search_chunks

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.is_global = False
    ctx.book_id = "book-789"

    async def fake_embed_query(query, ctx):
        return [0.1] * 3072

    searched_book_ids = None

    async def fake_vector_search(ctx, book_ids, query_vector=None):
        nonlocal searched_book_ids
        searched_book_ids = book_ids
        return [{"text": "matching chunk", "score": 0.8}]

    with (
        patch("app.services.rag.agent.tools.embed_query", fake_embed_query),
        patch("app.services.rag.agent.tools.vector_search", fake_vector_search),
    ):
        # Empty book_ids passed
        result = await _run_search_chunks({"query": "some search query"}, ctx)

    assert searched_book_ids == ["book-789"]
    assert len(result) == 1


@pytest.mark.asyncio
async def test_get_book_summary_intro_fallback_when_initial_pages_are_empty():
    """When initial pages (cover/blank pages) have empty text, get_book_summary must
    use find_first_pages_with_text to retrieve pages with actual content."""
    from app.db.repositories.pages_repository import PagesRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()

    async def fake_find_sister_volumes(self, book_id):
        return [FakeBook("book-empty-cover", "Cover Book", "Author Z", None)]

    async def fake_get_summaries_for_books(self, book_ids, text_filter=None):
        return []  # No summary in DB

    async def fake_get_book(self, book_id):
        return FakeBook("book-empty-cover", "Cover Book", "Author Z", None)

    fake_text_page = MagicMock()
    fake_text_page.text = "بۇ كىتابنىڭ نەق مەزمۇنى..."

    async def fake_find_first_pages_with_text(self, book_id, limit=5):
        return [fake_text_page]

    with (
        patch.object(BooksRepository, "find_sister_volumes", fake_find_sister_volumes),
        patch.object(BooksRepository, "get", fake_get_book),
        patch.object(
            BookSummariesRepository,
            "get_summaries_for_books",
            fake_get_summaries_for_books,
        ),
        patch.object(
            PagesRepository,
            "find_first_pages_with_text",
            fake_find_first_pages_with_text,
        ),
    ):
        result = await _run_get_book_summary({"book_ids": ["book-empty-cover"]}, ctx)

    assert "INTRO EXCERPT" in result["context"]
    assert "Cover Book" in result["context"]
    assert "بۇ كىتابنىڭ نەق مەزمۇنى..." in result["context"]


@pytest.mark.asyncio
async def test_vector_search_falls_back_to_threshold_zero_when_scoped_search_returns_zero_hits():
    """When a scoped search (book_ids provided) returns 0 results above threshold,
    vector_search must retry similarity_search with threshold=0.0 to return top matches."""
    from app.services.rag.retrieval import vector_search

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.query_vector = [0.1] * 3072
    ctx.character_categories = []
    ctx.is_global = False

    chunks_repo_mock = AsyncMock()
    # First call with threshold=0.35 returns [], second call with threshold=0.0 returns a chunk
    chunks_repo_mock.similarity_search.side_effect = [
        [],
        [
            {
                "text": "scoped chunk fallback",
                "similarity": 0.25,
                "page_number": 1,
                "title": "Scoped Title",
                "volume": None,
                "author": "Author S",
                "book_id": "book-scoped-1",
            }
        ],
    ]

    mock_config_repo = AsyncMock()
    mock_config_repo.get_value = AsyncMock(return_value="false")

    with (
        patch("app.core.providers.get_vector_store", return_value=chunks_repo_mock),
        patch("app.services.cache_service.cache_service.get", return_value=None),
        patch("app.services.cache_service.cache_service.set", return_value=None),
        patch(
            "app.db.repositories.system_configs_repository.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
    ):
        results = await vector_search(ctx, book_ids=["book-scoped-1"])

    assert len(results) == 1
    assert results[0]["text"] == "scoped chunk fallback"
    assert chunks_repo_mock.similarity_search.call_count == 2
    # Verify second call used threshold=0.0
    second_call_kwargs = chunks_repo_mock.similarity_search.call_args_list[1].kwargs
    assert second_call_kwargs["threshold"] == 0.0
