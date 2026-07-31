"""Tests for hybrid search fusion (services/rag/retrieval.py)"""

import logging

import pytest
from unittest.mock import AsyncMock, patch

from app.services.rag.retrieval import _fuse_rrf, _search_chunks


def _doc(book_id, page, chunk_index=0, **kw):
    d = {
        "book_id": book_id,
        "page_number": page,
        "chunk_index": chunk_index,
        "text": "t",
    }
    d.update(kw)
    return d


def test_fuse_rrf_combines_scores_for_overlapping_chunks():
    # "a" is rank 1 in both legs -> highest combined score
    vector_results = [_doc("b1", 1), _doc("b1", 2)]
    keyword_results = [_doc("b1", 1), _doc("b1", 3)]

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=10)

    keys = [(d["book_id"], d["page_number"]) for d in fused]
    assert keys[0] == ("b1", 1)  # appears rank-1 in both legs, highest fused score


def test_fuse_rrf_preserves_original_vector_similarity_scale():
    """The fused dict must keep the vector leg's real cosine similarity, not
    the RRF score. CONTEXT_SWITCH_SCORE_THRESHOLD (0.72) and similar absolute
    thresholds downstream (agent/tools.py, deterministic_handler.py) compare
    against this field expecting a genuine 0-1 cosine similarity — an RRF
    value (~0.01-0.03 for RRF_K=60) would always read as a weak match."""
    vector_results = [_doc("b1", 1, similarity=0.81)]
    keyword_results = []

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=10)

    assert fused[0]["similarity"] == 0.81


def test_fuse_rrf_keyword_only_chunk_has_no_similarity_field():
    # A keyword-only hit has no genuine cosine similarity to report.
    vector_results = []
    keyword_results = [_doc("b2", 5, rank=0.4)]

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=10)

    assert "similarity" not in fused[0]


def test_fuse_rrf_includes_chunks_found_by_only_one_leg():
    vector_results = [_doc("b1", 1)]
    keyword_results = [_doc("b2", 5)]

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=10)

    keys = {(d["book_id"], d["page_number"]) for d in fused}
    assert ("b1", 1) in keys
    assert ("b2", 5) in keys
    assert len(fused) == 2


def test_fuse_rrf_truncates_to_limit():
    vector_results = [_doc("b1", i) for i in range(5)]
    keyword_results = []

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=2)

    assert len(fused) == 2


def test_fuse_rrf_no_overlap_orders_by_rank():
    # b1/1 is rank 1 (best) in vector; b2/1 is rank 1 (best) in keyword;
    # b1/2 is rank 2 in vector -> lower score than either rank-1 entry.
    vector_results = [_doc("b1", 1), _doc("b1", 2)]
    keyword_results = [_doc("b2", 1)]

    fused, _ = _fuse_rrf(vector_results, keyword_results, limit=10)

    keys = [(d["book_id"], d["page_number"]) for d in fused]
    assert keys.index(("b1", 1)) < keys.index(("b1", 2))
    assert keys.index(("b2", 1)) < keys.index(("b1", 2))


def test_fuse_rrf_returns_detailed_statistics():
    vector_results = [_doc("b1", 1), _doc("b1", 2)]
    keyword_results = [_doc("b1", 2), _doc("b2", 1)]

    fused, stats = _fuse_rrf(vector_results, keyword_results, limit=2)

    assert stats["vector_hits"] == 2
    assert stats["keyword_hits"] == 2
    assert stats["fused_count"] == 2
    assert stats["final_from_vector"] == 2
    assert stats["final_from_keyword"] == 1
    assert stats["final_vector_only"] == 1
    assert stats["final_keyword_only"] == 0
    assert stats["final_both"] == 1


@pytest.mark.asyncio
async def test_search_chunks_hybrid_disabled_skips_keyword_leg():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b2", 1)])

    results = await _search_chunks(
        chunks_repo,
        query_embedding=[0.1],
        query_text="q",
        book_ids=None,
        categories=None,
        limit=5,
        threshold=0.5,
        hybrid_enabled=False,
    )

    chunks_repo.keyword_search.assert_not_awaited()
    assert results == [_doc("b1", 1)]


@pytest.mark.asyncio
async def test_search_chunks_hybrid_enabled_fuses_both_legs():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b2", 1)])

    results = await _search_chunks(
        chunks_repo,
        query_embedding=[0.1],
        query_text="q",
        book_ids=None,
        categories=None,
        limit=5,
        threshold=0.5,
        hybrid_enabled=True,
    )

    chunks_repo.keyword_search.assert_awaited_once()
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1), ("b2", 1)}


