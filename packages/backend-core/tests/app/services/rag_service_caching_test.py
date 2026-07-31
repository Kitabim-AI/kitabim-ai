import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.retrieval import embed_query, vector_search


@pytest.mark.asyncio
async def test_vector_search_uses_keywords_override_for_keyword_leg_when_provided():
    """Agent-supplied keywords replace the whole question as the keyword-search
    leg's tsquery input, so grammatical filler words in the raw question don't
    reach the tsquery. Confirmed in production that a filler word left in can
    match ~194K rows and cost 40-60s (see ChunksRepository.keyword_search)."""
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.query_vector = [0.1] * 3072
    ctx.character_categories = []
    ctx.is_global = False
    ctx.question = "بابۇر پادىشاھنىڭ قانچە بالىسى بار؟"
    ctx.enriched_question = None

    chunks_repo_mock = AsyncMock()
    chunks_repo_mock.similarity_search = AsyncMock(
        return_value=[
            {
                "book_id": "b1",
                "text": "t",
                "similarity": 0.9,
                "page_number": 1,
                "title": "T",
                "volume": None,
                "author": "A",
            }
        ]
    )
    chunks_repo_mock.keyword_search = AsyncMock(return_value=[])

    async def mock_get_value(key, default=""):
        if key == "rag_hybrid_search_enabled":
            return "true"
        return default

    mock_config_repo = AsyncMock()
    mock_config_repo.get_value = AsyncMock(side_effect=mock_get_value)

    with (
        patch("app.core.providers.get_vector_store", return_value=chunks_repo_mock),
        patch("app.services.cache_service.cache_service.get", return_value=None),
        patch("app.services.cache_service.cache_service.set", return_value=None),
        patch(
            "app.db.repositories.system_configs_repository.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
    ):
        await vector_search(
            ctx, book_ids=["b1"], keywords=["بابۇر", "پادىشاھ", "بالىلىرى"]
        )

    call_kwargs = chunks_repo_mock.keyword_search.call_args_list[0].kwargs
    assert call_kwargs["query_text"] == "بابۇر پادىشاھ بالىلىرى"


@pytest.mark.asyncio
async def test_vector_search_falls_back_to_question_when_keywords_omitted():
    """No keywords supplied -> old behavior unchanged: the full (enriched)
    question is used for the keyword-search leg."""
    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.query_vector = [0.1] * 3072
    ctx.character_categories = []
    ctx.is_global = False
    ctx.question = "بابۇر پادىشاھنىڭ قانچە بالىسى بار؟"
    ctx.enriched_question = None

    chunks_repo_mock = AsyncMock()
    chunks_repo_mock.similarity_search = AsyncMock(
        return_value=[
            {
                "book_id": "b1",
                "text": "t",
                "similarity": 0.9,
                "page_number": 1,
                "title": "T",
                "volume": None,
                "author": "A",
            }
        ]
    )
    chunks_repo_mock.keyword_search = AsyncMock(return_value=[])

    async def mock_get_value(key, default=""):
        if key == "rag_hybrid_search_enabled":
            return "true"
        return default

    mock_config_repo = AsyncMock()
    mock_config_repo.get_value = AsyncMock(side_effect=mock_get_value)

    with (
        patch("app.core.providers.get_vector_store", return_value=chunks_repo_mock),
        patch("app.services.cache_service.cache_service.get", return_value=None),
        patch("app.services.cache_service.cache_service.set", return_value=None),
        patch(
            "app.db.repositories.system_configs_repository.SystemConfigsRepository",
            return_value=mock_config_repo,
        ),
    ):
        await vector_search(ctx, book_ids=["b1"])

    call_kwargs = chunks_repo_mock.keyword_search.call_args_list[0].kwargs
    assert call_kwargs["query_text"] == "بابۇر پادىشاھنىڭ قانچە بالىسى بار؟"


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
async def test_embed_query_handles_none_embeddings(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.embeddings = None

    vector = await embed_query("hello", ctx)
    assert vector == []


@pytest.mark.asyncio
async def test_embed_query_handles_embedding_exception(monkeypatch):
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_embeddings = AsyncMock()
    mock_embeddings.aembed_query = AsyncMock(
        side_effect=Exception("API rate limit exceeded")
    )
    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.embeddings = mock_embeddings

    vector = await embed_query("hello", ctx)
    assert vector == []


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
    ) as mock_chunks_repo_cls, patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository"
    ) as mock_config_cls:
        mock_chunks_repo = mock_chunks_repo_cls.return_value
        mock_config_cls.return_value.get_value = AsyncMock(return_value="false")
        results = await vector_search(ctx, book_ids=["b1"])
        assert results == []

        # similarity_search should not have been called
        mock_chunks_repo.similarity_search.assert_not_called()


