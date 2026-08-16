# Entity Semantic Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up the entity-resolution semantic-matching pipeline (Item 8 of `knowledge-graph-improvement-backlog.md`) so the graph can recognize the same historical figure across differently-spelled names/titles, not just lexically-similar ones — currently the repository methods exist (`store_profile_embeddings_bulk`, `run_gds_knn_similarity`) but nothing populates or calls them.

**Architecture:** Every extracted entity gets a text "profile" (name + aliases + subtype + context summary) embedded with the same Gemini embedder used for chunks, stored as `profile_embedding` on its Neo4j node. A **native Neo4j vector index** (`db.index.vector.queryNodes`, live, incremental) is used for query-time top-K semantic candidate lookup during resolution — not the already-coded GDS batch `kNN`/graph-projection path, which requires an explicit projection-refresh lifecycle that doesn't fit a per-entity resolve call. Everything is gated behind a `system_configs` flag defaulting to **off**, and a standalone eval script validates the approach against real historical merge/review decisions already logged in Postgres before anyone flips it on.

**Tech Stack:** Python 3, SQLAlchemy (async), Neo4j Python driver (async), Gemini embeddings API (`GeminiEmbeddings`, 3072-dim), pytest + pytest-asyncio.

## Global Constraints

- No `print()` in application code (`packages/backend-core`, `services/worker`) — use `log_json`. Scripts in `scripts/` follow the existing convention there (`print()` is used throughout, e.g. `backfill_quran_embeddings.py`).
- No `os.environ.get()` in application code — use `settings.*`.
- Tuneable parameters (feature flag, weight, candidate limit) go in `system_configs` via `SystemConfigsRepository`, never hardcoded.
- Migration file first, ORM model second (not needed here — `system_configs` has no per-key model), repository third, service/job last.
- Every new capability defaults to **off** / byte-for-byte-unchanged behavior until explicitly enabled — this touches live entity-merge decisions.
- Embedding dimension is fixed at 3072 (`gemini-embedding-2`), matching the existing pgvector chunk/Quran storage convention (`Vector(3072)`/`halfvec(3072)`).

**Out of scope (deliberately not built here — YAGNI):** Items 7 (FastRP structural embeddings) and 9 (WCC cluster-based merging) from `knowledge-graph-improvement-backlog.md`. Item 7's structural signal is already approximated by the existing hand-rolled `neighbor_score` in `_graded_score`; Item 9 would restructure `resolve_entity`'s pairwise loop into cluster-based decisions, a materially bigger and riskier change than adding one new candidate source + one new scoring term. Revisit both only after Item 8 (this plan) has been validated live. The already-coded GDS batch methods (`project_gds_graph`, `run_gds_fastrp`, `run_gds_node_similarity`, `run_gds_wcc_clustering`) are untouched by this plan and remain unused.

---

## File Structure

| File | Responsibility |
|---|---|
| `packages/backend-core/migrations/088_seed_entity_semantic_matching_config.sql` (+ rollback) | Seeds the 3 new `system_configs` keys |
| `packages/backend-core/app/db/repositories/graph_repository.py` | Adds the native vector index to `init_constraints()`; adds `find_semantic_candidates()` |
| `packages/backend-core/app/services/entity_resolution_service.py` | Adds `cosine_similarity()`, `build_entity_profile_text()`, `embed_and_store_entity_profiles()`; extends `_graded_score()` with a `semantic_weight` term; extends `resolve_entity()` to fetch + merge semantic candidates |
| `services/worker/jobs/knowledge_graph_job.py` | Calls `embed_and_store_entity_profiles()` after a successful bulk graph write |
| `scripts/eval_entity_semantic_matching.py` | Standalone offline eval: replays semantic scoring against real `graph_merge_log`/`graph_resolution_reviews` history |
| `packages/backend-core/tests/app/db/graph_repository_test.py` | Updated + new tests for the vector index and `find_semantic_candidates` |
| `packages/backend-core/tests/app/services/entity_resolution_service_test.py` | New tests for the four service additions and the `resolve_entity` wiring |

---

## Task 1: Seed the `system_configs` feature-gate keys

**Files:**
- Create: `packages/backend-core/migrations/088_seed_entity_semantic_matching_config.sql`
- Create: `packages/backend-core/migrations/088_rollback_seed_entity_semantic_matching_config.sql`

**Interfaces:**
- Produces: 3 `system_configs` rows — `entity_semantic_matching_enabled` ("false"), `entity_semantic_weight` ("0.15"), `entity_semantic_candidate_limit` ("5") — consumed by Task 4/6's `config_repo.get_value(...)` calls. (Every call site also passes the same value as its Python-side default, so later tasks work correctly even before this migration is applied — but apply it first, per repo convention.)

- [ ] **Step 1: Write the migration**

```sql
-- Migration 088: Seed entity semantic-matching config
--
-- Feature-gates the semantic (embedding-based) candidate source and scoring term in
-- entity resolution (knowledge-graph-improvement-backlog.md Item 8). Defaults to off
-- so behavior is unchanged until explicitly enabled and validated via
-- scripts/eval_entity_semantic_matching.py.

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_matching_enabled',
    'false',
    'Gate for embedding-based semantic candidate matching in entity resolution (knowledge-graph-improvement-backlog.md Item 8). "true" to enable; also gates whether entity profile embeddings are generated during extraction.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_weight',
    '0.15',
    'Weight (0.0-1.0) given to profile-embedding cosine similarity in the entity-resolution graded score, when entity_semantic_matching_enabled is true. The remaining weight is distributed proportionally across the existing name/neighbor/subtype signals.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;

INSERT INTO system_configs (key, value, description, updated_at)
VALUES (
    'entity_semantic_candidate_limit',
    '5',
    'Max semantic-similarity candidates fetched per entity from the Neo4j vector index during resolution, in addition to the existing fulltext candidates.',
    NOW()
)
ON CONFLICT (key) DO NOTHING;
```

- [ ] **Step 2: Write the rollback**

```sql
-- Rollback Migration 088: Delete entity semantic-matching config

DELETE FROM system_configs WHERE key = 'entity_semantic_matching_enabled';
DELETE FROM system_configs WHERE key = 'entity_semantic_weight';
DELETE FROM system_configs WHERE key = 'entity_semantic_candidate_limit';
```

- [ ] **Step 3: Apply locally and verify**

Run:
```bash
docker exec -i $(docker compose ps -q postgres) \
    psql -U postgres kitabim < packages/backend-core/migrations/088_seed_entity_semantic_matching_config.sql
docker exec -i $(docker compose ps -q postgres) \
    psql -U postgres kitabim -c "SELECT key, value FROM system_configs WHERE key LIKE 'entity_semantic%' ORDER BY key;"
```
Expected: 3 rows — `entity_semantic_candidate_limit | 5`, `entity_semantic_matching_enabled | false`, `entity_semantic_weight | 0.15`.

