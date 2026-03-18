import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.chunks import ChunksRepository
from app.db.models import Chunk

@pytest.mark.asyncio
async def test_upsert_many():
    session = AsyncMock()
    repo = ChunksRepository(session)
    
    chunks = [{"book_id": "b1", "page_number": 1, "chunk_index": 0, "text": "test", "embedding": [0.1]*768}]
    await repo.upsert_many(chunks)
    
    assert session.execute.called
    assert session.flush.called

@pytest.mark.asyncio
async def test_delete_by_book():
    session = AsyncMock()
    repo = ChunksRepository(session)
    
    mock_res = MagicMock()
    mock_res.rowcount = 10
    session.execute.return_value = mock_res
    
    count = await repo.delete_by_book("b1")
    assert count == 10
    assert session.flush.called

@pytest.mark.asyncio
async def test_similarity_search():
    session = AsyncMock()
    repo = ChunksRepository(session)
    
    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.similarity = 0.9
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"
    
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res
    
    results = await repo.similarity_search([0.1]*768, limit=1)
    
    assert len(results) == 1
    assert results[0]["text"] == "result"
    assert results[0]["similarity"] == 0.9

@pytest.mark.asyncio
async def test_upsert_many_empty():
    session = AsyncMock()
    repo = ChunksRepository(session)
    await repo.upsert_many([])
    assert not session.execute.called

@pytest.mark.asyncio
async def test_delete_by_page():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.rowcount = 1
    session.execute.return_value = mock_res
    
    count = await repo.delete_by_page("b1", 1)
    assert count == 1
    assert session.flush.called

@pytest.mark.asyncio
async def test_find_by_book():
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Chunk(id=1)]
    session.execute.return_value = mock_res
    
    chunks = await repo.find_by_book("b1")
    assert len(chunks) == 1

@pytest.mark.asyncio
async def test_similarity_search_with_book_ids():
    session = AsyncMock()
    repo = ChunksRepository(session)
    
    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.similarity = 0.9
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"
    
    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res
    
    results = await repo.similarity_search([0.1]*768, book_ids=["b1"])
    assert len(results) == 1

def test_get_chunks_repository():
    from app.db.repositories.chunks import get_chunks_repository
    session = AsyncMock()
    repo = get_chunks_repository(session)
    assert isinstance(repo, ChunksRepository)

