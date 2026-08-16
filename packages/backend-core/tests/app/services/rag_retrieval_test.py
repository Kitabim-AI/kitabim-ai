"""Tests for exact-phrase retrieval and graph lookup (services/rag/retrieval.py)

Hybrid vector+keyword RRF fusion was removed in the keyword-search rework
(keyword-search-rework-plan.md Phase 1): the keyword leg no longer blends
with vector results — it runs standalone, only for exact-phrase intent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.retrieval import exact_phrase_chunk_search


def _doc(book_id, page, **kw):
    d = {
        "book_id": book_id,
        "page_number": page,
        "text": "t",
    }
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_single_phrase_returns_leg_results():
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(
        return_value=[_doc("b1", 1, rank=0.9), _doc("b1", 2, rank=0.4)]
    )

    results = await exact_phrase_chunk_search(
        chunks_repo, ["king Babur"], book_ids=["b1"], categories=None, limit=10
    )

    chunks_repo.keyword_search.assert_awaited_once_with(
        phrase="king Babur", book_ids=["b1"], categories=None, limit=10
    )
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1), ("b1", 2)}


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_multiple_phrases_are_anded():
    """A chunk must contain ALL quoted phrases to survive — per the resolved
    decision that multiple quoted phrases in one query are ANDed."""
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(
        side_effect=[
            [_doc("b1", 1, rank=0.9), _doc("b1", 2, rank=0.5)],  # phrase 1 leg
            [_doc("b1", 1, rank=0.7)],  # phrase 2 leg — only page 1 matches both
        ]
    )

    results = await exact_phrase_chunk_search(
        chunks_repo,
        ["king Babur", "Samarkand"],
        book_ids=None,
        categories=None,
        limit=10,
    )

    assert chunks_repo.keyword_search.await_count == 2
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1)}


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_no_intersection_returns_empty():
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(
        side_effect=[
            [_doc("b1", 1)],
            [_doc("b1", 2)],
        ]
    )

    results = await exact_phrase_chunk_search(
        chunks_repo, ["a", "b"], book_ids=None, categories=None, limit=10
    )

    assert results == []


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_respects_limit():
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(
        return_value=[_doc("b1", i, rank=float(i)) for i in range(5)]
    )

    results = await exact_phrase_chunk_search(
        chunks_repo, ["x"], book_ids=None, categories=None, limit=2
    )

    assert len(results) == 2


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_no_phrases_returns_empty_without_querying():
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b1", 1)])

    results = await exact_phrase_chunk_search(
        chunks_repo, [], book_ids=None, categories=None, limit=10
    )

    assert results == []
    chunks_repo.keyword_search.assert_not_awaited()


@pytest.mark.asyncio
async def test_graph_entity_lookup_b1_prefix_enumeration():
    from app.services.rag.retrieval import graph_entity_lookup

    with (
        patch("app.services.cache_service.cache_service") as mock_cache,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
    ):
        graph_repo = AsyncMock()
        graph_repo.get_entity_facts_for_citation.return_value = [
            {"text": "Fact about Babur", "page": 10, "book_id": "b1"}
        ]
        MockGraphRepo.return_value = graph_repo

        async def mock_get(key):
            if key.startswith("rag_graph_lookup:"):
                return None
            if "پابۇر" in key:
                return ["e-babur"]
            return None

        mock_cache.get = AsyncMock(side_effect=mock_get)

        hits = await graph_entity_lookup("پابۇرنىڭ تەرجىمىھالى")

        assert len(hits) == 1
        assert hits[0]["text"] == "Fact about Babur"
        graph_repo.get_entity_facts_for_citation.assert_called_once_with("e-babur")


@pytest.mark.asyncio
async def test_graph_entity_lookup_b2_token_intersection_suppresses_noise():
    from app.services.rag.retrieval import graph_entity_lookup

    with (
        patch("app.services.cache_service.cache_service") as mock_cache,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
    ):
        graph_repo = AsyncMock()
        graph_repo.get_entity_facts_for_citation.side_effect = lambda eid: [
            {"text": f"Fact for {eid}", "page": 1, "book_id": "b1"}
        ]
        MockGraphRepo.return_value = graph_repo

        async def mock_get(key):
            if key.startswith("rag_graph_lookup:"):
                return None
            from app.services.rag.utils import normalize_uyghur
            from app.services.entity_resolution_service import normalize_alias

            full_key = normalize_alias(normalize_uyghur("زەھىرىددىن بابۇر"))
            s1_key = normalize_alias(normalize_uyghur("زەھىرىددىن"))
            s2_key = normalize_alias(normalize_uyghur("بابۇر"))
            if key.endswith(":" + full_key):
                return ["e-full"]
            elif key.endswith(":" + s1_key):
                return ["e-single1"]
            elif key.endswith(":" + s2_key):
                return ["e-single2"]
            return None

        mock_cache.get = AsyncMock(side_effect=mock_get)

        hits = await graph_entity_lookup("زەھىرىددىن بابۇر")

        hit_texts = [h["text"] for h in hits]
        assert "Fact for e-full" in hit_texts
        assert "Fact for e-single1" not in hit_texts
        assert "Fact for e-single2" not in hit_texts


@pytest.mark.asyncio
async def test_graph_entity_lookup_b3_miss_only_fuzzy_fallback():
    from app.services.rag.retrieval import graph_entity_lookup

    with (
        patch("app.services.cache_service.cache_service") as mock_cache,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
    ):
        graph_repo = AsyncMock()
        graph_repo.search_entities_fulltext.return_value = [
            {"id": "e-fuzzy", "score": 0.82}
        ]
        graph_repo.get_entity_facts_for_citation.return_value = [
            {"text": "Fuzzy hit fact", "page": 5, "book_id": "b1"}
        ]
        MockGraphRepo.return_value = graph_repo

        mock_cache.get = AsyncMock(return_value=None)

        hits = await graph_entity_lookup("مۇھەممەدخان")

        assert len(hits) == 1
        assert hits[0]["text"] == "Fuzzy hit fact"
        assert hits[0]["score"] == 0.80
        graph_repo.search_entities_fulltext.assert_called_once()


@pytest.mark.asyncio
async def test_graph_entity_lookup_respects_top_k():
    """rag_graph_top_k caps the number of facts fed into RAG context,
    keeping the highest-scoring ones (mirrors the vector/keyword legs'
    per-leg caps — see keyword-search-rework-plan.md Phase 2)."""
    from app.services.rag.retrieval import graph_entity_lookup

    with (
        patch("app.services.cache_service.cache_service") as mock_cache,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
    ):
        graph_repo = AsyncMock()
        graph_repo.get_entities_facts_for_citation_bulk.return_value = {
            "e-1": [{"text": "Fact 1", "page": 1, "book_id": "b1"}],
            "e-2": [{"text": "Fact 2", "page": 2, "book_id": "b1"}],
            "e-3": [{"text": "Fact 3", "page": 3, "book_id": "b1"}],
        }
        MockGraphRepo.return_value = graph_repo

        async def mock_get(key):
            if key.startswith("rag_graph_lookup:"):
                return None
            if key.endswith(":kitab"):
                return ["e-1", "e-2", "e-3"]
            return None

        mock_cache.get = AsyncMock(side_effect=mock_get)

        hits = await graph_entity_lookup("kitab kitab kitab", top_k=2)

        assert len(hits) == 2


@pytest.mark.asyncio
async def test_graph_entity_lookup_resolves_book_title():
    """Verify graph_entity_lookup resolves book_id to title format «Book Title» (بىلىم گىرافى)."""
    from app.services.rag.retrieval import graph_entity_lookup

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [("book-123", "مۇغۇلىستان تارىخى")]
    mock_session.execute.return_value = mock_result

    with (
        patch("app.services.cache_service.cache_service") as mock_cache,
        patch("app.db.repositories.graph_repository.GraphRepository") as MockGraphRepo,
    ):
        graph_repo = AsyncMock()
        graph_repo.get_entities_facts_for_citation_bulk.return_value = {
            "e-1": [{"text": "Fact 1", "page": 99, "book_id": "book-123"}],
        }
        MockGraphRepo.return_value = graph_repo

        async def mock_get(key):
            if key.startswith("rag_graph_lookup:"):
                return None
            if key.endswith(":mogholistan"):
                return ["e-1"]
            return None

        mock_cache.get = AsyncMock(side_effect=mock_get)

        hits = await graph_entity_lookup(
            "mogholistan mogholistan", top_k=5, session=mock_session
        )

        assert len(hits) == 1
        assert hits[0]["book_id"] == "book-123"
        assert hits[0]["title"] == "«مۇغۇلىستان تارىخى» (بىلىم گىرافى)"
        assert hits[0]["page"] == 99
