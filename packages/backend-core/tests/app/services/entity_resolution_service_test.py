import unicodedata

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.entity_resolution_service import (
    EntityResolutionVerdict,
    _check_hard_constraints,
    _embed_texts_batched,
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


def test_normalize_alias_trims_and_lowercases():
    assert normalize_alias("  Ismail  ") == "ismail"


def test_check_hard_constraints_conflict_on_disjoint_parents():
    entity_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [{"parent_id": "p2"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "conflict"


def test_check_hard_constraints_match_on_shared_parent():
    entity_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [{"parent_id": "p1"}],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "match"


def test_check_hard_constraints_none_when_sparse():
    entity_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    candidate_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    assert _check_hard_constraints(entity_facts, candidate_facts) == "none"


def test_check_hard_constraints_falls_back_to_born_in():
    entity_facts = {
        "child_of": [],
        "born_in": [{"location_id": "l1"}],
        "died_in": [],
        "neighbors": [],
    }
    candidate_facts = {
        "child_of": [],
        "born_in": [{"location_id": "l2"}],
        "died_in": [],
        "neighbors": [],
    }
    assert _check_hard_constraints(entity_facts, candidate_facts) == "conflict"


def test_graded_score_high_for_identical_name_and_overlapping_neighbors():
    entity = {"canonical_name": "Same Name", "aliases": [], "subtype": "Sultan"}
    candidate = {"canonical_name": "Same Name", "aliases": [], "subtype": "Sultan"}
    entity_facts = {"neighbors": [{"neighbor_id": "n1"}, {"neighbor_id": "n2"}]}
    candidate_facts = {"neighbors": [{"neighbor_id": "n1"}, {"neighbor_id": "n2"}]}
    score = _graded_score(entity, candidate, entity_facts, candidate_facts)
    assert score > 0.9


def test_graded_score_low_for_different_name_and_no_overlap():
    entity = {"canonical_name": "Alpha", "aliases": [], "subtype": None}
    candidate = {"canonical_name": "Zeta", "aliases": [], "subtype": None}
    entity_facts = {"neighbors": [{"neighbor_id": "n1"}]}
    candidate_facts = {"neighbors": [{"neighbor_id": "n2"}]}
    score = _graded_score(entity, candidate, entity_facts, candidate_facts)
    assert score < 0.3


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


def test_build_entity_profile_text_nfc_normalizes_final_text():
    # "Ü" as a single precomposed codepoint (NFC) vs. "U" + combining diaeresis
    # (NFD) look visually identical but are different strings/embeddings unless
    # normalized. Assemble the profile text so only the *joined* string is
    # decomposed (each individual field is already NFC on its own) — this proves
    # normalization is applied to the final assembled text, not just per-field.
    entity_data = {
        "canonical_name": "Uyghur",
        "aliases": ["Ui" + "̈" + "ghur"],  # "Uïghur" in NFD form
    }
    text = build_entity_profile_text(entity_data)
    assert text == unicodedata.normalize("NFC", text)
    assert "̈" not in text  # combining diaeresis was folded into a precomposed char


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

    assert score_without_semantic < 0.3  # names look nothing alike
    assert (
        score_with_semantic > score_without_semantic
    )  # identical embeddings pull it up


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
    assert (
        score < 0.3
    )  # identical to the existing test_graded_score_low_... expectation


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


@pytest.mark.asyncio
async def test_embed_texts_batched_chunks_by_explicit_batch_size():
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.side_effect = [
        [[0.0], [0.1]],
        [[0.2], [0.3]],
        [[0.4]],
    ]

    vectors = await _embed_texts_batched(
        embeddings_model, ["a", "b", "c", "d", "e"], batch_size=2
    )

    assert vectors == [[0.0], [0.1], [0.2], [0.3], [0.4]]
    assert embeddings_model.aembed_documents.call_count == 3
    embeddings_model.aembed_documents.assert_any_call(["a", "b"])
    embeddings_model.aembed_documents.assert_any_call(["c", "d"])
    embeddings_model.aembed_documents.assert_any_call(["e"])


@pytest.mark.asyncio
async def test_embed_texts_batched_defaults_to_settings_embed_batch_size():
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.return_value = [[0.0]]

    with patch("app.services.entity_resolution_service.settings") as mock_settings:
        mock_settings.embed_batch_size = 50
        await _embed_texts_batched(embeddings_model, ["a"])

    # No explicit batch_size passed -> falls back to settings.embed_batch_size,
    # matching services/worker/jobs/embedding_job.py's existing batching convention
    # (rather than inventing a separate magic number for entity profile embeddings).
    embeddings_model.aembed_documents.assert_called_once_with(["a"])


@pytest.mark.asyncio
async def test_embed_texts_batched_partial_batch_mismatch_does_not_misalign_later_batches():
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.side_effect = [
        [[0.0]],  # first batch of 2 short-responds with only 1 vector
        [[0.2], [0.3]],  # second batch responds correctly
    ]

    vectors = await _embed_texts_batched(
        embeddings_model, ["a", "b", "c", "d"], batch_size=2
    )

    # The mismatched first batch is represented as None for each of its items
    # (never the short response), so "c"/"d"'s vectors stay correctly paired with
    # their own positions instead of shifting up to fill the gap.
    assert vectors == [None, None, [0.2], [0.3]]


@pytest.mark.asyncio
async def test_embed_and_store_entity_profiles_batches_large_entity_lists():
    graph_repo = AsyncMock()
    embeddings_model = AsyncMock()
    embeddings_model.aembed_documents.side_effect = [
        [[0.0], [0.1]],
        [[0.2]],
    ]
    entities = [
        {"id": "e1", "canonical_name": "A", "aliases": []},
        {"id": "e2", "canonical_name": "B", "aliases": []},
        {"id": "e3", "canonical_name": "C", "aliases": []},
    ]

    with patch("app.services.entity_resolution_service.settings") as mock_settings:
        mock_settings.embed_batch_size = 2
        await embed_and_store_entity_profiles(graph_repo, entities, embeddings_model)

    assert embeddings_model.aembed_documents.call_count == 2
    graph_repo.store_profile_embeddings_bulk.assert_called_once_with(
        [
            {"id": "e1", "embedding": [0.0]},
            {"id": "e2", "embedding": [0.1]},
            {"id": "e3", "embedding": [0.2]},
        ]
    )


@pytest.mark.asyncio
async def test_update_alias_cache_unions_existing_ids():
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = {
        "canonical_name": "Name",
        "aliases": ["Alt"],
    }
    with patch("app.services.entity_resolution_service.cache_service") as mock_cache:
        mock_cache.get = AsyncMock(return_value=["other-id"])
        mock_cache.set = AsyncMock()

        await update_alias_cache(graph_repo, "e1")

        assert mock_cache.set.call_count == 2  # "Name" and "Alt"
        for call in mock_cache.set.call_args_list:
            ids = call[0][1]
            assert set(ids) == {"other-id", "e1"}


@pytest.mark.asyncio
async def test_update_alias_cache_noop_when_entity_missing():
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = None
    with patch("app.services.entity_resolution_service.cache_service") as mock_cache:
        await update_alias_cache(graph_repo, "missing")
        mock_cache.set.assert_not_called()


@pytest.mark.asyncio
async def test_execute_merge_noop_when_entity_missing():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = [{"id": "keep-1"}, None]

    result = await execute_merge(
        session, graph_repo, "keep-1", "remove-1", "admin@example.com"
    )
    assert result is None
    graph_repo.merge_entities_by_id.assert_not_called()


@pytest.mark.asyncio
async def test_execute_merge_happy_path_logs_before_delete_and_requeues_children():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = [
        {"id": "keep-1", "canonical_name": "Keep", "aliases": []},
        {"id": "remove-1", "canonical_name": "Remove", "aliases": ["RemoveAlt"]},
    ]
    graph_repo.get_entity_edges_snapshot.return_value = [{"id": "edge-1"}]
    graph_repo.get_children_via_child_of.side_effect = [
        ["child-of-remove"],
        ["child-of-keep"],
    ]

    with (
        patch(
            "app.services.entity_resolution_service.GraphMergeLogRepository"
        ) as MockMergeLogRepo,
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
        ) as mock_update_cache,
    ):
        merge_log_repo = AsyncMock()
        merge_log_entry = MagicMock(id=42)
        merge_log_repo.log_merge.return_value = merge_log_entry
        MockMergeLogRepo.return_value = merge_log_repo

        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo

        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo

        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        result = await execute_merge(
            session, graph_repo, "keep-1", "remove-1", "admin@example.com"
        )

        assert result == 42
        # Snapshot logged BEFORE the Neo4j merge/delete call
        assert merge_log_repo.log_merge.call_args[1]["removed_entity_id"] == "remove-1"
        assert merge_log_repo.log_merge.call_args[1]["removed_edges_snapshot"] == [
            {"id": "edge-1"}
        ]
        graph_repo.merge_entities_by_id.assert_called_once()
        combined_aliases = graph_repo.merge_entities_by_id.call_args[0][2]
        assert set(combined_aliases) == {"Remove", "RemoveAlt"}

        queue_repo.delete_by_entity_id.assert_called_once_with("remove-1")
        reviews_repo.resolve_reviews_for_merge.assert_called_once_with(
            keep_id="keep-1", remove_id="remove-1", reviewed_by="admin@example.com"
        )
        requeued_ids = {c[0][0] for c in queue_repo.requeue_or_cap.call_args_list}
        assert requeued_ids == {"child-of-remove", "child-of-keep"}
        mock_update_cache.assert_called_once_with(graph_repo, "keep-1")


@pytest.mark.asyncio
async def test_execute_split_updates_alias_cache_for_both_nodes():
    graph_repo = AsyncMock()
    graph_repo.split_entities.return_value = {
        "new_entity_id": "new-1",
        "moved_edge_ids": ["edge-1"],
        "unclustered_edge_ids": [],
    }
    with patch(
        "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
    ) as mock_update_cache:
        result = await execute_split(graph_repo, "orig-1", "split-edge")
        assert result["new_entity_id"] == "new-1"
        assert mock_update_cache.call_count == 2


@pytest.mark.asyncio
async def test_execute_unmerge_restores_and_marks_reverted():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.restore_entity_from_snapshot.return_value = []

    with (
        patch(
            "app.services.entity_resolution_service.GraphMergeLogRepository"
        ) as MockMergeLogRepo,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        merge_log_repo = AsyncMock()
        entry = MagicMock(
            reverted_at=None,
            kept_entity_id="keep-1",
            removed_entity_id="remove-1",
            removed_entity_snapshot={"id": "remove-1"},
            removed_edges_snapshot=[],
        )
        merge_log_repo.get.return_value = entry
        MockMergeLogRepo.return_value = merge_log_repo

        result = await execute_unmerge(session, graph_repo, 42)

        assert result["restored_entity_id"] == "remove-1"
        merge_log_repo.mark_reverted.assert_called_once_with(42)


@pytest.mark.asyncio
async def test_execute_unmerge_raises_on_missing_entry():
    session = AsyncMock()
    graph_repo = AsyncMock()
    with patch(
        "app.services.entity_resolution_service.GraphMergeLogRepository"
    ) as MockMergeLogRepo:
        merge_log_repo = AsyncMock()
        merge_log_repo.get.return_value = None
        MockMergeLogRepo.return_value = merge_log_repo

        with pytest.raises(ValueError):
            await execute_unmerge(session, graph_repo, 999)


@pytest.mark.asyncio
async def test_execute_unmerge_raises_if_already_reverted():
    session = AsyncMock()
    graph_repo = AsyncMock()
    with patch(
        "app.services.entity_resolution_service.GraphMergeLogRepository"
    ) as MockMergeLogRepo:
        merge_log_repo = AsyncMock()
        merge_log_repo.get.return_value = MagicMock(reverted_at="2026-01-01T00:00:00Z")
        MockMergeLogRepo.return_value = merge_log_repo

        with pytest.raises(ValueError):
            await execute_unmerge(session, graph_repo, 1)


@pytest.mark.asyncio
async def test_resolve_entity_missing_marks_failed():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = None

    with patch(
        "app.services.entity_resolution_service.GraphResolutionQueueRepository"
    ) as MockQueueRepo:
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo

        await resolve_entity(session, graph_repo, "missing-id")

        queue_repo.mark_status.assert_called_once_with("missing-id", "failed")


@pytest.mark.asyncio
async def test_resolve_entity_no_candidates_marks_succeeded_and_resolved():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.return_value = {
        "id": "e1",
        "canonical_name": "Solo",
        "aliases": [],
        "scope": "nonfiction",
        "book_id": None,
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
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        graph_repo.set_resolution_status.assert_any_call("e1", "resolving")
        graph_repo.set_resolution_status.assert_any_call("e1", "resolved")
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


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


def _resolve_entity_common_mocks(graph_repo, config_overrides):
    """Shared per-test patch context for the config-parsing/clamping tests below —
    a single lexical candidate reaches _graded_score, which is patched so the test
    can assert on the exact semantic_weight it was called with."""
    graph_repo.get_entity_by_id.return_value = {
        "id": "e1",
        "canonical_name": "Temur",
        "aliases": [],
        "scope": "nonfiction",
        "book_id": None,
        "profile_embedding": [1.0, 0.0],
    }
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "Temur"}
    ]
    graph_repo.find_semantic_candidates.return_value = []
    graph_repo.get_entity_facts.return_value = {
        "child_of": [],
        "born_in": [],
        "died_in": [],
        "neighbors": [],
    }
    config_repo = AsyncMock()
    config_repo.get_value.side_effect = lambda key, default=None: {
        "resolution_similarity_threshold": "2",
        **config_overrides,
    }.get(key, default)
    return config_repo


@pytest.mark.asyncio
async def test_resolve_entity_clamps_semantic_weight_above_one():
    session = AsyncMock()
    graph_repo = AsyncMock()
    config_repo = _resolve_entity_common_mocks(
        graph_repo,
        {
            "entity_semantic_matching_enabled": "true",
            # A misconfigured admin typing "15" meaning "15%" — unclamped this drives
            # lexical_weight negative in _graded_score, which can push the blended
            # score above 1.0 and clear STRONG_MERGE_SCORE for nearly every candidate.
            "entity_semantic_weight": "15",
            "entity_semantic_candidate_limit": "5",
        },
    )

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
        patch(
            "app.services.entity_resolution_service._graded_score", return_value=0.1
        ) as mock_graded_score,
    ):
        MockQueueRepo.return_value = AsyncMock()
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        assert mock_graded_score.call_args.kwargs["semantic_weight"] == 1.0


@pytest.mark.asyncio
async def test_resolve_entity_falls_back_to_default_semantic_weight_on_malformed_config():
    session = AsyncMock()
    graph_repo = AsyncMock()
    config_repo = _resolve_entity_common_mocks(
        graph_repo,
        {
            "entity_semantic_matching_enabled": "true",
            "entity_semantic_weight": "not-a-number",
            "entity_semantic_candidate_limit": "5",
        },
    )

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
        patch(
            "app.services.entity_resolution_service._graded_score", return_value=0.1
        ) as mock_graded_score,
    ):
        MockQueueRepo.return_value = AsyncMock()
        MockConfigRepo.return_value = config_repo

        # Must not raise — a malformed config value degrades to the documented
        # 0.15 default instead of letting float(...) blow up the whole entity's
        # resolution.
        await resolve_entity(session, graph_repo, "e1")

        assert mock_graded_score.call_args.kwargs["semantic_weight"] == 0.15


