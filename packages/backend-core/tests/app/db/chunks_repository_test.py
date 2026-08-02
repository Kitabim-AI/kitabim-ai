import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db.repositories.chunks_repository import ChunksRepository
from app.db.models import Chunk, Book


@pytest.mark.asyncio
async def test_upsert_many():
    session = AsyncMock()
    repo = ChunksRepository(session)

    chunks = [
        {
            "book_id": "b1",
            "page_number": 1,
            "chunk_index": 0,
            "text": "test",
            "embedding": [0.1] * 768,
        }
    ]
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

    results = await repo.similarity_search([0.1] * 768, limit=1)

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

    results = await repo.similarity_search([0.1] * 768, book_ids=["b1"])
    assert len(results) == 1


@pytest.mark.asyncio
async def test_keyword_search_unscoped():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.rank = 0.045
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.keyword_search("سوئال", limit=5)

    assert len(results) == 1
    assert results[0]["text"] == "result"
    assert results[0]["rank"] == 0.045
    # book_ids/threshold aren't part of keyword_search's query params
    call_args = session.execute.await_args
    assert call_args.args[1]["phrase"] == "سوئال"
    assert call_args.args[1]["limit"] == 5
    query_sql = str(call_args.args[0])
    assert query_sql.count("phraseto_tsquery(") == 2
    assert "tsquery_expr" not in query_sql


@pytest.mark.asyncio
async def test_keyword_search_with_book_ids():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 1
    mock_row.text = "result"
    mock_row.rank = 0.02
    mock_row.title = "Book 1"
    mock_row.volume = 1
    mock_row.author = "Author"

    mock_res = MagicMock()
    mock_res.fetchall.return_value = [mock_row]
    session.execute.return_value = mock_res

    results = await repo.keyword_search("سوئال", book_ids=["b1"], limit=5)

    assert len(results) == 1
    call_args = session.execute.await_args
    assert call_args.args[1]["book_ids"] == ["b1"]
    assert call_args.args[1]["phrase"] == "سوئال"
    assert "phraseto_tsquery(" in str(call_args.args[0])


@pytest.mark.asyncio
async def test_keyword_search_empty_book_ids_fast_exit():
    session = AsyncMock()
    repo = ChunksRepository(session)

    results = await repo.keyword_search("سوئال", book_ids=[])

    assert results == []
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_keyword_search_passes_multi_word_phrase_through_unformatted():
    """Phrase mode hands the raw phrase to phraseto_tsquery() and lets
    Postgres build the tsquery — it must not pre-split/OR-format the words
    in Python the way the old prefix-match query did."""
    session = AsyncMock()
    repo = ChunksRepository(session)
    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("king Babur")

    call_args = session.execute.await_args
    assert call_args.args[1]["phrase"] == "king Babur"


@pytest.mark.asyncio
async def test_keyword_search_with_categories():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_res = MagicMock()
    mock_res.fetchall.return_value = []
    session.execute.return_value = mock_res

    await repo.keyword_search("سوئال", categories=["history"])

    call_args = session.execute.await_args
    assert call_args.args[1]["categories"] == ["history"]


@pytest.mark.asyncio
async def test_find_books_by_exact_phrase_returns_books_and_total():
    """The home 'Content' tab: exact-phrase search over chunk text, grouped
    by book, paginated. Distinct from keyword_search's chat-retrieval leg —
    this is a browse/discovery search, not context for an LLM answer."""
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 2

    book1 = Book(id="b1", content_hash="h1", title="Book One", author="Author A")
    book2 = Book(
        id="b2", content_hash="h2", title="Book Two", author="Author B", volume=1
    )
    mock_books_res = MagicMock()
    mock_books_res.scalars.return_value.all.return_value = [book1, book2]

    session.execute.side_effect = [mock_count_res, mock_books_res]

    books, total = await repo.find_books_by_exact_phrase("king Babur", skip=0, limit=40)

    assert total == 2
    assert len(books) == 2
    assert books[0].id == "b1"
    assert session.execute.await_count == 2


