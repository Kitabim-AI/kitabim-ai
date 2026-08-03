from app.models.schemas import HistoryStagingItem, HistoryFact, FactCitation


def test_fact_citation_schema():
    citation = FactCitation(
        book_id="book-123",
        book_title="ئۇيغۇر ئومۇمىي تارىخى",
        volume=2,
        pages=[45, 46],
    )
    assert citation.book_id == "book-123"
    assert citation.pages == [45, 46]


def test_history_fact_schema_camel_case_aliases():
    fact = HistoryFact(
        id=1,
        text="ياركەند خانلىقىنىڭ خانى.",
        citations=[FactCitation(book_id="book-1", book_title="Title", pages=[10])],
        status="active",
        conflict_group=None,
    )
    dumped = fact.model_dump(by_alias=True)
    assert dumped["conflictGroup"] is None
    assert dumped["citations"][0]["bookId"] == "book-1"


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
        facts=[
            {
                "id": 1,
                "text": "قاراخانىيلار خاندانلىقىنىڭ خانى.",
                "citations": [],
                "status": "active",
                "conflict_group": None,
            }
        ],
        status="pending",
    )
    assert item.significance_score == 9
    assert item.facts[0].text == "قاراخانىيلار خاندانلىقىنىڭ خانى."