@pytest.mark.asyncio
async def test_resolve_entity_falls_back_to_default_semantic_weight_on_nan_config():
    session = AsyncMock()
    graph_repo = AsyncMock()
    config_repo = _resolve_entity_common_mocks(
        graph_repo,
        {
            "entity_semantic_matching_enabled": "true",
            # float("nan") does not raise ValueError, so it needs its own guard
            # distinct from the "not a valid float" malformed-input case — an
            # un-clamped NaN would otherwise flow into _graded_score's arithmetic.
            "entity_semantic_weight": "nan",
            "entity_semantic_candidate_limit": "5",
        },
    )

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
        patch(
            "app.services.entity_resolution_service._graded_score", return_value=0.1
        ) as mock_graded_score,
    ):
        MockQueueRepo.return_value = AsyncMock()
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        assert mock_graded_score.call_args.kwargs["semantic_weight"] == 0.15


@pytest.mark.asyncio
async def test_resolve_entity_falls_back_to_default_candidate_limit_on_malformed_config():
    session = AsyncMock()
    graph_repo = AsyncMock()
    config_repo = _resolve_entity_common_mocks(
        graph_repo,
        {
            "entity_semantic_matching_enabled": "true",
            "entity_semantic_weight": "0.15",
            "entity_semantic_candidate_limit": "not-an-int",
        },
    )

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
        patch("app.services.entity_resolution_service._graded_score", return_value=0.1),
    ):
        MockQueueRepo.return_value = AsyncMock()
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        graph_repo.find_semantic_candidates.assert_called_once_with(
            entity_id="e1",
            embedding=[1.0, 0.0],
            scope="nonfiction",
            book_id=None,
            limit=5,
        )


