import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.pages import PagesRepository
from app.db.models import Page

@pytest.mark.asyncio
async def test_find_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Page(id=1, book_id="b1", page_number=1)]
    session.execute.return_value = mock_res
    
    pages = await repo.find_by_book("b1")
    assert len(pages) == 1
    assert pages[0].book_id == "b1"

@pytest.mark.asyncio
async def test_update_many_status():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 5
    session.execute.return_value = mock_res
    
    count = await repo.update_many_status("b1", [1, 2, 3], "done")
    assert count == 5
    assert session.flush.called

@pytest.mark.asyncio
async def test_delete_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 10
    session.execute.return_value = mock_res
    
    count = await repo.delete_by_book("b1")
    assert count == 10
    assert session.flush.called

@pytest.mark.asyncio
async def test_count_by_book():
    session = AsyncMock()
    repo = PagesRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 100
    session.execute.return_value = mock_res
    
    count = await repo.count_by_book("b1", status="done")
    assert count == 100

def test_get_pages_repository():
    from app.db.repositories.pages import get_pages_repository
    session = AsyncMock()
    repo = get_pages_repository(session)
    assert isinstance(repo, PagesRepository)

@pytest.mark.asyncio
async def test_find_one():
    session = AsyncMock()
    repo = PagesRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Page(id=1, book_id="b1", page_number=1)
    session.execute.return_value = mock_res
    
    page = await repo.find_one("b1", 1)
    assert page.page_number == 1

@pytest.mark.asyncio
async def test_upsert():
    session = AsyncMock()
    repo = PagesRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = Page(id=1, book_id="b1", page_number=1)
    session.execute.return_value = mock_res
    
    page_data = {"book_id": "b1", "page_number": 1, "text": "test"}
    page = await repo.upsert(page_data)
    
    assert page.id == 1
    assert session.flush.called

@pytest.mark.asyncio
async def test_update_status():
    session = AsyncMock()
    repo = PagesRepository(session)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Page(id=1, status="ready")
    session.execute.return_value = mock_res
    
    page = await repo.update_status("b1", 1, "ready")
    assert page.status == "ready"
    assert session.flush.called
