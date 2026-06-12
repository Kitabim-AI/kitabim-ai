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