@pytest.mark.asyncio
async def test_resolve_entity_degrades_to_lexical_only_when_semantic_lookup_raises():
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
        "lex-cand-1": {
            "id": "lex-cand-1",
            "canonical_name": "Zeta",  # deliberately dissimilar -> low score -> "leave"
            "aliases": [],
        },
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "lex-cand-1", "canonical_name": "Zeta"}
    ]
    graph_repo.find_semantic_candidates.side_effect = RuntimeError(
        "vector index unavailable"
    )
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
            "entity_semantic_matching_enabled": "true",
            "entity_semantic_weight": "0.15",
            "entity_semantic_candidate_limit": "5",
        }.get(key, default)
        MockConfigRepo.return_value = config_repo

        # Must not raise even though find_semantic_candidates blew up — resolution
        # degrades to lexical-only candidates and still runs to completion, rather
        # than leaving set_resolution_status(..., "resolving") stuck forever (every
        # other candidate query in this file excludes 'resolving' nodes, so a stuck
        # status would permanently poison the candidate pool for everyone else).
        await resolve_entity(session, graph_repo, "e1")

        graph_repo.find_semantic_candidates.assert_called_once()
        # The lexical candidate from find_resolution_candidates still reached the
        # per-candidate loop despite the semantic lookup failure.
        graph_repo.get_entity_by_id.assert_any_call("lex-cand-1")
        graph_repo.set_resolution_status.assert_any_call("e1", "resolved")
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_hard_conflict_skips_candidate_and_succeeds():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "A-lookalike", "aliases": []},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "A-lookalike"}
    ]
    graph_repo.get_entity_facts.side_effect = lambda eid: {
        "e1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
        "cand-1": {
            "child_of": [{"parent_id": "p2"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
    }.get(eid, {"child_of": [], "born_in": [], "died_in": [], "neighbors": []})

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
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_not_called()
        reviews_repo.create_review.assert_not_called()
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_hard_match_executes_merge():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "subtype": "Person",
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "A", "subtype": "Person"},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "A", "subtype": "Person"}
    ]
    graph_repo.get_entity_facts.side_effect = lambda eid: {
        "e1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
        "cand-1": {
            "child_of": [{"parent_id": "p1"}],
            "born_in": [],
            "died_in": [],
            "neighbors": [],
        },
    }.get(eid, {"child_of": [], "born_in": [], "died_in": [], "neighbors": []})

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
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_called_once_with(
            session,
            graph_repo,
            keep_id="e1",
            remove_id="cand-1",
            performed_by="system:resolution_job",
        )
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_resolve_entity_gray_zone_unsure_creates_review_and_marks_needs_review():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "Somewhat Similar A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {
            "id": "cand-1",
            "canonical_name": "Somewhat Similar B",
            "aliases": [],
        },
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "Somewhat Similar B"}
    ]
    sparse_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    graph_repo.get_entity_facts.return_value = sparse_facts

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
        patch("app.services.entity_resolution_service._graded_score", return_value=0.5),
        patch(
            "app.services.entity_resolution_service._gray_zone_judge",
            new=AsyncMock(
                return_value=EntityResolutionVerdict(
                    verdict="unsure", confidence=0.4, reasoning="not sure"
                )
            ),
        ) as mock_judge,
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_judge.assert_called_once()
        mock_execute_merge.assert_not_called()
        reviews_repo.create_review.assert_called_once()
        assert reviews_repo.create_review.call_args[0][0] == "e1"
        assert reviews_repo.create_review.call_args[0][1] == "cand-1"
        assert reviews_repo.create_review.call_args[0][4] == "unsure"
        queue_repo.mark_status.assert_called_once_with("e1", "needs_review")


