import pytest
from unittest.mock import AsyncMock, patch

from app.db.models import Book, Page
from app.db.repositories.books_repository import BooksRepository
from app.db.repositories.pages_repository import PagesRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.rag.toc_lookup_service import resolve_short_work


def _toc_page(book_id, page_number, text):
    return Page(book_id=book_id, page_number=page_number, text=text, is_toc=True)


def _content_page(book_id, page_number, text):
    return Page(book_id=book_id, page_number=page_number, text=text, is_toc=False)


TOC_TEXT = (
    "## مۇندەرىجە\n"
    "\n"
    "| سالام دەڭ | 1 |\n"
    "| ئۇچراشقاندا | 25 |\n"
    "| غەزەل | 27 |\n"
)


@pytest.mark.asyncio
async def test_resolve_short_work_with_known_book_happy_path():
    session = AsyncMock()

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, TOC_TEXT)]

    async def fake_find_one(self, book_id, page_number):
        assert page_number == 37  # 25 (printed) + 12 (offset)
        return _content_page("b1", 37, "## ئۇچراشقاندا\n\nسەھەر كۆرگەن...")

    async def fake_find_range(self, book_id, start_page, end_page):
        assert (start_page, end_page) == (37, 38)  # up to next entry (27+12-1)
        return [
            _content_page("b1", 37, "## ئۇچراشقاندا\n\nسەھەر كۆرگەن..."),
            _content_page("b1", 38, "دېدىم: شېكەر نەدۇر؟..."),
        ]

    async def fake_get(self, book_id):
        return Book(
            id="b1",
            title="ئۆمۈر مەنزىللىرى",
            author="ئابدۇرېھىم ئۆتكۈر",
            content_page_offset=12,
            total_pages=200,
        )

    async def fake_get_value(self, key, default=None):
        assert key == "toc_short_work_max_pages"
        return "10"

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
    ):
        result = await resolve_short_work(session, "ئۇچراشقاندا", book_id="b1")

    assert result is not None
    assert result.book_id == "b1"
    assert result.start_page == 37
    assert result.end_page == 38
    assert result.truncated is False
    assert "سەھەر كۆرگەن" in result.text
    assert "شېكەر نەدۇر" in result.text
    assert result.book_title == "ئۆمۈر مەنزىللىرى"
    assert result.book_author == "ئابدۇرېھىم ئۆتكۈر"


@pytest.mark.asyncio
async def test_resolve_short_work_resolves_book_via_cross_book_toc_search_when_book_id_missing():
    session = AsyncMock()

    async def fake_search_toc(self, phrase, book_ids=None, limit=10):
        return [{"book_id": "b1", "page_number": 9, "text": TOC_TEXT, "rank": 0.9}]

    async def fake_find_toc_pages(self, book_id):
        assert book_id == "b1"
        return [_toc_page("b1", 9, TOC_TEXT)]

    async def fake_find_one(self, book_id, page_number):
        return _content_page("b1", 37, "## ئۇچراشقاندا\n\nسەھەر كۆرگەن...")

    async def fake_find_range(self, book_id, start_page, end_page):
        return [_content_page("b1", 37, "## ئۇچراشقاندا\n\nسەھەر كۆرگەن...")]

    async def fake_get(self, book_id):
        return Book(id="b1", content_page_offset=12, total_pages=200)

    async def fake_get_value(self, key, default=None):
        return "10"

    with (
        patch.object(PagesRepository, "search_toc_pages_by_phrase", fake_search_toc),
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
    ):
        result = await resolve_short_work(session, "ئۇچراشقاندا", book_id=None)

    assert result is not None
    assert result.book_id == "b1"


@pytest.mark.asyncio
async def test_resolve_short_work_returns_none_when_cross_book_search_finds_nothing():
    session = AsyncMock()

    async def fake_search_toc(self, phrase, book_ids=None, limit=10):
        return []

    with patch.object(PagesRepository, "search_toc_pages_by_phrase", fake_search_toc):
        result = await resolve_short_work(session, "يوق شېئىر", book_id=None)

    assert result is None