- [ ] **Step 4: Commit**

```bash
git add packages/backend-core/migrations/088_seed_entity_semantic_matching_config.sql \
        packages/backend-core/migrations/088_rollback_seed_entity_semantic_matching_config.sql
git commit -m "feat: seed entity semantic-matching config keys (default off)"
```

---

## Task 2: Add the native Neo4j vector index

**Files:**
- Modify: `packages/backend-core/app/db/repositories/graph_repository.py:87-123` (`init_constraints`)
- Test: `packages/backend-core/tests/app/db/graph_repository_test.py:22-43` (`test_graph_repository_init_constraints`)

**Interfaces:**
- Produces: Neo4j vector index named `entity_profile_embedding_idx` on `Entity.profile_embedding`, 3072 dimensions, cosine similarity — consumed by Task 3's `find_semantic_candidates`.

- [ ] **Step 1: Update the failing test first**

Modify `test_graph_repository_init_constraints` in `packages/backend-core/tests/app/db/graph_repository_test.py`:

```python
@pytest.mark.asyncio
async def test_graph_repository_init_constraints():
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        await repo.init_constraints()

        # DROP entity_name_unique, CREATE entity_id_unique, 2 entity btree indexes,
        # 1 fulltext index, 4 relationship indexes, 1 vector index
        assert mock_session.run.call_count == 10
        statements = [c[0][0] for c in mock_session.run.call_args_list]
        assert any("DROP CONSTRAINT entity_name_unique" in s for s in statements)
        assert any("CREATE CONSTRAINT entity_id_unique" in s for s in statements)
        assert any("CREATE FULLTEXT INDEX entity_search_idx" in s for s in statements)
        assert any(
            "CREATE VECTOR INDEX entity_profile_embedding_idx" in s
            for s in statements
        )

        await GraphRepository.close_driver()
        assert mock_driver.close.called
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/db/graph_repository_test.py::test_graph_repository_init_constraints -v`
Expected: FAIL — `assert 9 == 10`

- [ ] **Step 3: Add the vector index statement**

In `packages/backend-core/app/db/repositories/graph_repository.py`, modify the `statements` list inside `init_constraints` (currently lines 97-107):

```python
        statements = [
            "DROP CONSTRAINT entity_name_unique IF EXISTS;",
            "CREATE CONSTRAINT entity_id_unique IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE;",
            "CREATE INDEX entity_canonical_name_idx IF NOT EXISTS FOR (e:Entity) ON (e.canonical_name);",
            "CREATE INDEX entity_aliases_idx IF NOT EXISTS FOR (e:Entity) ON (e.aliases);",
            "CREATE FULLTEXT INDEX entity_search_idx IF NOT EXISTS FOR (e:Entity) ON EACH [e.canonical_name, e.aliases];",
            "CREATE INDEX rel_book_id_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.book_id);",
            "CREATE INDEX rel_rel_type_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.rel_type);",
            "CREATE INDEX rel_id_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.id);",
            "CREATE INDEX rel_chunk_refs_idx IF NOT EXISTS FOR ()-[r:RELATED_TO]-() ON (r.chunk_refs);",
            """
            CREATE VECTOR INDEX entity_profile_embedding_idx IF NOT EXISTS
            FOR (e:Entity) ON (e.profile_embedding)
            OPTIONS { indexConfig: {
                `vector.dimensions`: 3072,
                `vector.similarity_function`: 'cosine'
            }};
            """,
        ]
```

Also update the docstring's index list at lines 88-96 to mention the new vector index (one line, same style as the existing `entity_search_idx` note).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/db/graph_repository_test.py::test_graph_repository_init_constraints -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/db/repositories/graph_repository.py \
        packages/backend-core/tests/app/db/graph_repository_test.py
