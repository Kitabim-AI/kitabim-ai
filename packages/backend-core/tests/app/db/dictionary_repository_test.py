import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.dictionary_repository import DictionaryRepository


@pytest.mark.asyncio
async def test_lookup_name_skips_who_is_queries():
    session = AsyncMock()
    repo = DictionaryRepository(session)

    # For a "who is" query in English, lookup_name should return [] immediately without executing any DB statement
    res_en = await repo.lookup_name("who is Mahmud Kashgari?")
    assert res_en == []
    session.execute.assert_not_called()

    # For a "who is" query in Uyghur, lookup_name should return [] immediately
    res_ug = await repo.lookup_name("ئۆمەرجان كىم؟")
    assert res_ug == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_lookup_name_queries_db_for_regular_names():
    session = AsyncMock()
    repo = DictionaryRepository(session)

    # Set up mock execute results for standard query
    mock_res = MagicMock()
    mock_res.all.return_value = [
        MagicMock(_mapping={"id": 1, "name": "ئۆمەر", "letter_group": "ئا"})
    ]
    session.execute.return_value = mock_res

    # Query for a regular name, should query the database
    res = await repo.lookup_name("ئۆمەر")
    assert len(res) == 1
    assert res[0]["name"] == "ئۆمەر"
    session.execute.assert_called_once()


def test_build_fuzzy_term_where_multi_word():
    from app.db.models import HistoryDictionary
    from app.db.repositories.dictionary_repository import _build_fuzzy_term_where

    clause = _build_fuzzy_term_where(HistoryDictionary.term, "قوقان خانلىقى")
    clause_str = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "قوقان خانلىقى" in clause_str
    assert "قوقان" in clause_str
