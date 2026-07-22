import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.retrieval import embed_query, vector_search


@pytest.mark.asyncio
async def test_embed_query_uses_and_sets_cache(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)  # Cache miss
    mock_cache.set = AsyncMock()

    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query = AsyncMock(return_value=[0.1, 0.2])

    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.embeddings = mock_embeddings

    # Execute embed_query
    vector = await embed_query("hello", ctx)
    assert vector == [0.1, 0.2]

    # Verify cache was checked and set
    mock_cache.get.assert_called_once()
    mock_embeddings.aembed_query.assert_called_once_with("hello")
    mock_cache.set.assert_called_once()


@pytest.mark.asyncio
async def test_embed_query_hits_cache(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=[0.3, 0.4])  # Cache hit

    mock_embeddings = AsyncMock()

    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.embeddings = mock_embeddings

    vector = await embed_query("hello", ctx)
    assert vector == [0.3, 0.4]

    mock_cache.get.assert_called_once()
    mock_embeddings.aembed_query.assert_not_called()


@pytest.mark.asyncio
async def test_vector_search_respects_cached_empty_results(monkeypatch):
    mock_cache = AsyncMock()
    # Cache returns an EMPTY LIST (hit), not None (miss)
    mock_cache.get = AsyncMock(return_value=[])

    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.query_vector = [0.1, 0.2]
    ctx.character_categories = []
    ctx.is_global = False

    with patch(
        "app.db.repositories.chunks_repository.ChunksRepository"
    ) as mock_chunks_repo_cls:
        mock_chunks_repo = mock_chunks_repo_cls.return_value
        results = await vector_search(ctx, book_ids=["b1"])
        assert results == []

        # similarity_search should not have been called
        mock_chunks_repo.similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_vector_search_multi_book_guarantees_per_book_quota(monkeypatch):
    """A question naming several books (e.g. "compare book A, B and C") must
    not let one book's chunks crowd out the others in a single global top-K
    ranking — each named book gets its own quota of the pgvector search."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.query_vector = [0.1, 0.2]
    ctx.character_categories = []
    ctx.is_global = False
    ctx.question = "compare book A, book B, and book C"
    ctx.enriched_question = None

    book_results = {
        "b1": [
            {
                "book_id": "b1",
                "text": "b1 text",
                "similarity": 0.9,
                "page_number": 1,
                "title": "Book A",
                "volume": None,
                "author": "Author A",
            }
        ],
        "b2": [
            {
                "book_id": "b2",
                "text": "b2 text",
                "similarity": 0.95,
                "page_number": 1,
                "title": "Book B",
                "volume": None,
                "author": "Author B",
            }
        ],
        "b3": [
            {
                "book_id": "b3",
                "text": "b3 text",
                "similarity": 0.5,
                "page_number": 1,
                "title": "Book C",
                "volume": None,
                "author": "Author C",
            }
        ],
    }

    async def fake_similarity_search(
        query_embedding, book_ids, categories, limit, threshold
    ):
        assert book_ids is not None and len(book_ids) == 1
        assert limit == 8  # rag_top_k(25) // 3 books
        return book_results[book_ids[0]]

    with patch("app.db.repositories.chunks_repository.ChunksRepository") as mock_cls:
        mock_repo = mock_cls.return_value
        mock_repo.similarity_search = AsyncMock(side_effect=fake_similarity_search)

        results = await vector_search(ctx, book_ids=["b1", "b2", "b3"])

    # One similarity_search call per named book — not one shared global search.
    assert mock_repo.similarity_search.call_count == 3
    result_book_ids = {r["book_id"] for r in results}
    assert result_book_ids == {"b1", "b2", "b3"}
    # Merged and sorted by similarity across books, highest first.
    assert [r["book_id"] for r in results] == ["b2", "b1", "b3"]
