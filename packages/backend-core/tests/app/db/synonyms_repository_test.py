import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.synonyms_repository import (
    SynonymsRepository,
    get_synonyms_repository,
)
from app.db.models import Synonym


@pytest.mark.asyncio
async def test_lookup_word_exact_match():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Synonym(
        id=1, word="ئابايا", letter_group="ئا", synonyms=["بايا", "ھېلى"]
    )
    session.execute.return_value = mock_res

    res = await repo.lookup_word("ئابايا")
    assert res is not None
    assert res.word == "ئابايا"
    assert res.synonyms == ["بايا", "ھېلى"]


@pytest.mark.asyncio
async def test_lookup_word_not_found():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_res

    res = await repo.lookup_word("يوق سۆز")
    assert res is None


@pytest.mark.asyncio
async def test_lookup_word_blank_returns_none_without_query():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    res = await repo.lookup_word("   ")
    assert res is None
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_search_fuzzy_returns_matches():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Synonym(id=1, word="ئابايا", letter_group="ئا", synonyms=["بايا"])
    ]
    session.execute.return_value = mock_res

    res = await repo.search_fuzzy("ئاباي")
    assert len(res) == 1
    assert res[0].word == "ئابايا"


@pytest.mark.asyncio
async def test_search_fuzzy_blank_term_short_circuits():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    res = await repo.search_fuzzy("")
    assert res == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_list_by_letter_group():
    session = AsyncMock()
    repo = SynonymsRepository(session)

    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [
        Synonym(id=1, word="ئابايا", letter_group="ئا", synonyms=["بايا"]),
        Synonym(id=2, word="ئاباسىيە", letter_group="ئا", synonyms=["ماڭالماسلىق"]),
    ]
    session.execute.return_value = mock_res

    res = await repo.list_by_letter_group("ئا")
    assert len(res) == 2
    assert all(r.letter_group == "ئا" for r in res)


def test_get_synonyms_repository():
    session = MagicMock()
    repo = get_synonyms_repository(session)
    assert isinstance(repo, SynonymsRepository)
