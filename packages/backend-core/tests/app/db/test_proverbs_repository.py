import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.proverbs import ProverbsRepository, get_proverbs_repository
from app.db.models import Proverb

@pytest.mark.asyncio
async def test_find_by_text_pattern():
    session = AsyncMock()
    repo = ProverbsRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Proverb(id=1, text="Test Proverb")]
    session.execute.return_value = mock_res
    
    res = await repo.find_by_text_pattern("test")
    assert len(res) == 1
    assert res[0].text == "Test Proverb"

@pytest.mark.asyncio
async def test_get_random_proverb():
    session = AsyncMock()
    repo = ProverbsRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Proverb(id=1, text="Random Proverb")
    session.execute.return_value = mock_res
    
    res = await repo.get_random_proverb(text_pattern="random")
    assert res is not None
    assert res.text == "Random Proverb"

@pytest.mark.asyncio
async def test_count_matching_proverbs():
    session = AsyncMock()
    repo = ProverbsRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 10
    session.execute.return_value = mock_res
    
    count = await repo.count_matching("match")
    assert count == 10

def test_get_proverbs_repository():
    session = MagicMock()
    repo = get_proverbs_repository(session)
    assert isinstance(repo, ProverbsRepository)