git commit -m "feat: add native Neo4j vector index for entity profile embeddings"
```

---

## Task 3: `GraphRepository.find_semantic_candidates`

**Files:**
- Modify: `packages/backend-core/app/db/repositories/graph_repository.py` (add method near `find_resolution_candidates`, after line 485)
- Test: `packages/backend-core/tests/app/db/graph_repository_test.py`

**Interfaces:**
- Consumes: `entity_profile_embedding_idx` (Task 2).
- Produces: `async def find_semantic_candidates(self, entity_id: str, embedding: List[float], scope: str, book_id: Optional[str] = None, limit: int = 5) -> List[Dict[str, Any]]`, returning dicts shaped like `find_resolution_candidates`'s output (`id`, `canonical_name`, `aliases`, `type`, `subtype`, `scope`, `book_id`, `year_hijri`, `year_gregorian`, `century_gregorian`) — consumed by Task 6's `resolve_entity`.

- [ ] **Step 1: Write the failing test**

Add to `packages/backend-core/tests/app/db/graph_repository_test.py`:

```python
@pytest.mark.asyncio
async def test_graph_repository_find_semantic_candidates():
    mock_result = AsyncMock()
    mock_result.data.return_value = [
        {"id": "cand-1", "canonical_name": "Temur Barlas", "score": 0.91}
    ]
    mock_session = AsyncMock()
    mock_session.__aenter__.return_value = mock_session
    mock_session.run.return_value = mock_result
    mock_driver = _mock_driver_session(mock_session)

    with patch(
        "app.db.repositories.graph_repository.AsyncGraphDatabase.driver",
        return_value=mock_driver,
    ):
        repo = GraphRepository()
        records = await repo.find_semantic_candidates(
            entity_id="e1",
            embedding=[0.1, 0.2, 0.3],
            scope="nonfiction",
            book_id=None,
            limit=5,
        )

        assert records == [
            {"id": "cand-1", "canonical_name": "Temur Barlas", "score": 0.91}
        ]
        assert mock_session.run.called
        call_args = mock_session.run.call_args[0]
        call_kwargs = mock_session.run.call_args[1]
        assert "db.index.vector.queryNodes" in call_args[0]
        assert "entity_profile_embedding_idx" in call_args[0]
        assert call_kwargs["embedding"] == [0.1, 0.2, 0.3]
        assert call_kwargs["entity_id"] == "e1"
        assert call_kwargs["scope"] == "nonfiction"
        assert call_kwargs["book_id"] is None
        assert call_kwargs["k"] == 6
        assert call_kwargs["limit"] == 5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest packages/backend-core/tests/app/db/graph_repository_test.py::test_graph_repository_find_semantic_candidates -v`
Expected: FAIL — `AttributeError: 'GraphRepository' object has no attribute 'find_semantic_candidates'`

- [ ] **Step 3: Implement the method**

Add to `packages/backend-core/app/db/repositories/graph_repository.py`, directly after `find_resolution_candidates` (after line 485, before `search_entities_fulltext`):

```python
    async def find_semantic_candidates(
        self,
        entity_id: str,
        embedding: List[float],
        scope: str,
        book_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """Live per-entity semantic candidate lookup via the native Neo4j vector index
        (`entity_profile_embedding_idx`, Task 2). Unlike the GDS `kNN` methods below
        (Items 6-9), this needs no graph projection/refresh lifecycle — the index
        updates incrementally as `profile_embedding` is written, so a query always
        sees current data.

        Returns candidates shaped like `find_resolution_candidates`'s output so both
        candidate sources merge into one list in `resolve_entity` without reshaping.
        Requests one extra result (`k = limit + 1`) since the entity's own node is
        always the top hit against its own embedding and is filtered out below.
        """
        query = """
        CALL db.index.vector.queryNodes('entity_profile_embedding_idx', $k, $embedding)
        YIELD node, score
        WHERE node.id <> $entity_id
          AND node.scope = $scope
          AND coalesce(node.resolution_status, 'unresolved') <> 'resolving'
          AND ($book_id IS NULL OR node.book_id = $book_id)
        RETURN node.id AS id, node.canonical_name AS canonical_name, node.aliases AS aliases,
               node.type AS type, node.subtype AS subtype, node.scope AS scope, node.book_id AS book_id,
               node.year_hijri AS year_hijri, node.year_gregorian AS year_gregorian,
               node.century_gregorian AS century_gregorian, score
        ORDER BY score DESC
        LIMIT $limit
        """
        async with self._driver.session() as session:
            result = await session.run(
                query,
                embedding=embedding,
                entity_id=entity_id,
                scope=scope,
                book_id=book_id,
                k=limit + 1,
                limit=limit,
            )
            return await result.data()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest packages/backend-core/tests/app/db/graph_repository_test.py::test_graph_repository_find_semantic_candidates -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add packages/backend-core/app/db/repositories/graph_repository.py \
        packages/backend-core/tests/app/db/graph_repository_test.py
git commit -m "feat: add GraphRepository.find_semantic_candidates via native vector index"
```

---

## Task 4: Entity-resolution service additions (embedding, text-building, cosine similarity, scoring)

**Files:**
- Modify: `packages/backend-core/app/services/entity_resolution_service.py`
- Test: `packages/backend-core/tests/app/services/entity_resolution_service_test.py`

**Interfaces:**
- Consumes: `GraphRepository.store_profile_embeddings_bulk` (existing, unchanged).
- Produces:
  - `cosine_similarity(a: Optional[List[float]], b: Optional[List[float]]) -> Optional[float]`
  - `build_entity_profile_text(entity_data: Dict[str, Any]) -> str`
  - `async def embed_and_store_entity_profiles(graph_repo: GraphRepository, entities: List[Dict[str, Any]], embeddings_model: Any) -> None` — `embeddings_model` must expose `aembed_documents(texts: List[str]) -> List[List[float]]`
  - `_graded_score(..., semantic_weight: float = 0.0)` — new optional parameter, default preserves exact current behavior
  - Consumed by Task 5 (`embed_and_store_entity_profiles`, `build_entity_profile_text`) and Task 6 (`_graded_score`'s new parameter), and Task 7's eval script (`cosine_similarity`, `build_entity_profile_text`).

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/services/entity_resolution_service_test.py`, after the existing `_graded_score` tests (after line 90):

```python
def test_cosine_similarity_identical_vectors_is_one():
    assert cosine_similarity([1.0, 0.0, 0.0], [1.0, 0.0, 0.0]) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_vectors_is_zero():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_similarity_none_when_missing_or_mismatched():
    assert cosine_similarity(None, [1.0]) is None
    assert cosine_similarity([1.0], None) is None
    assert cosine_similarity([1.0, 0.0], [1.0]) is None
    assert cosine_similarity([], [1.0]) is None


def test_build_entity_profile_text_includes_all_fields():
    entity_data = {
        "canonical_name": "Temur",
        "aliases": ["Temur Barlas", "the Iron Ruler"],
        "type": "person",
        "subtype": "Sultan",
        "context_summary": "14th-century conqueror",
    }
    text = build_entity_profile_text(entity_data)
    assert "Temur" in text
    assert "Temur Barlas" in text
    assert "the Iron Ruler" in text
    assert "Sultan" in text
    assert "14th-century conqueror" in text
    assert "person" not in text  # subtype present, so type is not also included


def test_build_entity_profile_text_falls_back_to_type_without_subtype():
    entity_data = {"canonical_name": "Samarkand", "aliases": [], "type": "place"}
    text = build_entity_profile_text(entity_data)
    assert text == "Samarkand — place"


def test_build_entity_profile_text_handles_missing_optional_fields():
    entity_data = {"canonical_name": "Solo"}
    assert build_entity_profile_text(entity_data) == "Solo"


def test_graded_score_blends_semantic_similarity_when_weighted():
    entity = {
        "canonical_name": "Temur",
        "aliases": [],
        "subtype": None,
        "profile_embedding": [1.0, 0.0],
    }
    candidate = {
        "canonical_name": "the Iron Ruler",
        "aliases": [],
        "subtype": None,
        "profile_embedding": [1.0, 0.0],
    }
    entity_facts = {"neighbors": []}
    candidate_facts = {"neighbors": []}

    score_without_semantic = _graded_score(
        entity, candidate, entity_facts, candidate_facts
    )
    score_with_semantic = _graded_score(
        entity, candidate, entity_facts, candidate_facts, semantic_weight=0.5
    )

    assert score_without_semantic < 0.3  # names share few enough characters to score low
    assert score_with_semantic > score_without_semantic  # identical embeddings pull it up


def test_graded_score_unchanged_when_semantic_weight_zero_even_with_embeddings():
    entity = {
        "canonical_name": "Alpha",
        "aliases": [],
        "subtype": None,
        "profile_embedding": [1.0, 0.0],
    }
    candidate = {
        "canonical_name": "Zeta",
        "aliases": [],
        "subtype": None,
        "profile_embedding": [1.0, 0.0],
    }
    entity_facts = {"neighbors": [{"neighbor_id": "n1"}]}
    candidate_facts = {"neighbors": [{"neighbor_id": "n2"}]}
    score = _graded_score(entity, candidate, entity_facts, candidate_facts)
    assert score < 0.3  # identical to the existing test_graded_score_low_... expectation


@pytest.mark.asyncio
async def test_embed_and_store_entity_profiles_happy_path():
    graph_repo = AsyncMock()
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.return_value = [[0.1, 0.2], [0.3, 0.4]]
    entities = [
        {"id": "e1", "canonical_name": "A", "aliases": []},
        {"id": "e2", "canonical_name": "B", "aliases": []},
    ]

    await embed_and_store_entity_profiles(graph_repo, entities, embeddings_model)

    embeddings_model.aembed_documents.assert_called_once_with(["A", "B"])
    graph_repo.store_profile_embeddings_bulk.assert_called_once_with(
        [
            {"id": "e1", "embedding": [0.1, 0.2]},
            {"id": "e2", "embedding": [0.3, 0.4]},
        ]
    )


@pytest.mark.asyncio
async def test_embed_and_store_entity_profiles_noop_on_empty_list():
    graph_repo = AsyncMock()
    embeddings_model = AsyncMock()

    await embed_and_store_entity_profiles(graph_repo, [], embeddings_model)

    embeddings_model.aembed_documents.assert_not_called()
    graph_repo.store_profile_embeddings_bulk.assert_not_called()


@pytest.mark.asyncio
async def test_embed_and_store_entity_profiles_skips_store_on_count_mismatch():
    graph_repo = AsyncMock()
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.return_value = [[0.1, 0.2]]  # only 1, not 2
    entities = [
        {"id": "e1", "canonical_name": "A", "aliases": []},
        {"id": "e2", "canonical_name": "B", "aliases": []},
    ]

    await embed_and_store_entity_profiles(graph_repo, entities, embeddings_model)

    graph_repo.store_profile_embeddings_bulk.assert_not_called()
```

Update the import block at the top of the test file (lines 4-14) to add the four new names:

```python
from app.services.entity_resolution_service import (
    EntityResolutionVerdict,
    _check_hard_constraints,
    _graded_score,
    build_entity_profile_text,
    cosine_similarity,
    embed_and_store_entity_profiles,
    execute_merge,
    execute_split,
    execute_unmerge,
    normalize_alias,
    resolve_entity,
    update_alias_cache,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v -k "cosine_similarity or build_entity_profile_text or embed_and_store_entity_profiles or graded_score_blends or graded_score_unchanged"`
Expected: FAIL — `ImportError: cannot import name 'cosine_similarity'` (and similar for the other three new names)

- [ ] **Step 3: Implement**

In `packages/backend-core/app/services/entity_resolution_service.py`:

Add `import math` to the imports at the top (line 12, alongside the existing `difflib`/`json`/`logging`/`unicodedata`):

```python
import difflib
import json
import logging
import math
import unicodedata
```

Add these three functions right after `_name_similarity` (after line 79, before `_check_hard_constraints`):

```python
def cosine_similarity(
    a: Optional[List[float]], b: Optional[List[float]]
) -> Optional[float]:
    """Returns the cosine similarity of two equal-length vectors, or None if either is
    missing/empty or their lengths don't match (e.g. one predates a model change)."""
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return dot / (norm_a * norm_b)


def build_entity_profile_text(entity_data: Dict[str, Any]) -> str:
    """Builds the normalized text an entity's semantic `profile_embedding` (Item 8,
    knowledge-graph-improvement-backlog.md) is computed from: canonical name, aliases,
    subtype/type, and context summary. Used both when embedding freshly extracted
    entities (`embed_and_store_entity_profiles`, called from knowledge_graph_job) and
    when re-embedding a merge-log snapshot for offline evaluation
    (scripts/eval_entity_semantic_matching.py) — the two must build text identically
    or evaluated similarity scores won't reflect what resolution actually saw.
    """
    parts = [entity_data.get("canonical_name") or ""]
    parts.extend(entity_data.get("aliases") or [])
    if entity_data.get("subtype"):
        parts.append(entity_data["subtype"])
    elif entity_data.get("type"):
        parts.append(entity_data["type"])
    if entity_data.get("context_summary"):
        parts.append(entity_data["context_summary"])
    return " — ".join(p for p in parts if p)


async def embed_and_store_entity_profiles(
    graph_repo: GraphRepository,
    entities: List[Dict[str, Any]],
    embeddings_model: Any,
) -> None:
    """Embeds each entity's profile text (`build_entity_profile_text`) and stores it
    as `profile_embedding` on its Neo4j node — the write side of Item 8. Never raises
    on a count mismatch; logs and skips the store instead, since a partial/misaligned
    write would silently corrupt which embedding belongs to which entity.
    `embeddings_model` must expose `aembed_documents(texts: list[str]) -> list[list[float]]`
    (the `EmbeddingProvider` protocol / `GeminiEmbeddings`).
    """
    if not entities:
        return
    texts = [build_entity_profile_text(e) for e in entities]
    vectors = await embeddings_model.aembed_documents(texts)
    if len(vectors) != len(entities):
        log_json(
            logger,
            logging.WARNING,
            "entity profile embedding count mismatch — skipping store",
            expected=len(entities),
            got=len(vectors),
        )
        return
    profile_data = [
        {"id": e["id"], "embedding": vec}
        for e, vec in zip(entities, vectors)
        if vec
    ]
    if profile_data:
        await graph_repo.store_profile_embeddings_bulk(profile_data)
```

`Any` needs adding to the `typing` import (line 16): `from typing import Any, Dict, List, Literal, Optional`.

Now modify `_graded_score` (lines 113-169) to accept and use `semantic_weight`:

```python
def _graded_score(
    entity: Dict[str, Any],
    candidate: Dict[str, Any],
    entity_facts: Dict[str, Any],
    candidate_facts: Dict[str, Any],
    hard_match: bool = False,
    semantic_weight: float = 0.0,
) -> float:
    """Name/alias similarity + relationship-neighborhood overlap + weak subtype hint +
    discounted shared-parent boost, roughly normalized to 0.0-1.0.

    When `semantic_weight` > 0 and both entities carry a `profile_embedding` (Item 8),
    a semantic-similarity term is blended in, scaled down proportionally from the
    other three signals so the total stays in [0, 1]. Falls back to the original
    three-signal formula, byte-for-byte, when the weight is 0 (the default) or either
    embedding is missing.
    """
    name_score = max(
        _name_similarity(entity.get("canonical_name"), candidate.get("canonical_name")),
        max(
            (
                _name_similarity(a, b)
                for a in [entity.get("canonical_name"), *(entity.get("aliases") or [])]
                for b in [
                    candidate.get("canonical_name"),
                    *(candidate.get("aliases") or []),
                ]
            ),
            default=0.0,
        ),
    )

    e_neighbors = {
        n["neighbor_id"]
        for n in entity_facts.get("neighbors", [])
        if n.get("neighbor_id")
    }
    c_neighbors = {
        n["neighbor_id"]
        for n in candidate_facts.get("neighbors", [])
        if n.get("neighbor_id")
    }
    neighbor_score = 0.0
    if e_neighbors or c_neighbors:
        neighbor_score = len(e_neighbors & c_neighbors) / max(
            len(e_neighbors | c_neighbors), 1
        )

    subtype_score = (
        1.0
        if entity.get("subtype") and entity.get("subtype") == candidate.get("subtype")
        else 0.0
    )

    semantic_score = None
    if semantic_weight > 0.0:
        semantic_score = cosine_similarity(
            entity.get("profile_embedding"), candidate.get("profile_embedding")
        )

    if semantic_score is not None:
        lexical_weight = 1.0 - semantic_weight
        base_score = (
            lexical_weight * 0.55 * name_score
            + lexical_weight * 0.35 * neighbor_score
            + lexical_weight * 0.10 * subtype_score
            + semantic_weight * semantic_score
        )
    else:
        base_score = 0.55 * name_score + 0.35 * neighbor_score + 0.10 * subtype_score

    # Item 3: Shared parent is a supporting signal, not an auto-merge.
    # Discount shared parent if neighbor degree indicates a high-degree hub ancestor.
    if hard_match:
        max_degree = max(len(e_neighbors), len(c_neighbors))
        # High degree hub (e.g. >10 connections to prominent ancestor) receives discounted boost
        parent_boost = 0.05 if max_degree > 10 else 0.15
        base_score = min(1.0, base_score + parent_boost)

    return round(base_score, 4)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v -k "cosine_similarity or build_entity_profile_text or embed_and_store_entity_profiles or graded_score"`
Expected: PASS (all, including the two pre-existing `_graded_score` tests — confirms the default path is unchanged)

- [ ] **Step 5: Run the full service test file to confirm no regressions**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v`
Expected: PASS (all tests, including the ones untouched by this task)

- [ ] **Step 6: Commit**

```bash
git add packages/backend-core/app/services/entity_resolution_service.py \
        packages/backend-core/tests/app/services/entity_resolution_service_test.py
git commit -m "feat: add semantic embedding/scoring building blocks to entity resolution"
```

---

## Task 5: Wire embedding generation into `knowledge_graph_job`

**Files:**
- Modify: `services/worker/jobs/knowledge_graph_job.py:33-53` (imports), add a new module-level helper after `_chunk_ref` (after line 64), and call it from the bulk-write section (currently lines 383-406)
- Test: `services/worker/tests/jobs/knowledge_graph_job_test.py`

**Interfaces:**
- Consumes: `embed_and_store_entity_profiles` (Task 4); `get_embedding_provider` (existing, `app.core.providers`).
- Produces: `async def _maybe_embed_entity_profiles(graph_repo: GraphRepository, entities: list[dict], book_id: str) -> None` — tested directly and in isolation, so this task never needs to mock the LLM extraction pipeline (`extract_batch`'s `genai.Client().aio.models.generate_content` call) to reach the code under test.

- [ ] **Step 1: Write the failing tests**

Add to `services/worker/tests/jobs/knowledge_graph_job_test.py` (uses the existing `_config_get_value` helper already in this file):

```python
@pytest.mark.asyncio
async def test_maybe_embed_entity_profiles_noop_when_disabled():
    graph_repo = AsyncMock()
    entities = [{"id": "e1", "canonical_name": "A", "aliases": []}]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            new_callable=AsyncMock,
        ) as mock_get_value,
        patch(
            "services.worker.jobs.knowledge_graph_job.get_embedding_provider"
        ) as mock_get_embedding_provider,
        patch(
            "services.worker.jobs.knowledge_graph_job.embed_and_store_entity_profiles",
            new_callable=AsyncMock,
        ) as mock_embed_and_store,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_get_value.return_value = "false"

        await _maybe_embed_entity_profiles(graph_repo, entities, "book-123")

        mock_get_embedding_provider.assert_not_called()
        mock_embed_and_store.assert_not_called()


