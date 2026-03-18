import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.books import BooksRepository
from app.db.models import Book

@pytest.mark.asyncio
async def test_find_by_hash():
    session = AsyncMock()
    repo = BooksRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", content_hash="h1")
    session.execute.return_value = mock_res
    book = await repo.find_by_hash("h1")
    assert book.id == "b1"

@pytest.mark.asyncio
async def test_find_by_filename():
    session = AsyncMock()
    repo = BooksRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = Book(id="b1", file_name="f1")
    session.execute.return_value = mock_res
    book = await repo.find_by_filename("f1")
    assert book.id == "b1"

@pytest.mark.asyncio
async def test_find_many():
    session = AsyncMock()
    repo = BooksRepository(session)
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = [Book(id="b1")]
    session.execute.return_value = mock_res
    books = await repo.find_many(status="ready", search_query="test")
    assert len(books) == 1

@pytest.mark.asyncio
async def test_get_batch_stats_empty_ids():
    session = AsyncMock()
    repo = BooksRepository(session)
    
    stats = await repo.get_batch_stats([])
    assert stats == {}
    session.execute.assert_not_called()

@pytest.mark.asyncio
async def test_get_batch_stats_success():
    session = AsyncMock()
    repo = BooksRepository(session)
    
    # Mocking books_info result
    mock_book_row = MagicMock()
    mock_book_row.id = "book-1"
    mock_book_row.status = "ready"
    mock_book_row.total_pages = 10
    
    mock_books_res = MagicMock()
    mock_books_res.fetchall.return_value = [mock_book_row]

    # Mocking milestone_stats result
    mock_row = MagicMock()
    mock_row.book_id = "book-1"
    mock_row.ocr = 10
    mock_row.ocr_failed = 0
    mock_row.ocr_active = 0
    mock_row.chunking = 10
    mock_row.chunking_failed = 0
    mock_row.chunking_active = 0
    mock_row.embedding = 10
    mock_row.embedding_failed = 0
    mock_row.embedding_active = 0
    mock_row.spell_check = 10
    mock_row.spell_check_failed = 0
    mock_row.spell_check_active = 0
    
    mock_stats_res = MagicMock()
    mock_stats_res.fetchall.return_value = [mock_row]
    
    # Mocking summaries result
    mock_summary_res = MagicMock()
    mock_summary_res.fetchall.return_value = []
    
    session.execute.side_effect = [mock_books_res, mock_stats_res, mock_summary_res]
    
    stats = await repo.get_batch_stats(["book-1"])
    
    assert "book-1" in stats
    assert stats["book-1"]["pipeline_stats"]["ocr"] == 10
    assert stats["book-1"]["has_summary"] == False

@pytest.mark.asyncio
async def test_get_with_page_stats_ready():
    session = AsyncMock()
    repo = BooksRepository(session)
    
    # 1. Mock get(book_id)
    # We need to mock the internal get call or the session.execute it uses
    # Since get() is from BaseRepository, let's just mock it directly on the repo instance
    mock_book = Book(id="b1", status="ready", total_pages=10, title="T1", author="A1")
    repo.get = AsyncMock(return_value=mock_book)
    
    # 2. Mock summary query
    mock_summary_res = MagicMock()
    mock_summary_res.scalar.return_value = 1
    
    # 3. Mock spell check query
    mock_row = MagicMock()
    mock_row.done = 10
    mock_row.failed = 0
    mock_row.active = 0
    mock_sc_res = MagicMock()
    mock_sc_res.fetchone.return_value = mock_row
    
    session.execute.side_effect = [mock_summary_res, mock_sc_res]
    
    result = await repo.get_with_page_stats("b1")
    
    assert result["book"].id == "b1"
    assert result["pipeline_stats"]["ocr"] == 10
    assert result["has_summary"] is True
    assert result["pipeline_stats"]["spell_check"] == 10

@pytest.mark.asyncio
async def test_get_with_page_stats_processing():
    session = AsyncMock()
    repo = BooksRepository(session)
    
    mock_book = Book(id="b1", status="processing", total_pages=10)
    repo.get = AsyncMock(return_value=mock_book)
    
    # stats_stmt result
    mock_row = MagicMock()
    mock_row.total = 10
    mock_row.ocr_done = 5
    mock_row.ocr_failed = 1
    mock_row.ocr_active = 2
    mock_row.chunking_done = 0
    mock_row.chunking_failed = 0
    mock_row.chunking_active = 0
    mock_row.embedding_done = 0
    mock_row.embedding_failed = 0
    mock_row.embedding_active = 0
    mock_row.spell_check_done = 0
    mock_row.spell_check_failed = 0
    mock_row.spell_check_active = 0
    mock_row.pending_count = 2
    mock_row.processing_count = 0
    
    mock_stats_res = MagicMock()
    mock_stats_res.fetchone.return_value = mock_row
    
    # summary query result
    mock_summary_res = MagicMock()
    mock_summary_res.scalar.return_value = 0
    
    session.execute.side_effect = [mock_stats_res, mock_summary_res]
    
    result = await repo.get_with_page_stats("b1")
    
    assert result["book"].id == "b1"
    assert result["pipeline_stats"]["ocr"] == 5
    assert result["pipeline_stats"]["ocr_failed"] == 1
    assert result["pipeline_stats"]["ocr_active"] == 2
    assert result["has_summary"] is False

@pytest.mark.asyncio
async def test_get_with_page_stats_not_found():
    session = AsyncMock()
    repo = BooksRepository(session)
    repo.get = AsyncMock(return_value=None)
    res = await repo.get_with_page_stats("non_existent")
    assert res is None

@pytest.mark.asyncio
async def test_get_with_page_stats_with_step():
    session = AsyncMock()
    repo = BooksRepository(session)
    mock_book = Book(id="b1", status="ocr_processing", total_pages=10)
    repo.get = AsyncMock(return_value=mock_book)
    
    mock_row = MagicMock()
    mock_row.total = 10
    mock_row.ocr_done = 5
    mock_row.ocr_failed = 0
    mock_row.ocr_active = 1
    
    mock_res = MagicMock()
    mock_res.fetchone.return_value = mock_row
    session.execute.return_value = mock_res
    
    res = await repo.get_with_page_stats("b1", step="ocr")
    assert res["pipeline_stats"]["ocr"] == 5

@pytest.mark.asyncio
async def test_count_by_status():
    session = AsyncMock()
    repo = BooksRepository(session)
    repo.count = AsyncMock(return_value=10)
    count = await repo.count_by_status("ready")
    assert count == 10

@pytest.mark.asyncio
async def test_count_by_visibility():
    session = AsyncMock()
    repo = BooksRepository(session)
    mock_res = MagicMock()
    mock_res.scalar_one.return_value = 5
    session.execute.return_value = mock_res
    count = await repo.count_by_visibility("public", status="ready")
    assert count == 5

@pytest.mark.asyncio
async def test_find_stale_books():
    session = AsyncMock()
    repo = BooksRepository(session)
    from datetime import datetime
    now = datetime.now()
    
    mock_res = MagicMock()
    mock_res.scalars.return_value.all.return_value = []
    session.execute.return_value = mock_res
    
    await repo.find_stale_processing_books(now)
    await repo.find_stale_pending_books(now)
    await repo.find_stale_ocr_done_books(now)
    await repo.find_stale_indexing_books(now)
    assert session.execute.call_count == 4

def test_get_books_repository():
    from app.db.repositories.books import get_books_repository
    session = AsyncMock()
    repo = get_books_repository(session)
    assert isinstance(repo, BooksRepository)


