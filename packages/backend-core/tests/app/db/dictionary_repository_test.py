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


@pytest.mark.asyncio
async def test_check_word_spelling_dynamic_morphology_recognizes_inflected_word():
    session = AsyncMock()
    repo = DictionaryRepository(session)

    # 1st execute: exact `Word` lookup misses `ئاپتورلىرىڭىزنىڭ`
    exact_res = MagicMock()
    exact_res.first.return_value = None

    # 2nd execute: probe lookup finds `ئاپتور`, `ئاپتورلار`, `ئاپتورى`
    probe_res = MagicMock()
    probe_res.scalars.return_value.all.return_value = [
        "ئاپتور",
        "ئاپتورلار",
        "ئاپتورى",
    ]
    session.execute.side_effect = [exact_res, probe_res]

    result = await repo.check_word_spelling("ئاپتورلىرىڭىزنىڭ")
    assert result == {
        "is_known": True,
        "word": "ئاپتورلىرىڭىزنىڭ",
        "suggestions": [],
    }


@pytest.mark.asyncio
async def test_check_word_spelling_uses_trgm_operator_with_sql_literals():
    from sqlalchemy.dialects.postgresql import asyncpg

    session = AsyncMock()
    repo = DictionaryRepository(session)

    exact_res = MagicMock()
    exact_res.first.return_value = None
    suggestions_res = MagicMock()
    suggestions_res.all.return_value = [
        MagicMock(_mapping={"id": 1, "word": "كىتاب", "score": 0.5})
    ]
    # "كىتاپ" has no morphological suffix probes, so only exact + suggestions execute
    session.execute.side_effect = [exact_res, suggestions_res]

    result = await repo.check_word_spelling("كىتاپ")
    assert result["is_known"] is False
    assert result["suggestions"] == [{"id": 1, "word": "كىتاب", "score": 0.5}]

    stmt = session.execute.call_args_list[-1].args[0]
    compiled = str(stmt.compile(dialect=asyncpg.dialect()))
    # Must use the indexable pg_trgm `%` operator rather than `similarity(...) > 0.3`
    assert " % " in compiled
    assert "> 0.3" not in compiled
    # Must use inline SQL literals (not bind params) so idx_words_norm_trgm matches
    assert "'\u06d0'" in compiled
    assert "'\u06cc'" in compiled


@pytest.mark.asyncio
async def test_check_word_spelling_short_word_uses_bounded_prefix_query():
    from sqlalchemy.dialects.postgresql import asyncpg

    session = AsyncMock()
    repo = DictionaryRepository(session)

    exact_res = MagicMock()
    exact_res.first.return_value = None
    suggestions_res = MagicMock()
    suggestions_res.all.return_value = [
        MagicMock(_mapping={"id": 2, "word": "كىت", "score": 0.4})
    ]
    session.execute.side_effect = [exact_res, suggestions_res]

    result = await repo.check_word_spelling("كى")
    assert result["is_known"] is False
    assert result["suggestions"] == [{"id": 2, "word": "كىت", "score": 0.4}]

    stmt = session.execute.call_args_list[-1].args[0]
    compiled = str(
        stmt.compile(dialect=asyncpg.dialect(), compile_kwargs={"literal_binds": True})
    )
    # Short (<3 char) lookup uses bounded prefix LIKE (`q%`) instead of `%q%`
    assert "LIKE 'ك\u06cc%'" in compiled
    assert "LIMIT 200" in compiled