@pytest.mark.asyncio
async def test_resolve_entity_gray_zone_confident_same_merges():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = lambda eid: {
        "e1": {
            "id": "e1",
            "canonical_name": "A",
            "aliases": [],
            "scope": "nonfiction",
            "book_id": None,
        },
        "cand-1": {"id": "cand-1", "canonical_name": "B"},
    }.get(eid)
    graph_repo.find_resolution_candidates.return_value = [
        {"id": "cand-1", "canonical_name": "B"}
    ]
    sparse_facts = {"child_of": [], "born_in": [], "died_in": [], "neighbors": []}
    graph_repo.get_entity_facts.return_value = sparse_facts

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
        patch("app.services.entity_resolution_service._graded_score", return_value=0.5),
        patch(
            "app.services.entity_resolution_service._gray_zone_judge",
            new=AsyncMock(
                return_value=EntityResolutionVerdict(
                    verdict="same", confidence=0.9, reasoning="clearly the same"
                )
            ),
        ),
        patch(
            "app.services.entity_resolution_service.execute_merge", new=AsyncMock()
        ) as mock_execute_merge,
        patch(
            "app.services.entity_resolution_service.update_alias_cache", new=AsyncMock()
        ),
    ):
        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        await resolve_entity(session, graph_repo, "e1")

        mock_execute_merge.assert_called_once()
        reviews_repo.create_review.assert_not_called()
        queue_repo.mark_status.assert_called_once_with("e1", "succeeded")


