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

    fused = _fuse_rrf(vector_results, keyword_results, limit=10)

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

    fused = _fuse_rrf(vector_results, keyword_results, limit=10)

    assert fused[0]["similarity"] == 0.81


def test_fuse_rrf_keyword_only_chunk_has_no_similarity_field():
    # A keyword-only hit has no genuine cosine similarity to report.
    vector_results = []
    keyword_results = [_doc("b2", 5, rank=0.4)]

    fused = _fuse_rrf(vector_results, keyword_results, limit=10)

    assert "similarity" not in fused[0]


def test_fuse_rrf_includes_chunks_found_by_only_one_leg():
    vector_results = [_doc("b1", 1)]
    keyword_results = [_doc("b2", 5)]

    fused = _fuse_rrf(vector_results, keyword_results, limit=10)

    keys = {(d["book_id"], d["page_number"]) for d in fused}
    assert ("b1", 1) in keys
    assert ("b2", 5) in keys
    assert len(fused) == 2


def test_fuse_rrf_truncates_to_limit():
    vector_results = [_doc("b1", i) for i in range(5)]
    keyword_results = []

    fused = _fuse_rrf(vector_results, keyword_results, limit=2)

    assert len(fused) == 2


def test_fuse_rrf_no_overlap_orders_by_rank():
    # b1/1 is rank 1 (best) in vector; b2/1 is rank 1 (best) in keyword;
    # b1/2 is rank 2 in vector -> lower score than either rank-1 entry.
    vector_results = [_doc("b1", 1), _doc("b1", 2)]
    keyword_results = [_doc("b2", 1)]

    fused = _fuse_rrf(vector_results, keyword_results, limit=10)

    keys = [(d["book_id"], d["page_number"]) for d in fused]
    assert keys.index(("b1", 1)) < keys.index(("b1", 2))
    assert keys.index(("b2", 1)) < keys.index(("b1", 2))


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
