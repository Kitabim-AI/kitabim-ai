"""Tests for exact-phrase retrieval and graph lookup (services/rag/retrieval.py)

Hybrid vector+keyword RRF fusion was removed in the keyword-search rework
(keyword-search-rework-plan.md Phase 1): the keyword leg no longer blends
with vector results — it runs standalone, only for exact-phrase intent."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.rag.retrieval import exact_phrase_chunk_search


@pytest.fixture(autouse=True)
def _db_session_factory():
    """agent_keyword_search opens its own session via
    app.db.session.async_session_factory, which is None until init_db() runs.
    Provide a mock factory by default; tests that care patch it themselves."""
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    with patch("app.db.session.async_session_factory", factory):
        yield


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
    """A page must contain ALL quoted phrases — per the resolved decision that
    multiple quoted phrases in one query are ANDed. The AND runs in the
    database (one query), not by intersecting each phrase's top-N in Python:
    two top-10 lists rarely overlap even when many pages contain both."""
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b1", 1, rank=0.7)])

    results = await exact_phrase_chunk_search(
        chunks_repo,
        ["king Babur", "Samarkand"],
        book_ids=None,
        categories=None,
        limit=10,
    )

    chunks_repo.keyword_search.assert_awaited_once_with(
        phrase="king Babur",
        book_ids=None,
        categories=None,
        limit=10,
        and_phrases=["Samarkand"],
    )
    keys = {(d["book_id"], d["page_number"]) for d in results}
    assert keys == {("b1", 1)}


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_no_page_with_all_phrases_returns_empty():
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(return_value=[])

    results = await exact_phrase_chunk_search(
        chunks_repo, ["a", "b"], book_ids=None, categories=None, limit=10
    )

    assert results == []
    assert chunks_repo.keyword_search.await_count == 1


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


@pytest.mark.asyncio
async def test_agent_keyword_search_passes_config_limit_and_scope():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.character_categories = ["history"]

    captured = {}

    async def fake_get_value(self, key, default=None):
        assert key == "rag_keyword_top_k"
        return "7"

    async def fake_keyword_search(
        self, phrase, book_ids=None, categories=None, limit=10
    ):
        captured["phrase"] = phrase
        captured["book_ids"] = book_ids
        captured["categories"] = categories
        captured["limit"] = limit
        return [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]

    with (
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
    ):
        result = await agent_keyword_search(ctx, "Yunus Khan", ["book-1"])

    assert captured == {
        "phrase": "Yunus Khan",
        "book_ids": ["book-1"],
        "categories": ["history"],
        "limit": 7,
    }
    assert result == [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]


@pytest.mark.asyncio
async def test_agent_keyword_search_falls_back_to_default_limit_on_bad_config():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.character_categories = []

    captured = {}

    async def fake_get_value(self, key, default=None):
        return "not-a-number"

    async def fake_keyword_search(
        self, phrase, book_ids=None, categories=None, limit=10
    ):
        captured["limit"] = limit
        return []

    with (
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
    ):
        await agent_keyword_search(ctx, "term", None)

    assert captured["limit"] == 10


@pytest.mark.asyncio
async def test_agent_keyword_search_empty_phrase_returns_empty_without_querying():
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()

    called = False

    async def fake_keyword_search(self, *a, **kw):
        nonlocal called
        called = True
        return []

    with patch.object(ChunksRepository, "keyword_search", fake_keyword_search):
        result = await agent_keyword_search(ctx, "   ", None)

    assert result == []
    assert called is False


@pytest.mark.asyncio
async def test_agent_keyword_search_empty_book_ids_list_broadens_to_global_scan():
    """An explicit empty book_ids list is the agent's documented "broaden to the
    whole library" signal (agent/prompts.py: "broaden by calling search_chunks
    with an empty book_ids list to search the entire library"). It must reach
    keyword_search as an unscoped (book_ids=None) search, not be silently
    short-circuited to zero results — that mismatch was the root cause of named
    short-work (e.g. poem) title lookups failing whenever discovery tools
    scoped to the wrong book(s) first."""
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock()
    ctx.character_categories = []

    captured = {}

    async def fake_get_value(self, key, default=None):
        return "10"

    async def fake_keyword_search(
        self, phrase, book_ids=None, categories=None, limit=10
    ):
        captured["book_ids"] = book_ids
        return [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]

    with (
        patch.object(SystemConfigsRepository, "get_value", fake_get_value),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
    ):
        result = await agent_keyword_search(ctx, "term", [])

    assert captured["book_ids"] is None
    assert result == [{"book_id": "b1", "page_number": 5, "text": "hit", "rank": 0.9}]


@pytest.mark.asyncio
async def test_agent_keyword_search_runs_on_its_own_session():
    """keyword_search runs SET LOCAL work_mem/statement_timeout; on the shared
    request session that would stay in force for every later query in the
    turn (e.g. the next vector search). It must use a dedicated session."""
    from app.services.rag.retrieval import agent_keyword_search
    from app.db.repositories.system_configs_repository import SystemConfigsRepository
    from app.db.repositories.chunks_repository import ChunksRepository

    ctx = MagicMock()
    ctx.session = AsyncMock(name="request_session")
    ctx.character_categories = []
    own_session = AsyncMock(name="keyword_session")

    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=own_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)

    used_sessions = []

    async def fake_keyword_search(
        self, phrase, book_ids=None, categories=None, limit=10
    ):
        used_sessions.append(self.session)
        return []

    with (
        patch.object(
            SystemConfigsRepository, "get_value", AsyncMock(return_value="10")
        ),
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
        patch("app.db.session.async_session_factory", factory),
    ):
        await agent_keyword_search(ctx, "بابۇر", None)

    assert used_sessions == [own_session]


@pytest.mark.asyncio
async def test_exact_phrase_chunk_search_three_phrases_use_one_query():
    """One query per call also means no concurrent operations on the shared
    session (asyncpg rejects those)."""
    chunks_repo = AsyncMock()
    chunks_repo.keyword_search = AsyncMock(return_value=[_doc("b1", 1, rank=0.5)])

    results = await exact_phrase_chunk_search(
        chunks_repo, ["a b", "c d", "e f"], book_ids=None, categories=None, limit=10
    )

    assert chunks_repo.keyword_search.await_count == 1
    assert chunks_repo.keyword_search.await_args.kwargs["and_phrases"] == ["c d", "e f"]
    assert len(results) == 1


@pytest.mark.asyncio
async def test_run_exact_phrase_retrieval_uses_its_own_session():
    from app.services.chat.exact_phrase import run_exact_phrase_retrieval
    from app.services.rag.phrase_intent import PhraseIntent
    from app.db.repositories.chunks_repository import ChunksRepository

    own_session = AsyncMock(name="exact_phrase_session")
    factory = MagicMock()
    factory.return_value.__aenter__ = AsyncMock(return_value=own_session)
    factory.return_value.__aexit__ = AsyncMock(return_value=False)
    used = []

    async def fake_keyword_search(
        self, phrase, book_ids=None, categories=None, limit=10
    ):
        used.append(self.session)
        return []

    intent = MagicMock(spec=PhraseIntent)
    intent.phrases = ["بابۇر شاھ"]
    with (
        patch.object(ChunksRepository, "keyword_search", fake_keyword_search),
        patch("app.db.session.async_session_factory", factory),
    ):
        await run_exact_phrase_retrieval(
            intent, book_ids=None, categories=None, limit=10
        )

    assert used == [own_session]


def _book_chunks(book_id, sims):
    return [
        {
            "book_id": book_id,
            "page_number": i,
            "similarity": s,
            "text": f"{book_id}-{i}",
        }
        for i, s in enumerate(sims)
    ]


def test_select_balanced_chunks_three_books_each_get_floor_then_fill_by_score():
    from app.services.rag.retrieval import select_balanced_chunks

    strong = _book_chunks("A", [0.9 - i * 0.01 for i in range(25)])
    weak_b = _book_chunks("B", [0.5 - i * 0.01 for i in range(10)])
    weak_c = _book_chunks("C", [0.4 - i * 0.01 for i in range(10)])

    picked = select_balanced_chunks([strong, weak_b, weak_c], top_k=25)

    by_book = {b: sum(1 for c in picked if c["book_id"] == b) for b in "ABC"}
    assert len(picked) == 25
    assert by_book == {"A": 19, "B": 3, "C": 3}
    sims = [c["similarity"] for c in picked]
    assert sims == sorted(sims, reverse=True)


def test_select_balanced_chunks_many_books_capped_at_top_k():
    """A prolific author's 30 books used to yield up to 90 chunks."""
    from app.services.rag.retrieval import select_balanced_chunks

    books = [_book_chunks(f"b{i}", [0.3 + i * 0.01, 0.2, 0.1]) for i in range(30)]

    picked = select_balanced_chunks(books, top_k=25)

    assert len(picked) == 25
    # One chunk per book, from the 25 books with the strongest best match.
    assert len({c["book_id"] for c in picked}) == 25
    assert {c["book_id"] for c in picked} == {f"b{i}" for i in range(5, 30)}


def test_select_balanced_chunks_returns_everything_when_under_top_k():
    from app.services.rag.retrieval import select_balanced_chunks

    picked = select_balanced_chunks(
        [_book_chunks("A", [0.9, 0.8]), _book_chunks("B", [0.7]), []], top_k=25
    )

    assert [c["text"] for c in picked] == ["A-0", "A-1", "B-0"]