@pytest.mark.asyncio
async def test_gray_zone_judge_defaults_to_unsure_on_exception():
    from app.services.entity_resolution_service import _gray_zone_judge

    config_repo = AsyncMock()
    config_repo.get_value.return_value = "gemini-3.1-flash-lite"

    with patch("app.services.entity_resolution_service.genai") as mock_genai:
        mock_genai.Client.side_effect = RuntimeError("boom")
        verdict = await _gray_zone_judge({}, {}, {}, {}, config_repo)
        assert verdict.verdict == "unsure"
        assert verdict.confidence == 0.0


def test_expand_name_components_decomposes_names_and_filters_titles():
    from app.services.entity_resolution_service import _expand_name_components

    raw = ["زەھىرىددىن مۇھەممەد بابۇر", "سۇلتان بابۇر خان"]
    expanded = _expand_name_components(raw)

    # Full names should be preserved
    assert "زەھىرىددىن مۇھەممەد بابۇر" in expanded
    assert "سۇلتان بابۇر خان" in expanded

    # Distinctive name components should be included
    assert "زەھىرىددىن" in expanded
    assert "مۇھەممەد" in expanded
    assert "بابۇر" in expanded

    # Titles ("سۇلتان", "خان") should be excluded from standalone component tokens
    assert "سۇلتان" not in expanded
    assert "خان" not in expanded


