import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.dictionary_repository import (
    DictionaryRepository,
    _build_strict_term_where,
)
from app.db.models import HistoryDictionary, HistoryDictionaryStaging


def test_strict_term_where_excludes_loose_common_word_branch():
    # Regression for a 2026-08-03 production incident: the shared search-tolerant
    # matcher's "shares one common word + similarity > 0.4" branch caused
    # extraction dedup to false-match "تارىخى رەشىدى" (a book) against "رىم تارىخى"
    # ("History of Rome", similarity 0.47) and "سۇلتان سەئىدخان" (a person)
    # against the bare word "سۇلتان" (similarity 0.5) — silently discarding
    # every extracted entity as if it already existed. The strict matcher used
    # for dedup must never match on a single shared common word.
    clause = _build_strict_term_where(HistoryDictionary.term, "تارىخى رەشىدى")
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "0.4" not in compiled
    assert "0.7" in compiled


@pytest.mark.asyncio
async def test_create_staging_term():
    session = AsyncMock()
    repo = DictionaryRepository(session)
    staged = await repo.create_staging_term(
        book_id="book-1",
        term="سۇلتان سۇتۇق بۇغراخان",
        letter_group="س",
        transliteration="Sultan Sutuk Bughra Khan",
        category="figure",
        significance_score=9,
        significance_reason="Central Karakhanid ruler",
        facts=[
            {
                "id": 1,
                "text": "تارىخىي شەخس",
                "citations": [
                    {"book_id": "book-1", "book_title": "ئۇيغۇر تارىخى", "pages": [10]}
                ],
                "status": "active",
                "conflict_group": None,
            }
        ],
    )
    assert staged.term == "سۇلتان سۇتۇق بۇغراخان"
    assert staged.significance_score == 9
    assert staged.definition is None


@pytest.mark.asyncio
async def test_get_staging_terms():
    session = AsyncMock()
    repo = DictionaryRepository(session)

    mock_count = MagicMock()
    mock_count.scalar.return_value = 1

    mock_row = HistoryDictionaryStaging(
        id=1,
        book_id="book-1",
        term="سۇلتان سۇتۇق بۇغراخان",
        definition="تارىخىي شەخس",
        category="figure",
        significance_score=9,
        is_ai_generated=True,
        entry_type="new",
        letter_group="س",
        facts=[],
        status="pending",
    )

    mock_items = MagicMock()
    mock_items.scalars.return_value.all.return_value = [mock_row]

    session.execute.side_effect = [mock_count, mock_items]

    results = await repo.get_staging_terms(status="pending")
    assert results["total"] == 1
    assert len(results["items"]) == 1
    assert results["items"][0]["significanceScore"] == 9
