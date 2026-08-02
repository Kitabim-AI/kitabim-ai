import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.dictionary_repository import DictionaryRepository
from app.db.models import HistoryDictionaryStaging


@pytest.mark.asyncio
async def test_create_staging_term():
    session = AsyncMock()
    repo = DictionaryRepository(session)
    staged = await repo.create_staging_term(
        book_id="book-1",
        term="سۇلتان سۇتۇق بۇغراخان",
        transliteration="Sultan Sutuk Bughra Khan",
        definition="تارىخىي شەخس",
        category="figure",
        significance_score=9,
        significance_reason="Central Karakhanid ruler",
        letter_group="س",
        sources=[{"book_id": "book-1", "book_title": "ئۇيغۇر تارىخى", "pages": [10]}],
    )
    assert staged.term == "سۇلتان سۇتۇق بۇغراخان"
    assert staged.significance_score == 9


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
        sources=[],
        status="pending",
    )

    mock_items = MagicMock()
    mock_items.scalars.return_value.all.return_value = [mock_row]

    session.execute.side_effect = [mock_count, mock_items]

    results = await repo.get_staging_terms(status="pending")
    assert results["total"] == 1
    assert len(results["items"]) == 1
    assert results["items"][0]["significanceScore"] == 9
