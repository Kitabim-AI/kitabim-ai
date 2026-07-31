import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.rag.retrieval import find_books_by_title_in_question


@pytest.mark.asyncio
async def test_find_books_by_title_subset_filtering():
    session = AsyncMock()
    mock_result = MagicMock()
    # Mock data in the database: (id, title, author, volume)
    mock_result.fetchall.return_value = [
        ("b1", "لېيىغان بۇلاق", "Author A", 1),
        ("b2", "لېيىغان بۇلاق", "Author A", 2),
        ("b3", "لېيىغان بۇلاق", "Author A", 3),
        ("b4", "لېيىغان بۇلاق", "Author A", 4),
        ("b5", "لېيىغان بۇلاق", "Author A", 5),
        ("b6", "لېيىغان بۇلاق", "Author A", 6),
        ("b7", "لېيىغان بۇلاق", "Author A", 7),
        ("b8", "بۇلاق", "Author B", None),
        ("b9", "مۇرات", "Author C", None),
        ("b10", "باشقا كىتاب", "Author D", None),
    ]
    session.execute.return_value = mock_result

    question = "لېيىغان بۇلاق رومانىدىكى مۇرات قانداق ۋاپات بولغان؟"
    res = await find_books_by_title_in_question(question, session)

    # We expect to match:
    # - "لېيىغان بۇلاق" (7 books)
    # "بۇلاق" must be filtered out because it is a strict subset of "لېيىغان بۇلاق".
    # "باشقا كىتاب" must not match.
    assert res is not None
    matched_ids = {r["id"] for r in res}

    # b1-b7 (لېيىغان بۇلاق) should be in matches
    expected_ids = {"b1", "b2", "b3", "b4", "b5", "b6", "b7"}
    assert matched_ids == expected_ids

    # b8 (بۇلاق) must NOT be present
    assert "b8" not in matched_ids


@pytest.mark.asyncio
async def test_find_books_by_title_quoted_multiple_titles():
    """A question quoting several titles («A» and «B» and «C») must resolve
    all of them, not just the first one the dict-iteration order happens to
    match first."""
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("b1", "ئانا يۇرت", "Author A", 1),
        ("b2", "بالىلىق خاتىرىلىرى", "Author B", None),
        ("b3", "باشقا كىتاب", "Author C", None),
    ]
    session.execute.return_value = mock_result

    question = "«ئانا يۇرت» بىلەن «بالىلىق خاتىرىلىرى» نى سېلىشتۇرۇپ بەر"
    res = await find_books_by_title_in_question(question, session)

    assert res is not None
    matched_ids = {r["id"] for r in res}
    assert matched_ids == {"b1", "b2"}
    assert "b3" not in matched_ids


@pytest.mark.asyncio
async def test_find_books_by_title_quoted_no_match_returns_none():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [
        ("b1", "ئانا يۇرت", "Author A", 1),
    ]
    session.execute.return_value = mock_result

    question = "«يوق كىتاب» توغرىسىدا ئېيتىپ بەر"
    res = await find_books_by_title_in_question(question, session)

    assert res is None


@pytest.mark.asyncio
async def test_find_books_by_title_orders_by_volume():
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute.return_value = mock_result

    await find_books_by_title_in_question("ئانا يۇرت رومانى", session)

    executed_stmt = session.execute.call_args[0][0]
    compiled = str(executed_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "ORDER BY" in compiled
    assert "volume" in compiled.lower()
