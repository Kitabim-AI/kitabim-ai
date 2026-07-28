import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rag.context import QueryContext
from app.services.rag.retrieval import vector_search
from app.services.rag.agent.reranker import rerank_context
from app.services.rag.agent.llm_routed_handler import _grade_context


@pytest.fixture
def mock_ctx():
    ctx = MagicMock(spec=QueryContext)
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    session.execute.return_value = mock_result
    ctx.session = session
    ctx.question = "Test question"
    ctx.enriched_question = None
    ctx.query_vector = [0.1] * 3072
    ctx.is_global = True
    ctx.character_categories = []
    return ctx


@pytest.mark.asyncio
async def test_vector_search_uses_dynamic_rag_top_k(mock_ctx):
    async def fake_search_chunks(
        chunks_repo,
        query_embedding,
        query_text,
        book_ids,
        categories,
        limit,
        threshold,
        hybrid_enabled,
    ):
        # Verify limit matches the dynamic rag_top_k value (10 instead of default 25)
        assert limit == 10
        return [
            {
                "text": f"Chunk {i}",
                "similarity": 0.8,
                "page_number": i,
                "title": "Title",
                "volume": None,
                "author": "Author",
                "book_id": "b1",
            }
            for i in range(10)
        ]

    with patch("app.core.providers.get_vector_store"), patch(
        "app.services.rag.retrieval._search_chunks", side_effect=fake_search_chunks
    ), patch("app.services.rag.retrieval.cache_service.get", return_value=None), patch(
        "app.services.rag.retrieval.cache_service.set", new_callable=AsyncMock
    ), patch(
        "app.db.repositories.system_configs_repository.SystemConfigsRepository"
    ) as mock_config_cls:

        async def mock_get_value(key, default=""):
            if key == "rag_top_k":
                return "10"
            if key == "rag_hybrid_search_enabled":
                return "false"
            return default

        mock_config_cls.return_value.get_value = AsyncMock(side_effect=mock_get_value)

        results = await vector_search(mock_ctx, book_ids=["b1"])
        assert len(results) == 10


@pytest.mark.asyncio
async def test_rerank_context_honors_max_chunks():
    observations = [
        {
            "tool": "search_chunks",
            "result": {
                "ok": True,
                "chunks": [
                    {
                        "book_id": f"b{i}",
                        "page": i,
                        "text": f"Content {i}",
                        "score": 0.9 - (i * 0.01),
                        "title": f"Book {i}",
                    }
                    for i in range(1, 30)
                ],
            },
        }
    ]

    with patch("app.services.rag.agent.reranker.build_text_llm") as mock_llm_builder:
        mock_llm = AsyncMock()
        # Return indices [1..29] in JSON array (matching the 29 chunks above)
        mock_llm.ainvoke.return_value = str(list(range(1, 30)))
        mock_llm_builder.return_value = mock_llm

        # Request max_chunks=5
        graded_context, before_count, after_count = await rerank_context(
            "Test question", observations, "gemini-3.1-flash-lite", max_chunks=5
        )

        assert before_count == 29
        assert after_count == 5


def test_grade_context_honors_max_chunks():
    observations = [
        {
            "tool": "search_chunks",
            "result": {
                "ok": True,
                "chunks": [
                    {
                        "book_id": f"b{i}",
                        "page": i,
                        "text": f"Content {i}",
                        "score": 0.9 - (i * 0.01),
                        "title": f"Book {i}",
                    }
                    for i in range(1, 30)
                ],
            },
        }
    ]

    graded_context, before_count, after_count = _grade_context(
        observations, max_chunks=7
    )
    assert before_count == 29
    assert after_count == 7