@pytest.mark.asyncio
async def test_resolve_short_work_returns_none_when_book_has_no_toc():
    session = AsyncMock()

    async def fake_find_toc_pages(self, book_id):
        return []

    with patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages):
        result = await resolve_short_work(session, "ئۇچراشقاندا", book_id="b1")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_short_work_returns_none_when_title_not_in_toc():
    session = AsyncMock()

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, TOC_TEXT)]

    with patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages):
        result = await resolve_short_work(session, "مەۋجۇت ئەمەس شېئىر", book_id="b1")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_short_work_rejects_long_entry_without_any_page_fetch():
    """An entry whose span (computed purely from the ToC's own printed page
    numbers, before any DB fetch) exceeds the configured cap is not a short
    work -- must reject immediately, with zero Book/page fetches."""
    session = AsyncMock()
    long_toc_text = "| ئۇزۇن باب | 1 |\n| كىيىنكى باب | 50 |\n"

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, long_toc_text)]

    async def fake_get_value(self, key, default=None):
        return "10"

    get_called = False

    async def fake_get(self, book_id):
        nonlocal get_called
        get_called = True
        return Book(id="b1", content_page_offset=5, total_pages=200)

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(BooksRepository, "get", fake_get),
    ):
        result = await resolve_short_work(session, "ئۇزۇن باب", book_id="b1")

    assert result is None
    assert get_called is False


@pytest.mark.asyncio
async def test_resolve_short_work_last_entry_uses_book_total_pages_as_bound():
    session = AsyncMock()
    toc_text = "| سالام دەڭ | 1 |\n| ئاخىرقى شېئىر | 40 |\n"

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, toc_text)]

    async def fake_get(self, book_id):
        return Book(id="b1", content_page_offset=10, total_pages=53)

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_find_one(self, book_id, page_number):
        assert page_number == 50  # 40 + 10
        return _content_page("b1", 50, "## ئاخىرقى شېئىر\n\nمەزمۇنى...")

    captured_range = {}

    async def fake_find_range(self, book_id, start_page, end_page):
        captured_range["range"] = (start_page, end_page)
        return [_content_page("b1", 50, "## ئاخىرقى شېئىر\n\nمەزمۇنى...")]

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
    ):
        result = await resolve_short_work(session, "ئاخىرقى شېئىر", book_id="b1")

    assert result is not None
    assert result.truncated is False
    # book.total_pages (53) is the bound for the last entry, not an arbitrary default.
    assert captured_range["range"] == (50, 53)
    assert result.end_page == 53


@pytest.mark.asyncio
async def test_resolve_short_work_truncates_last_entry_exceeding_cap_with_note_flag():
    session = AsyncMock()
    toc_text = "| سالام دەڭ | 1 |\n| ئاخىرقى شېئىر | 40 |\n"

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, toc_text)]

    async def fake_get(self, book_id):
        # total_pages puts the last entry's span at 40 pages -- way over the cap.
        return Book(id="b1", content_page_offset=10, total_pages=90)

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_find_one(self, book_id, page_number):
        return _content_page("b1", 50, "## ئاخىرقى شېئىر\n\nمەزمۇنى...")

    captured_range = {}

    async def fake_find_range(self, book_id, start_page, end_page):
        captured_range["range"] = (start_page, end_page)
        return [
            _content_page("b1", p, f"page {p}") for p in range(start_page, end_page + 1)
        ]

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
    ):
        result = await resolve_short_work(session, "ئاخىرقى شېئىر", book_id="b1")

    assert result is not None
    assert result.truncated is True
    assert result.end_page == 59  # start_page(50) + max_pages(10) - 1
    assert captured_range["range"] == (50, 59)


