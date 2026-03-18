import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.db.repositories.base import BaseRepository
from app.db.models import Book

@pytest.mark.asyncio
async def test_base_get():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    # Mocking sqlalchemy inspect and session.execute
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1")
    session.execute.return_value = mock_res
    
    with patch("sqlalchemy.inspect") as mock_inspect:
        # Mocking primary key column for inspect(Book)
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]
        
        book = await repo.get("b1")
        assert book.id == "b1"
        session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_base_get_all():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Book(id="b1"), Book(id="b2")]
    session.execute.return_value = mock_res
    
    books = await repo.get_all(skip=0, limit=2, order_by="title")
    assert len(books) == 2
    session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_base_create():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    # BaseRepository.create uses self.model(**kwargs)
    # Then session.add(), session.flush(), session.refresh()
    
    book = await repo.create(title="Title")
    assert book.title == "Title"
    session.add.assert_called_once()
    session.flush.assert_called_once()
    session.refresh.assert_called_once()

@pytest.mark.asyncio
async def test_base_update_one():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", title="new")
    session.execute.return_value = mock_res
    
    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]
        
        book = await repo.update_one("b1", title="new")
        assert book.title == "new"
        session.execute.assert_called_once()
        session.flush.assert_called_once()

@pytest.mark.asyncio
async def test_base_delete_one():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res
    
    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]
        
        res = await repo.delete_one("b1")
        assert res is True
        session.flush.called

@pytest.mark.asyncio
async def test_base_count():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 5
    session.execute.return_value = mock_res
    
    count = await repo.count(status="ready")
    assert count == 5
    session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_base_exists():
    session = AsyncMock()
    repo = BaseRepository(session, Book)
    
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 1
    session.execute.return_value = mock_res
    
    with patch("sqlalchemy.inspect") as mock_inspect:
        mock_pk = MagicMock()
        mock_inspect.return_value.primary_key = [mock_pk]
        
        exists = await repo.exists("b1")
        assert exists is True