@pytest.mark.asyncio
async def test_vector_search_global_empty_results_retries_without_threshold(
    monkeypatch,
):
    """Book-scoped searches already retry at threshold=0.0 when the first pass
    returns nothing (e.g. meta/summary questions scoring low against body
    text). A cold-start global question (no book_ids — the first turn of a
    new conversation, before any book has been discovered) hit the same
    "generic query vector scores below threshold" failure mode but had no
    retry at all, since the retry was gated on `book_ids` being truthy. This
    produced empty-context turns for well-covered topics whenever the exact
    phrasing didn't score above RAG_SCORE_THRESHOLD on the first pass."""
    mock_cache = AsyncMock()
    mock_cache.get = AsyncMock(return_value=None)
    mock_cache.set = AsyncMock()
    monkeypatch.setattr("app.services.rag.retrieval.cache_service", mock_cache)

    ctx = MagicMock()
    ctx.session = MagicMock()
    ctx.query_vector = [0.1, 0.2]
    ctx.character_categories = []
    ctx.is_global = True
    ctx.question = "who was X?"
    ctx.enriched_question = None

    calls = []

    async def fake_similarity_search(
        query_embedding, book_ids, categories, limit, threshold
    ):
        calls.append(threshold)
        if threshold > 0.0:
            return []
        return [
            {
                "book_id": "b1",
                "text": "b1 text",
                "similarity": 0.1,
                "page_number": 1,
                "title": "Book A",
                "volume": None,
                "author": "Author A",
            }
        ]

    with patch(
        "app.db.repositories.chunks_repository.ChunksRepository"
    ) as mock_cls, patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository"
    ) as mock_config_cls:
        mock_repo = mock_cls.return_value
        mock_repo.similarity_search = AsyncMock(side_effect=fake_similarity_search)
        mock_config_cls.return_value.get_value = AsyncMock(return_value="false")

        results = await vector_search(ctx, book_ids=None)

    assert calls == [pytest.approx(0.50), 0.0]
    assert len(results) == 1
    assert results[0]["book_id"] == "b1"


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

    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = MagicMock()

    with patch(
        "app.db.repositories.chunks_repository.ChunksRepository"
    ) as mock_cls, patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository"
    ) as mock_config_cls, patch("app.db.session.async_session_factory", mock_factory):
        mock_repo = mock_cls.return_value
        mock_repo.similarity_search = AsyncMock(side_effect=fake_similarity_search)

        async def mock_get_value(key, default=""):
            if key == "rag_top_k":
                return "25"
            if key == "rag_hybrid_search_enabled":
                return "false"
            return default

        mock_config_cls.return_value.get_value = AsyncMock(side_effect=mock_get_value)

        results = await vector_search(ctx, book_ids=["b1", "b2", "b3"])

    # One similarity_search call per named book — not one shared global search.
    assert mock_repo.similarity_search.call_count == 3
    result_book_ids = {r["book_id"] for r in results}
    assert result_book_ids == {"b1", "b2", "b3"}
    # Merged and sorted by similarity across books, highest first.
    assert [r["book_id"] for r in results] == ["b2", "b1", "b3"]