@pytest.mark.asyncio
async def test_resolve_short_work_returns_none_when_heading_verification_fails():
    """If the offset-resolved start page doesn't actually contain the title
    as a heading, the offset is stale/wrong -- fall through rather than
    return mismatched content."""
    session = AsyncMock()

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, TOC_TEXT)]

    async def fake_get(self, book_id):
        return Book(
            id="b1", content_page_offset=0, total_pages=200
        )  # wrong/stale offset

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_find_one(self, book_id, page_number):
        return _content_page("b1", page_number, "completely unrelated content")

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(PagesRepository, "find_one", fake_find_one),
    ):
        result = await resolve_short_work(session, "ئۇچراشقاندا", book_id="b1")

    assert result is None


@pytest.mark.asyncio
async def test_resolve_short_work_duplicate_titles_first_occurrence_wins():
    session = AsyncMock()
    # Small gap between the two duplicate-titled entries so the first
    # occurrence's span stays within the cap and isn't rejected by the
    # long-entry gate -- this test is about first-occurrence disambiguation,
    # not the span gate.
    toc_text = "| غەزەل | 27 |\n| غەزەل | 30 |\n"

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, toc_text)]

    async def fake_get(self, book_id):
        return Book(id="b1", content_page_offset=12, total_pages=200)

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_find_one(self, book_id, page_number):
        assert page_number == 39  # 27 + 12 -- the FIRST occurrence, not 30+12
        return _content_page("b1", 39, "## غەزەل\n\nگۈلھىدۇر...")

    async def fake_find_range(self, book_id, start_page, end_page):
        return [_content_page("b1", 39, "## غەزەل\n\nگۈلھىدۇر...")]

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
    ):
        result = await resolve_short_work(session, "غەزەل", book_id="b1")

    assert result is not None
    assert result.start_page == 39


@pytest.mark.asyncio
async def test_resolve_short_work_preserves_irregular_verse_line_breaks():
    """Regression test: a real poem's lines are rarely uniform in length and
    can carry inline footnote markers -- exactly the shape that
    clean_uyghur_text's is_poem_block heuristic misclassifies as prose and
    reflows into one paragraph (confirmed in production: a poem's verses
    were merged into running paragraphs in the chat answer). Content
    resolved via the ToC is already known to be a poem, so every line break
    from the source page must survive untouched, regardless of line shape.
    """
    session = AsyncMock()
    toc_text = "| مەن ئاق بايراق ئەمەس | 1 |\n"

    # Deliberately irregular line lengths + a mid-line period (an explicit
    # is_poem_block prose disqualifier) so this would fail that heuristic.
    page_text = (
        "## مەن ئاق بايراق ئەمەس\n"
        "\n"
        "كۆمۈش كەبى يالتىراق. مەرۋايىتتەك پارقىراق\n"
        "بىر\n"
        "چوققا ئۈستىدىكى قار ئۆزگىچە جانلانغان بىر دۇنيا كۆرگۈزىدۇ."
    )

    async def fake_find_toc_pages(self, book_id):
        return [_toc_page("b1", 9, toc_text)]

    async def fake_get(self, book_id):
        return Book(id="b1", content_page_offset=8, total_pages=200)

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_find_one(self, book_id, page_number):
        return _content_page("b1", 9, page_text)

    async def fake_find_range(self, book_id, start_page, end_page):
        return [_content_page("b1", 9, page_text)]

    with (
        patch.object(PagesRepository, "find_toc_pages", fake_find_toc_pages),
        patch.object(BooksRepository, "get", fake_get),
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(PagesRepository, "find_one", fake_find_one),
        patch.object(PagesRepository, "find_range", fake_find_range),
    ):
        result = await resolve_short_work(session, "مەن ئاق بايراق ئەمەس", book_id="b1")

    assert result is not None
    lines = result.text.split("\n")
    assert "كۆمۈش كەبى يالتىراق. مەرۋايىتتەك پارقىراق" in lines
    assert "بىر" in lines
    assert "چوققا ئۈستىدىكى قار ئۆزگىچە جانلانغان بىر دۇنيا كۆرگۈزىدۇ." in lines