@pytest.mark.asyncio
async def test_execute_merge_cleans_up_removed_entity_alias_keys():
    session = AsyncMock()
    graph_repo = AsyncMock()
    graph_repo.get_entity_by_id.side_effect = [
        {"id": "keep-1", "canonical_name": "Keep Node", "aliases": []},
        {"id": "remove-1", "canonical_name": "Remove Node", "aliases": []},
    ]
    graph_repo.get_entity_edges_snapshot.return_value = []
    graph_repo.get_children_via_child_of.return_value = []

    with (
        patch("app.services.entity_resolution_service.cache_service") as mock_cache,
        patch(
            "app.services.entity_resolution_service.GraphMergeLogRepository"
        ) as MockMergeLogRepo,
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
    ):
        merge_log_repo = AsyncMock()
        merge_log_entry = MagicMock(id=42)
        merge_log_repo.log_merge.return_value = merge_log_entry
        MockMergeLogRepo.return_value = merge_log_repo

        queue_repo = AsyncMock()
        MockQueueRepo.return_value = queue_repo
        reviews_repo = AsyncMock()
        MockReviewsRepo.return_value = reviews_repo
        config_repo = AsyncMock()
        config_repo.get_value.return_value = "5"
        MockConfigRepo.return_value = config_repo

        mock_cache.get = AsyncMock(return_value=["remove-1", "other-id"])
        mock_cache.set = AsyncMock()
        mock_cache.delete = AsyncMock()

        await execute_merge(
            session, graph_repo, "keep-1", "remove-1", "admin@example.com"
        )

        # mock_cache.set should be called with "remove-1" pruned
        mock_cache.set.assert_called()
        set_ids = mock_cache.set.call_args_list[0][0][1]
        assert set_ids == ["other-id"]
