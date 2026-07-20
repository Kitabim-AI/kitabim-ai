import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.auto_correct_rules_repository import (
    AutoCorrectRulesRepository,
    _format_frequent_corrections,
    invalidate_frequent_corrections_cache,
)


def test_format_frequent_corrections_groups_by_six():
    pairs = [(f"w{i}", f"c{i}") for i in range(7)]
    block = _format_frequent_corrections(pairs)
    lines = block.split("\n")
    assert len(lines) == 2
    assert lines[0].count("|") == 5
    assert lines[1] == "w6 -> c6"


def test_format_frequent_corrections_empty():
    assert _format_frequent_corrections([]) == ""


@pytest.mark.asyncio
async def test_get_active_pairs():
    session = AsyncMock()
    repo = AutoCorrectRulesRepository(session)

    row1 = MagicMock(misspelled_word="ئولار", corrected_word="ئۇلار")
    row2 = MagicMock(misspelled_word="بونداق", corrected_word="بۇنداق")
    mock_res = MagicMock()
    mock_res.__iter__.return_value = iter([row1, row2])
    session.execute.return_value = mock_res

    pairs = await repo.get_active_pairs()
    assert pairs == [("ئولار", "ئۇلار"), ("بونداق", "بۇنداق")]


@pytest.mark.asyncio
async def test_get_frequent_corrections_block_cached():
    session = AsyncMock()
    repo = AutoCorrectRulesRepository(session)

    with patch(
        "app.db.repositories.auto_correct_rules_repository.cache_service"
    ) as mock_cache:
        mock_cache.get = AsyncMock(return_value="cached block")

        block = await repo.get_frequent_corrections_block()
        assert block == "cached block"
        session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_get_frequent_corrections_block_db_and_caches():
    session = AsyncMock()
    repo = AutoCorrectRulesRepository(session)
    repo.get_active_pairs = AsyncMock(return_value=[("ئولار", "ئۇلار")])

    with patch(
        "app.db.repositories.auto_correct_rules_repository.cache_service"
    ) as mock_cache:
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock()

        block = await repo.get_frequent_corrections_block()
        assert block == "ئولار -> ئۇلار"
        mock_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_frequent_corrections_cache():
    with patch(
        "app.db.repositories.auto_correct_rules_repository.cache_service"
    ) as mock_cache:
        mock_cache.delete = AsyncMock()
        await invalidate_frequent_corrections_cache()
        mock_cache.delete.assert_called_once()
