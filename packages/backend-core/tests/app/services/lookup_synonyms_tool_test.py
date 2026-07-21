import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.agent.tools import _run_lookup_synonyms
from app.db.models import Synonym


@pytest.mark.asyncio
async def test_lookup_synonyms_letter_group_mode():
    ctx = MagicMock()
    ctx.session = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.list_by_letter_group.return_value = [
        Synonym(id=1, word="ئابايا", letter_group="ئا", synonyms=["بايا"]),
        Synonym(id=2, word="ئاباسىيە", letter_group="ئا", synonyms=["ماڭالماسلىق"]),
    ]

    with patch(
        "app.db.repositories.synonyms_repository.SynonymsRepository",
        return_value=mock_repo,
    ):
        result = await _run_lookup_synonyms({"term": "ئا"}, ctx)

    mock_repo.list_by_letter_group.assert_called_once_with("ئا", limit=100)
    assert len(result["entries"]) == 2
    assert "ئابايا" in result["context"]
    assert "Letter Group" in result["context"]


@pytest.mark.asyncio
async def test_lookup_synonyms_exact_word_match():
    ctx = MagicMock()
    ctx.session = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.lookup_word.return_value = Synonym(
        id=1, word="ئابايا", letter_group="ئا", synonyms=["بايا", "ھېلى"]
    )

    with patch(
        "app.db.repositories.synonyms_repository.SynonymsRepository",
        return_value=mock_repo,
    ):
        result = await _run_lookup_synonyms({"term": "ئابايا"}, ctx)

    mock_repo.lookup_word.assert_called_once_with("ئابايا")
    mock_repo.search_fuzzy.assert_not_called()
    assert len(result["entries"]) == 1
    assert result["entries"][0]["synonyms"] == ["بايا", "ھېلى"]
    assert "بايا" in result["context"]


@pytest.mark.asyncio
async def test_lookup_synonyms_falls_back_to_fuzzy_when_no_exact_match():
    ctx = MagicMock()
    ctx.session = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.lookup_word.return_value = None
    mock_repo.search_fuzzy.return_value = [
        Synonym(id=2, word="ئاباسىيلار", letter_group="ئا", synonyms=["ئابباسىيە"])
    ]

    with patch(
        "app.db.repositories.synonyms_repository.SynonymsRepository",
        return_value=mock_repo,
    ):
        result = await _run_lookup_synonyms({"term": "ئاباس"}, ctx)

    mock_repo.lookup_word.assert_called_once_with("ئاباس")
    mock_repo.search_fuzzy.assert_called_once_with("ئاباس", limit=5)
    assert len(result["entries"]) == 1
    assert result["entries"][0]["word"] == "ئاباسىيلار"


@pytest.mark.asyncio
async def test_lookup_synonyms_no_results():
    ctx = MagicMock()
    ctx.session = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.lookup_word.return_value = None
    mock_repo.search_fuzzy.return_value = []

    with patch(
        "app.db.repositories.synonyms_repository.SynonymsRepository",
        return_value=mock_repo,
    ):
        result = await _run_lookup_synonyms({"term": "يوق سۆز"}, ctx)

    assert result["entries"] == []
    assert "No synonyms found" in result["context"]