@pytest.mark.asyncio
async def test_maybe_embed_entity_profiles_embeds_when_enabled():
    graph_repo = AsyncMock()
    entities = [{"id": "e1", "canonical_name": "A", "aliases": []}]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(
                overrides={
                    "entity_semantic_matching_enabled": "true",
                    "gemini_embedding_model": "gemini-embedding-2",
                }
            ),
        ),
        patch(
            "services.worker.jobs.knowledge_graph_job.get_embedding_provider"
        ) as mock_get_embedding_provider,
        patch(
            "services.worker.jobs.knowledge_graph_job.embed_and_store_entity_profiles",
            new_callable=AsyncMock,
        ) as mock_embed_and_store,
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_embeddings_model = AsyncMock()
        mock_get_embedding_provider.return_value = mock_embeddings_model

        await _maybe_embed_entity_profiles(graph_repo, entities, "book-123")

        mock_get_embedding_provider.assert_called_once_with("gemini-embedding-2")
        mock_embed_and_store.assert_called_once_with(
            graph_repo, entities, mock_embeddings_model
        )


@pytest.mark.asyncio
async def test_maybe_embed_entity_profiles_swallows_embedding_failure():
    graph_repo = AsyncMock()
    entities = [{"id": "e1", "canonical_name": "A", "aliases": []}]

    with (
        patch("app.db.session.async_session_factory") as mock_session_factory,
        patch(
            "services.worker.jobs.knowledge_graph_job.SystemConfigsRepository.get_value",
            side_effect=_config_get_value(
                overrides={
                    "entity_semantic_matching_enabled": "true",
                    "gemini_embedding_model": "gemini-embedding-2",
                }
            ),
        ),
        patch(
            "services.worker.jobs.knowledge_graph_job.get_embedding_provider"
        ) as mock_get_embedding_provider,
        patch(
            "services.worker.jobs.knowledge_graph_job.embed_and_store_entity_profiles",
            new_callable=AsyncMock,
            side_effect=RuntimeError("embedding API down"),
        ),
    ):
        mock_session = AsyncMock()
        mock_session_factory.return_value.__aenter__.return_value = mock_session
        mock_get_embedding_provider.return_value = AsyncMock()

        # Must not raise — an embedding failure is logged and swallowed, never
        # allowed to fail the job (the graph write already succeeded by this point).
        # Reaching get_embedding_provider confirms the failure happened where
        # expected (inside embed_and_store_entity_profiles), not earlier.
        await _maybe_embed_entity_profiles(graph_repo, entities, "book-123")
        mock_get_embedding_provider.assert_called_once_with("gemini-embedding-2")