@pytest.mark.asyncio
async def test_find_books_by_exact_phrase_respects_pagination_params():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_books_res = MagicMock()
    mock_books_res.scalars.return_value.all.return_value = []
    session.execute.side_effect = [mock_count_res, mock_books_res]

    await repo.find_books_by_exact_phrase("king Babur", skip=40, limit=20)

    books_stmt = session.execute.await_args_list[1].args[0]
    compiled = str(books_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT 20" in compiled
    assert "OFFSET 40" in compiled


@pytest.mark.asyncio
async def test_find_books_by_exact_phrase_restricts_to_public_by_default():
    """Guests must not see private/draft books' content leak through the
    Content-tab search — same visibility rule as the rest of books_router."""
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_books_res = MagicMock()
    mock_books_res.scalars.return_value.all.return_value = []
    session.execute.side_effect = [mock_count_res, mock_books_res]

    await repo.find_books_by_exact_phrase("king Babur", skip=0, limit=40)

    books_stmt = session.execute.await_args_list[1].args[0]
    compiled = str(books_stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "visibility" in compiled.lower()
    assert "'ready'" in compiled or '"ready"' in compiled


@pytest.mark.asyncio
async def test_find_books_by_exact_phrase_skips_visibility_filter_when_not_restricted():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 0
    mock_books_res = MagicMock()
    mock_books_res.scalars.return_value.all.return_value = []
    session.execute.side_effect = [mock_count_res, mock_books_res]

    await repo.find_books_by_exact_phrase(
        "king Babur", skip=0, limit=40, restrict_to_public=False
    )

    books_stmt = session.execute.await_args_list[1].args[0]
    compiled = str(books_stmt.compile(compile_kwargs={"literal_binds": True})).lower()
    where_clause = compiled.split(" where ", 1)[1]
    assert "visibility" not in where_clause


def test_get_chunks_repository():
    from app.db.repositories.chunks_repository import get_chunks_repository

    session = AsyncMock()
    repo = get_chunks_repository(session)
    assert isinstance(repo, ChunksRepository)


@pytest.mark.asyncio
async def test_search_content_chunks_single_token():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 5

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 10
    mock_row.chunk_index = 0
    mock_row.text = "test snippet"
    mock_row.title = "Test Book"
    mock_row.volume = None
    mock_row.author = "Test Author"
    mock_row.cover_url = None
    mock_row.rank = 0.0

    mock_hits_res = MagicMock()
    mock_hits_res.fetchall.return_value = [mock_row]

    session.execute.side_effect = [
        MagicMock(),  # SET work_mem
        MagicMock(),  # SET statement_timeout
        mock_count_res,
        mock_hits_res,
    ]

    hits, total = await repo.search_content_chunks("ياش", skip=0, limit=40)

    assert total == 5
    assert len(hits) == 1
    assert hits[0]["book_title"] == "Test Book"
    assert hits[0]["rank"] == 0.0

    # Verify single-token SQL query omits ts_rank
    hits_query_arg = str(session.execute.await_args_list[3].args[0])
    assert "0.0 AS rank" in hits_query_arg
    assert "ts_rank" not in hits_query_arg


@pytest.mark.asyncio
async def test_search_content_chunks_multi_token():
    session = AsyncMock()
    repo = ChunksRepository(session)

    mock_count_res = MagicMock()
    mock_count_res.scalar_one.return_value = 1

    mock_row = MagicMock()
    mock_row.book_id = "b1"
    mock_row.page_number = 10
    mock_row.chunk_index = 0
    mock_row.text = "test snippet"
    mock_row.title = "Test Book"
    mock_row.volume = None
    mock_row.author = "Test Author"
    mock_row.cover_url = None
    mock_row.rank = 0.85

    mock_hits_res = MagicMock()
    mock_hits_res.fetchall.return_value = [mock_row]

    session.execute.side_effect = [
        MagicMock(),  # SET work_mem
        MagicMock(),  # SET statement_timeout
        mock_count_res,
        mock_hits_res,
    ]

    hits, total = await repo.search_content_chunks("ياش يىگىت", skip=0, limit=40)

    assert total == 1
    assert hits[0]["rank"] == 0.85

    # Verify multi-token SQL query includes ts_rank
    hits_query_arg = str(session.execute.await_args_list[3].args[0])
    assert "ts_rank" in hits_query_arg


@pytest.mark.asyncio
async def test_search_content_chunks_handles_timeout():
    session = AsyncMock()
    repo = ChunksRepository(session)

    session.execute.side_effect = Exception(
        "canceling statement due to statement timeout"
    )

    hits, total = await repo.search_content_chunks("ياش", skip=0, limit=40)

    assert hits == []
    assert total == 0
