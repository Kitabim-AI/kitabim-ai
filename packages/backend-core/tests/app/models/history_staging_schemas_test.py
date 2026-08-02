from app.models.schemas import HistoryStagingItem, SourceCitation


def test_source_citation_schema():
    citation = SourceCitation(
        id=1,
        book_id="book-123",
        book_title="ئۇيغۇر ئومۇمىي تارىخى",
        volume=2,
        pages=[45, 46],
    )
    assert citation.book_id == "book-123"
    assert citation.pages == [45, 46]


def test_history_staging_item_schema():
    item = HistoryStagingItem(
        id=1,
        book_id="book-123",
        term="سۇلتان سۇتۇق بۇغراخان",
        transliteration="Sultan Sutuk Bughra Khan, ? - 955",
        definition="ئوتتۇرا ئاسىيادىكى قاراخانىيلار خاندانلىقىنىڭ خانى...",
        category="figure",
        significance_score=9,
        significance_reason="Central Karakhanid ruler",
        is_ai_generated=True,
        entry_type="new",
        letter_group="س",
        sources=[],
        status="pending",
    )
    assert item.significance_score == 9
    assert item.category == "figure"