@pytest.mark.asyncio
async def test_search_chunks_keyword_leg_failure_falls_back_to_vector_only():
    chunks_repo = AsyncMock()
    vector_results = [_doc("b1", 1)]
    chunks_repo.similarity_search = AsyncMock(return_value=vector_results)
    chunks_repo.keyword_search = AsyncMock(side_effect=ValueError("malformed tsquery"))

    results = await _search_chunks(
        chunks_repo,
        query_embedding=[0.1],
        query_text="q",
        book_ids=None,
        categories=None,
        limit=5,
        threshold=0.5,
        hybrid_enabled=True,
    )

    assert results == vector_results


@pytest.mark.asyncio
async def test_search_chunks_logs_success_with_hit_counts():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(
        return_value=[_doc("b1", 1), _doc("b1", 2)]
    )
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b2", 1)])

    with patch("app.services.rag.retrieval.log_json") as mock_log:
        await _search_chunks(
            chunks_repo,
            query_embedding=[0.1],
            query_text="q",
            book_ids=None,
            categories=None,
            limit=5,
            threshold=0.5,
            hybrid_enabled=True,
        )

    mock_log.assert_called_once()
    kwargs = mock_log.call_args.kwargs
    assert kwargs["vector_hits"] == 2
    assert kwargs["keyword_hits"] == 1
    assert kwargs["fused_count"] == 3
    assert kwargs["final_from_vector"] == 2
    assert kwargs["final_from_keyword"] == 1
    assert kwargs["final_vector_only"] == 2
    assert kwargs["final_keyword_only"] == 1
    assert kwargs["final_both"] == 0
    assert mock_log.call_args.args[2] == "Hybrid search fused vector + keyword results"


@pytest.mark.asyncio
async def test_search_chunks_no_success_log_when_hybrid_disabled():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b2", 1)])

    with patch("app.services.rag.retrieval.log_json") as mock_log:
        await _search_chunks(
            chunks_repo,
            query_embedding=[0.1],
            query_text="q",
            book_ids=None,
            categories=None,
            limit=5,
            threshold=0.5,
            hybrid_enabled=False,
        )

    mock_log.assert_not_called()


@pytest.mark.asyncio
async def test_search_chunks_no_success_log_when_keyword_leg_fails():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(side_effect=ValueError("malformed tsquery"))

    with patch("app.services.rag.retrieval.log_json") as mock_log:
        await _search_chunks(
            chunks_repo,
            query_embedding=[0.1],
            query_text="q",
            book_ids=None,
            categories=None,
            limit=5,
            threshold=0.5,
            hybrid_enabled=True,
        )

    # Only the WARNING fallback log should fire, not the success log
    mock_log.assert_called_once()
    assert mock_log.call_args.args[1] == logging.WARNING


@pytest.mark.asyncio
async def test_search_chunks_hybrid_enabled_with_scoped_book_ids_runs_parallel_unscoped_keyword():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(
        side_effect=[[_doc("b1", 2)], [_doc("b2", 1)]]
    )

    results = await _search_chunks(
        chunks_repo,
        query_embedding=[0.1],
        query_text="q",
        book_ids=["b1"],
        categories=None,
        limit=5,
        threshold=0.5,
        hybrid_enabled=True,
    )

    assert chunks_repo.keyword_search.await_count == 2
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1), ("b1", 2), ("b2", 1)}


@pytest.mark.asyncio
async def test_search_chunks_in_reader_mode_disallows_unscoped_keyword():
    chunks_repo = AsyncMock()
    chunks_repo.similarity_search = AsyncMock(return_value=[_doc("b1", 1)])
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b1", 2)])

    results = await _search_chunks(
        chunks_repo,
        query_embedding=[0.1],
        query_text="q",
        book_ids=["b1"],
        categories=None,
        limit=5,
        threshold=0.5,
        hybrid_enabled=True,
        allow_unscoped_keyword=False,
    )

    assert chunks_repo.keyword_search.await_count == 1
    chunks_repo.keyword_search.assert_awaited_once_with(
        query_text="q",
        book_ids=["b1"],
        categories=None,
        limit=5,
    )
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1), ("b1", 2)}


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