@pytest.mark.asyncio
async def test_maybe_embed_entity_profiles_noop_on_empty_entities():
    graph_repo = AsyncMock()

    with patch(
        "services.worker.jobs.knowledge_graph_job.get_embedding_provider"
    ) as mock_get_embedding_provider:
        await _maybe_embed_entity_profiles(graph_repo, [], "book-123")
        mock_get_embedding_provider.assert_not_called()
```

Update the import line at the top of the test file (line 3) to also import the new helper:

```python
from services.worker.jobs.knowledge_graph_job import (
    knowledge_graph_job,
    _maybe_embed_entity_profiles,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest services/worker/tests/jobs/knowledge_graph_job_test.py -v -k maybe_embed_entity_profiles`
Expected: FAIL — `ImportError: cannot import name '_maybe_embed_entity_profiles'`

- [ ] **Step 3: Implement**

In `services/worker/jobs/knowledge_graph_job.py`, add three imports (near the existing imports at lines 38-47):

```python
from app.core.providers import get_embedding_provider
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.graph_resolution_repository import (
    GraphResolutionQueueRepository,
)
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.services.entity_resolution_service import embed_and_store_entity_profiles
from app.services.knowledge_graph_service import (
    KnowledgeExtraction,
    parse_and_clean_json_from_exception,
    EntityType,
)
```

Add the helper right after `_chunk_ref` (after line 64, before `knowledge_graph_job`):

```python
async def _maybe_embed_entity_profiles(
    graph_repo: GraphRepository, entities: list[dict], book_id: str
) -> None:
    """Embeds and stores entity profile vectors (Item 8,
    knowledge-graph-improvement-backlog.md) when entity_semantic_matching_enabled is
    on. Never raises — an embedding failure must not fail the graph write that
    already succeeded by the time this is called; it's an optional signal for the
    resolution pass, not a requirement for extraction.
    """
    if not entities:
        return
    try:
        async with db_session.async_session_factory() as config_session:
            config_repo = SystemConfigsRepository(config_session)
            semantic_enabled = (
                await config_repo.get_value(
                    "entity_semantic_matching_enabled", "false"
                )
            ).strip().lower() == "true"
            if not semantic_enabled:
                return
            gemini_embedding_model = await config_repo.get_value(
                "gemini_embedding_model"
            )
        if not gemini_embedding_model:
            raise RuntimeError("system_config 'gemini_embedding_model' is not set")
        embeddings_model = get_embedding_provider(gemini_embedding_model)
        await embed_and_store_entity_profiles(graph_repo, entities, embeddings_model)
    except Exception as embed_exc:
        log_json(
            logger,
            logging.WARNING,
            "entity profile embedding failed — resolution will fall back to lexical matching only",
            book_id=book_id,
            error=str(embed_exc),
        )
```

Modify the bulk-write section (currently lines 383-406) to call it right after the existing "Neo4j bulk write complete" log:

```python
            # Single bulk write: 2 Neo4j round-trips for the entire book
            save_errors = 0
            try:
                if all_entities:
                    await graph_repo.upsert_entities_bulk(all_entities)
                if all_relations:
                    await graph_repo.connect_entities_bulk(all_relations)
                log_json(
                    logger,
                    logging.INFO,
                    "Neo4j bulk write complete",
                    book_id=book_id,
                    entities=len(all_entities),
                    relations=len(all_relations),
                )
                await _maybe_embed_entity_profiles(graph_repo, all_entities, book_id)
            except Exception as save_exc:
                save_errors += 1
                log_json(
                    logger,
                    logging.ERROR,
                    "failed to save entities/relations to Neo4j",
                    book_id=book_id,
                    error=str(save_exc),
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest services/worker/tests/jobs/knowledge_graph_job_test.py -v -k maybe_embed_entity_profiles`
Expected: PASS

- [ ] **Step 5: Run the full job test file to confirm no regressions**

Run: `pytest services/worker/tests/jobs/knowledge_graph_job_test.py -v`
Expected: PASS (all tests — in particular the disabled-flag/no-chunks/book-not-found tests, which return before ever reaching the new call site)

- [ ] **Step 6: Commit**

```bash
git add services/worker/jobs/knowledge_graph_job.py services/worker/tests/jobs/knowledge_graph_job_test.py
git commit -m "feat: embed entity profiles after graph write when semantic matching is enabled"
```

---

## Task 6: Wire semantic candidates + scoring into `resolve_entity`

**Files:**
- Modify: `packages/backend-core/app/services/entity_resolution_service.py:401-457` (`resolve_entity`)
- Test: `packages/backend-core/tests/app/services/entity_resolution_service_test.py`

**Interfaces:**
- Consumes: `GraphRepository.find_semantic_candidates` (Task 3), `_graded_score`'s `semantic_weight` param (Task 4).
- Produces: nothing new consumed by later tasks.

- [ ] **Step 1: Write the failing tests**

Add to `packages/backend-core/tests/app/services/entity_resolution_service_test.py`, after `test_resolve_entity_no_candidates_marks_succeeded_and_resolved` (after line 340):

```python
@pytest.mark.asyncio
async def test_resolve_entity_skips_semantic_lookup_when_disabled():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = {
        "id": "e1",
        "canonical_name": "Solo",
        "aliases": [],
        "scope": "nonfiction",
        "book_id": None,
        "profile_embedding": [1.0, 0.0],
    }
    graph_repo.find_resolution_candidates.return_value = []
    graph_repo.get_entity_facts.return_value = {
        "child_of": [],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ),
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        config_repo = AsyncMock()
        config_repo.get_value.side_effect = lambda key, default=None: {
            "resolution_similarity_threshold": "2",
            "entity_semantic_matching_enabled": "false",
        }.get(key, default)
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        graph_repo.find_semantic_candidates.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_entity_merges_semantic_candidates_when_enabled():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "Temur",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
            "profile_embedding": [1.0, 0.0],
        },
        "sem-cand-1": {
            "id": "sem-cand-1",
            "canonical_name": "the Iron Ruler",
            "aliases": [],
            "profile_embedding": [1.0, 0.0],
        },
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = []
    graph_repo.find_semantic_candidates.return_value = [
        {"id": "sem-cand-1", "canonical_name": "the Iron Ruler"}
    ]
    graph_repo.get_entity_facts.return_value = {
        "child_of": [],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }

    with (
        patch(
            "app.services.entity_resolution_service.GraphResolutionQueueRepository"
        ) as MockQueueRepo,
        patch(
            "app.services.entity_resolution_service.GraphResolutionReviewsRepository"
        ) as MockReviewsRepo,
        patch(
            "app.services.entity_resolution_service.SystemConfigsRepository"
        ) as MockConfigRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
        patch(
            "app.services.entity_resolution_service._gray_zone_judge",
            new=AsyncMock(
                return_value=EntityResolutionVerdict(
                    verdict="unsure", confidence=0.5, reasoning="test"
                )
            ),
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.side_effect = lambda key, default=None: {
            "resolution_similarity_threshold": "2",
            "entity_semantic_matching_enabled": "true",
            "entity_semantic_weight": "0.5",
            "entity_semantic_candidate_limit": "5",
        }.get(key, default)
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        graph_repo.find_semantic_candidates.assert_called_once_with(
            entity_id="e1",
            embedding=[1.0, 0.0],
            scope="nonfiction",
            book_id=None,
            limit=5,
        )
        # The semantic-only candidate reached the per-candidate loop (fetched via
        # get_entity_by_id, same as any other candidate).
        graph_repo.get_entity_by_id.assert_any_call("sem-cand-1")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v -k "resolve_entity_skips_semantic or resolve_entity_merges_semantic"`
Expected: FAIL — `graph_repo.find_semantic_candidates.assert_not_called()` / `assert_called_once_with(...)` fail because `resolve_entity` never calls it yet.

- [ ] **Step 3: Implement**

In `packages/backend-core/app/services/entity_resolution_service.py`, modify `resolve_entity` (currently lines 419-457):

```python
    scope = entity.get("scope")
    book_id = entity.get("book_id")
    similarity_threshold = int(
        await config_repo.get_value("resolution_similarity_threshold", "2")
    )
    semantic_matching_enabled = (
        await config_repo.get_value("entity_semantic_matching_enabled", "false")
    ).strip().lower() == "true"
    semantic_weight = (
        float(await config_repo.get_value("entity_semantic_weight", "0.15"))
        if semantic_matching_enabled
        else 0.0
    )

    await graph_repo.set_resolution_status(entity_id, "resolving")

    candidates = await graph_repo.find_resolution_candidates(
        entity_id=entity_id,
        canonical_name=entity.get("canonical_name"),
        aliases=entity.get("aliases"),
        scope=scope,
        book_id=book_id,
        edit_distance=similarity_threshold,
    )

    if semantic_matching_enabled and entity.get("profile_embedding"):
        candidate_limit = int(
            await config_repo.get_value("entity_semantic_candidate_limit", "5")
        )
        semantic_candidates = await graph_repo.find_semantic_candidates(
            entity_id=entity_id,
            embedding=entity["profile_embedding"],
            scope=scope,
            book_id=book_id,
            limit=candidate_limit,
        )
        seen_ids = {c["id"] for c in candidates}
        candidates = candidates + [
            c for c in semantic_candidates if c["id"] not in seen_ids
        ]

    entity_facts = await graph_repo.get_entity_facts(entity_id)
    review_created = False

    for candidate in candidates:
```

And modify the `_graded_score` call site (currently lines 451-457):

```python
        score = _graded_score(
            entity,
            candidate,
            entity_facts,
            candidate_facts,
            hard_match=(hard == "match"),
            semantic_weight=semantic_weight,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v -k "resolve_entity_skips_semantic or resolve_entity_merges_semantic"`
Expected: PASS

- [ ] **Step 5: Run the full service test file to confirm no regressions**

Run: `pytest packages/backend-core/tests/app/services/entity_resolution_service_test.py -v`
Expected: PASS — all tests, including every pre-existing `resolve_entity` test (they don't set `entity_semantic_matching_enabled`, so `config_repo.get_value` returns their stubbed `"5"` default for unknown keys... verify each pre-existing test's `config_repo.get_value.return_value = "5"` stub against the new call — see Step 6 note)

- [ ] **Step 6: Fix any pre-existing test breakage from the blanket `"5"` stub**

Several pre-existing tests stub `config_repo.get_value.return_value = "5"` unconditionally (not `side_effect`), meaning `entity_semantic_matching_enabled` would also resolve to `"5"` — and `"5".strip().lower() == "true"` is `False`, so `semantic_matching_enabled` correctly evaluates to `False` and no behavior changes. Run Step 5 first; if any test unexpectedly fails, it means that test's flow reaches the `float(await config_repo.get_value("entity_semantic_weight", ...))` line while `semantic_matching_enabled` is `True` — trace which stub causes that and fix it to use the `side_effect` dict pattern shown in Step 1's tests instead of a blanket `return_value`.

- [ ] **Step 7: Commit**

```bash
git add packages/backend-core/app/services/entity_resolution_service.py \
        packages/backend-core/tests/app/services/entity_resolution_service_test.py
git commit -m "feat: merge semantic candidates and blend semantic score into resolve_entity"
```

---

## Task 7: Offline eval script against real merge/review history

**Files:**
- Create: `scripts/eval_entity_semantic_matching.py`

**Interfaces:**
- Consumes: `cosine_similarity`, `build_entity_profile_text` (Task 4); `GraphMergeLog`, `GraphResolutionReview` ORM models (existing); `GraphRepository.get_entity_by_id` (existing); `get_embedding_provider` (existing).
- Produces: a printed report — no code consumers (this is a standalone operational script, matching the existing `scripts/backfill_quran_embeddings.py` convention: no pytest suite, verified by running it).

This script answers the "how do we test it" question from before turning `entity_semantic_matching_enabled` on for real: it replays semantic similarity against merges/reviews that already happened and reports how often it would have agreed with the human/system outcome, **before** trusting it to drive new decisions. It requires entities to already have `profile_embedding` populated (Task 5 must have run against at least some books with the flag on) — it reports a skip count for anything it can't score, rather than failing.

- [ ] **Step 1: Write the script**

```python
"""
Offline evaluation: replays semantic-similarity scoring against real historical
entity-resolution decisions already logged in Postgres, to validate the approach
(knowledge-graph-improvement-backlog.md Item 8) before enabling
`entity_semantic_matching_enabled` for live merges.

Two label sources:
  - graph_merge_log: every merge that has happened. reverted_at IS NULL is treated
    as "same" (presumed-correct, though this is an imperfect proxy — absence of a
    revert isn't strong positive proof, just the best signal available).
    reverted_at IS NOT NULL means a human later undid it — labeled "different".
    The removed entity no longer exists in Neo4j, so its snapshot text is embedded
    live for this comparison.
  - graph_resolution_reviews: only status='rejected' rows are used, labeled
    "different" — both entities are guaranteed to still exist (rejecting a review
    means "leave separate", nothing gets deleted), so no re-embedding is needed.

Requires entities to already have `profile_embedding` populated (run
knowledge_graph_job with entity_semantic_matching_enabled=true on at least a sample
of books first) — anything without one is skipped and counted, not failed.
"""

import os
import sys
import asyncio
import argparse
import statistics

sys.path.insert(
    0,
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../packages/backend-core")
    ),
)

from sqlalchemy import select

from app.db import session as db_session
from app.db.models import GraphMergeLog, GraphResolutionReview
from app.db.repositories.graph_repository import GraphRepository
from app.db.repositories.system_configs_repository import SystemConfigsRepository
from app.core.providers import get_embedding_provider
from app.services.entity_resolution_service import (
    build_entity_profile_text,
    cosine_similarity,
)

STRONG_MERGE_SCORE = 0.75  # mirrors entity_resolution_service.STRONG_MERGE_SCORE


def _summarize(labeled_scores):
    """labeled_scores: list of (label, score_or_None) tuples, label in {'same','different'}.
    Pure function — no I/O — so it's testable without mocking the DB/embedder."""
    by_label = {"same": [], "different": []}
    skipped = 0
    for label, score in labeled_scores:
        if score is None:
            skipped += 1
            continue
        by_label[label].append(score)

    report = {"skipped": skipped}
    for label, scores in by_label.items():
        if not scores:
            report[label] = {"count": 0}
            continue
        report[label] = {
            "count": len(scores),
            "mean": round(statistics.mean(scores), 4),
            "median": round(statistics.median(scores), 4),
        }
    # The number that matters most: "different"-labeled pairs the semantic score
    # would have flagged as a strong merge — these would have been wrong auto-merges.
    would_wrongly_merge = sum(
        1 for s in by_label["different"] if s >= STRONG_MERGE_SCORE
    )
    report["different_would_wrongly_merge"] = would_wrongly_merge
    return report


async def main(limit: int = 500):
    print("Initializing database connection...", flush=True)
    await db_session.init_db()

    async with db_session.async_session_factory() as session:
        configs_repo = SystemConfigsRepository(session)
        embedding_model_name = await configs_repo.get_value("gemini_embedding_model")
        if not embedding_model_name:
            print("ERROR: system_config 'gemini_embedding_model' is not set.")
            return
        merge_rows = (
            (
                await session.execute(
                    select(GraphMergeLog).order_by(GraphMergeLog.performed_at.desc()).limit(limit)
                )
            )
            .scalars()
            .all()
        )
        rejected_review_rows = (
            (
                await session.execute(
                    select(GraphResolutionReview)
                    .where(GraphResolutionReview.status == "rejected")
                    .order_by(GraphResolutionReview.reviewed_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    print(
        f"Loaded {len(merge_rows)} merge_log rows and {len(rejected_review_rows)} "
        "rejected review rows.",
        flush=True,
    )

    embeddings_model = get_embedding_provider(embedding_model_name)
    graph_repo = GraphRepository()
    labeled_scores = []

    try:
        # graph_merge_log: kept entity's embedding already lives on its Neo4j node;
        # removed entity's snapshot text must be re-embedded (it's deleted from Neo4j).
        snapshot_texts = [
            build_entity_profile_text(row.removed_entity_snapshot) for row in merge_rows
        ]
        snapshot_vectors = (
            await embeddings_model.aembed_documents(snapshot_texts)
            if snapshot_texts
            else []
        )

        for row, removed_vector in zip(merge_rows, snapshot_vectors):
            kept = await graph_repo.get_entity_by_id(str(row.kept_entity_id))
            kept_vector = kept.get("profile_embedding") if kept else None
            score = cosine_similarity(kept_vector, removed_vector)
            label = "different" if row.reverted_at is not None else "same"
            labeled_scores.append((label, score))

        # graph_resolution_reviews (rejected only): both entities still exist.
        for row in rejected_review_rows:
            entity_a = await graph_repo.get_entity_by_id(str(row.entity_a_id))
            entity_b = await graph_repo.get_entity_by_id(str(row.entity_b_id))
            score = cosine_similarity(
                entity_a.get("profile_embedding") if entity_a else None,
                entity_b.get("profile_embedding") if entity_b else None,
            )
            labeled_scores.append(("different", score))
    finally:
        await graph_repo.close()

    report = _summarize(labeled_scores)
    print("\n--- Semantic Matching Eval Report ---")
    print(f"Skipped (no embedding available yet): {report['skipped']}")
    print(f"'same'  (unreverted merges):    {report['same']}")
    print(f"'different' (reverted merges + rejected reviews): {report['different']}")
    print(
        "'different' pairs that would have scored >= "
        f"{STRONG_MERGE_SCORE} (would-be wrong auto-merges): "
        f"{report['different_would_wrongly_merge']}"
    )
    if report["skipped"] > 0:
        print(
            "\nNote: a high skip count usually means profile_embedding hasn't been "
            "backfilled for most of the graph yet — run knowledge_graph_job with "
            "entity_semantic_matching_enabled=true on a sample of books first."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--limit",
        type=int,
        default=500,
        help="Max rows to pull from each of graph_merge_log / graph_resolution_reviews.",
    )
    args = parser.parse_args()
    asyncio.run(main(limit=args.limit))
```

- [ ] **Step 2: Verify `_summarize` by hand (no DB/embedder needed)**

Run this inline sanity check to confirm the pure summarizer behaves correctly before touching real data:

```bash
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from eval_entity_semantic_matching import _summarize

report = _summarize([
    ('same', 0.9),
    ('same', 0.85),
    ('different', 0.2),
    ('different', 0.8),   # would wrongly merge
    ('different', None),  # skipped
])
assert report['skipped'] == 1
assert report['same']['count'] == 2
assert report['different']['count'] == 2
assert report['different_would_wrongly_merge'] == 1
print('OK:', report)
"
```
Expected: `OK: {'skipped': 1, 'same': {...}, 'different': {...}, 'different_would_wrongly_merge': 1}`

- [ ] **Step 3: Run it against the local dev DB**

Requires Task 5 to have already run (with `entity_semantic_matching_enabled` temporarily set to `true`) against at least a few books so some entities have `profile_embedding` set — otherwise expect a large skip count, which the script explains in its own output.

```bash
docker exec -it $(docker compose ps -q worker) \
    python scripts/eval_entity_semantic_matching.py --limit 200
```
Expected: the report prints without raising; review `different_would_wrongly_merge` and the skip count before deciding whether to flip `entity_semantic_matching_enabled` to `true` for live resolution.

- [ ] **Step 4: Do NOT commit**

`/scripts/` is blanket-`.gitignore`'d repo-wide (added after a past credentials-leak cleanup) — confirmed every existing file under `scripts/`, including `backfill_quran_embeddings.py` cited as this task's style precedent, is untracked (`git ls-files scripts/` returns nothing for any of them). This script stays untracked too, exactly like its siblings — the deliverable is the file on disk, not a commit. Do not `git add -f` past the ignore rule.

---

## Rollout note (not a task — read before flipping the flag)

After all 7 tasks land, `entity_semantic_matching_enabled` is still `"false"` (Task 1's seed default) — nothing changes for live resolution yet. To actually turn it on:

1. Reprocess (or wait for newly ingested) books so their entities get `profile_embedding` populated (Task 5's code path only runs when the flag is already `true` — flip it to `true` in `system_configs` first, just to start collecting embeddings, before trusting it for scoring).
2. Run `scripts/eval_entity_semantic_matching.py` (Task 7) and check `different_would_wrongly_merge` is 0 or acceptably low.
3. Only then consider raising `entity_semantic_weight` above its conservative `0.15` default, and only after checking the eval report again at the new weight.

**Known gap in step 2, found by the final whole-branch review — read before relying on the eval script's output:** "reprocessing a sample of books" does NOT make the eval script's `graph_merge_log`/`graph_resolution_reviews` replay meaningful on its own. `knowledge_graph_job` calls `delete_book_graph` and re-mints every entity with a fresh `uuid4()` on reprocess, so historical merge-log/review rows reference entity ids that either no longer exist or were never re-embedded — the eval script will report ~100% skipped regardless of how many books are reprocessed, which looks identical to "not backfilled yet" but isn't fixed by more reprocessing. Closing this gap needs a separate small backfill routine that embeds *existing, currently-live* Entity nodes in place (no delete/re-mint) — out of scope for this plan's 7 tasks; treat as a prerequisite follow-up before trusting step 2's output, not as something reprocessing already gives you. Until that backfill exists, step 2 can only validate decisions made *after* the flag went live, not historical ones — a weaker (but not worthless) form of the intended pre-validation.
